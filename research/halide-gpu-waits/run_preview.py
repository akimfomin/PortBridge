"""Compare real Halide WebAssembly preview paths in a fresh Windows Chrome profile."""

import argparse
from datetime import datetime, timezone
from functools import partial
import hashlib
from http.server import ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import queue
import secrets
from statistics import median
import subprocess
import sys
import threading
from urllib.parse import urlencode

from browser_runner import (
    Handler, adapter_reference, attest_adapter, read_browser_result, stop_launched_browser,
)

ROOT = Path(__file__).resolve().parent


IMAGE_SHA256 = "88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5"
IMAGE_ASSET = "astronaut.png"
ASSETS = {
    "preview.html": "text/html; charset=utf-8",
    "preview.mjs": "text/javascript; charset=utf-8",
    "preview_host.mjs": "text/javascript; charset=utf-8",
    "preview_host.wasm": "application/wasm",
    "astronaut.png": "image/png",
}


class PreviewHandler(Handler):
    def send_header(self, key, value):
        if key.casefold() == "content-security-policy":
            value = value.replace("script-src 'self'", "script-src 'self' 'wasm-unsafe-eval'")
        super().send_header(key, value)


def summarise(payload, args, inventory, reference):
    if payload.get("ok") is not True:
        raise ValueError("Browser preview failed: " + str(payload.get("error", "empty result")))
    report = payload["report"]
    physical = attest_adapter(report, inventory, reference)
    if (
        report["imageSha256"] != IMAGE_SHA256 or report["pairs"] != args.pairs
        or report["frames"] != args.frames or report["size"] != 512
        or report["trace"] != args.trace or len(report["hashes"]) != args.frames
        or len(report["results"]) != args.pairs * 2
    ):
        raise ValueError("Browser report does not match the requested workload")

    by_mode = {"stock": [], "reuse": []}
    for pair in range(args.pairs):
        rows = report["results"][pair*2:pair*2+2]
        modes = ("stock", "reuse") if pair % 2 == 0 else ("reuse", "stock")
        for mode, row in zip(modes, rows):
            if row["mode"] != mode or row["pair"] != pair or len(row["times"]) != args.frames:
                raise ValueError(f"Unexpected sample sequence at pair {pair}, {mode}")
            if row["pipelineRequests"] <= 0 or row["nativePipelineCreates"] != (row["pipelineRequests"] if mode == "stock" else 0):
                raise ValueError(f"Requested pipeline treatment did not occur at pair {pair}, {mode}: {row}")
            if row["bufferMaps"] < args.frames or row["maxAbsoluteError"] > 5e-6:
                raise ValueError(f"Preview did not validate the expected readback at pair {pair}, {mode}")
            for observation in row["times"]:
                bitmap = observation["inputToBitmapMs"]
                readback = observation["inputToReadbackMs"]
                if not (math.isfinite(bitmap) and 0 < readback <= bitmap):
                    raise ValueError(f"Invalid timing at pair {pair}, {mode}: {observation}")
            by_mode[mode].append(row)
        for field in ("pipelineRequests", "errorPops", "submissions", "bufferCopies", "bufferMaps"):
            if rows[0][field] != rows[1][field]:
                raise ValueError(f"Observed different runtime behavior at pair {pair}, {field}")

    def paired_totals(mode, field):
        return [sum(timing[field] for timing in row["times"]) for row in by_mode[mode]]

    def timing_summary(field):
        stock = paired_totals("stock", field)
        reuse = paired_totals("reuse", field)
        return {
            "stock_ms_per_preview": median(stock) / args.frames,
            "reuse_ms_per_preview": median(reuse) / args.frames,
            "median_paired_stock_to_reuse_ratio": median(before/after for before, after in zip(stock, reuse)),
            "stock_ms_per_pair": stock,
            "reuse_ms_per_pair": reuse,
        }

    scope = {
        "visible_bitmap": "Sigma change through Halide GPU processing, host readback and synchronous canvas bitmap update",
        "readback": "Sigma change through verified Halide GPU output copied to WebAssembly memory",
        "exclusions": "Initial image decode, resident input upload, CPU-reference checks, hashing, browser compositor and display scanout",
    }
    summary = {
        "scope": scope, "adapter_attestation": physical, "browser_user_agent": report["userAgent"],
        "trace": args.trace, "pairs": args.pairs, "frames_per_mode_per_pair": args.frames,
        "verified_values": 512*512*2*args.frames*args.pairs,
        "max_absolute_error": max(row["maxAbsoluteError"] for row in report["results"]),
        "image_file_sha256": report["imageSha256"], "decoded_luma_sha256": report["inputSha256"],
        "first_adapter_acquisition_and_upload_ms": report["initializeAndUploadMs"],
        "input_to_bitmap": timing_summary("inputToBitmapMs"),
        "input_to_readback": timing_summary("inputToReadbackMs"),
        "webgpu_calls_per_preview": {
            mode: {
                key: median(row[key] for row in rows) / args.frames
                for key in ("pipelineRequests", "nativePipelineCreates", "errorPops", "submissions", "bufferCopies", "bufferMaps")
            } for mode, rows in by_mode.items()
        },
    }
    if args.trace:
        summary["diagnostics"] = {
            mode: {
                "distinct_pipeline_descriptors_per_batch": sorted(set(row["distinctDescriptors"] for row in rows)),
                "pipeline_create_sum_ms_per_preview": median(row["pipelineCreateMs"] for row in rows)/args.frames,
                "native_error_scope_callback_sum_ms_per_preview": median(row["errorCallbackMs"] for row in rows)/args.frames,
                "native_map_callback_sum_ms_per_preview": median(row["mapCallbackMs"] for row in rows)/args.frames,
                "wasm_sleep_calls_per_preview": {
                    kind: median(row["pollCounts"][kind] for row in rows)/args.frames
                    for kind in ("scope", "map", "other")
                },
                "wasm_sleep_ms_per_preview": {
                    kind: median(row["pollMs"][kind] for row in rows)/args.frames
                    for kind in ("scope", "map", "other")
                },
                "gpu_errors": sum(row["gpuErrors"] for row in rows),
            } for mode, rows in by_mode.items()
        }
    return summary


def run(args):
    chrome = args.chrome.resolve(strict=True)
    dest = args.out.resolve()
    if os.name != "nt" or dest == ROOT or not dest.is_relative_to(ROOT):
        raise ValueError("This Windows launcher requires a fresh output directory inside its scratch directory")
    if not 5 <= args.timeout <= 60 or not 2 <= args.pairs <= 20 or args.pairs % 2 or not 2 <= args.frames <= 10:
        raise ValueError("Use a 5–60 second timeout, 2–20 even pairs, and 2–10 frames")
    assets = {"/" + name: (mime, (ROOT / name).read_bytes()) for name, mime in ASSETS.items()}
    if hashlib.sha256(assets["/" + IMAGE_ASSET][1]).hexdigest() != IMAGE_SHA256:
        raise ValueError("Public-domain image integrity check failed")
    dest.mkdir(parents=True, exist_ok=False)
    inventory, reference = adapter_reference(args.expect_gpu)
    token = secrets.token_urlsafe(24)
    results = queue.Queue(maxsize=1)
    factory = partial(PreviewHandler, assets=assets, token=token, results=results)
    server = ThreadingHTTPServer(("127.0.0.1", 0), factory)
    profile = dest / "chrome-profile"
    query = urlencode({"run": 1, "result": "/result/" + token, "pairs": args.pairs,
                       "frames": args.frames, "trace": int(args.trace)})
    url = f"http://127.0.0.1:{server.server_port}/preview.html?" + query
    command = [str(chrome), "--headless", "--enable-gpu", "--no-first-run",
               "--no-default-browser-check", "--disable-background-networking",
               "--user-data-dir=" + str(profile), url]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with (dest / "chrome.log").open("xb") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW, cwd=dest)
            try:
                payload = read_browser_result(process, results, args.timeout)
            finally:
                stop_launched_browser(process)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    (dest / "browser-result.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    summary = summarise(payload, args, inventory, reference)
    wasm_asset = getattr(args, "wasm_asset", "preview_host.wasm")
    summary["wasm_file_sha256"] = hashlib.sha256(assets["/" + wasm_asset][1]).hexdigest()
    summary["javascript_sha256"] = {
        name[1:]: hashlib.sha256(data).hexdigest()
        for name, (_, data) in assets.items() if name.endswith(".mjs")
    }
    summary["collected_utc"] = datetime.now(timezone.utc).isoformat()
    (dest / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--chrome", type=Path, default=Path(
        os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe")
    parser.add_argument("--expect-gpu", default="RTX 4070 Ti SUPER")
    parser.add_argument("--pairs", type=int, default=8)
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=55)
    parser.add_argument("--trace", action="store_true")
    try:
        run(parser.parse_args())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Preview unavailable: {error}", file=sys.stderr)
        sys.exit(1)
