"""Run a balanced two-factor test using the same physical Halide preview."""

import argparse
import math
import os
from pathlib import Path
from statistics import median

import run_preview


VARIANTS = ("stock", "reuse", "park", "reuse-park")
ORDERS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))
COUNTERS = ("pipelineRequests", "errorPops", "submissions", "bufferCopies", "bufferMaps")


class ParkingPreviewHandler(run_preview.PreviewHandler):
    variant_path = "/preview_parking.mjs"

    def __init__(self, *args, assets, **kwargs):
        assets = dict(assets)
        assets["/preview.mjs"] = assets[self.variant_path]
        super().__init__(*args, assets=assets, **kwargs)


def summarise(payload, args, inventory, reference):
    if payload.get("ok") is not True:
        raise ValueError(f"Preview failed: {payload.get('error')}")
    report = payload["report"]
    physical = run_preview.attest_adapter(report, inventory, reference)
    if (report["imageSha256"] != run_preview.IMAGE_SHA256
            or report["pairs"] != args.pairs or report["frames"] != args.frames
            or report["size"] != 512 or len(report["hashes"]) != args.frames
            or len(report["results"]) != args.pairs * len(VARIANTS)
            or report["trace"] != args.trace):
        raise ValueError("Browser report does not match the requested workload")

    samples = {variant: [] for variant in VARIANTS}
    for pair in range(args.pairs):
        rows = report["results"][pair * 4: (pair + 1) * 4]
        order = ORDERS[pair % len(ORDERS)]
        baseline_counts = tuple(rows[0][key] for key in COUNTERS)
        for row, index in zip(rows, order):
            variant = VARIANTS[index]
            if row["mode"] != variant or row["pair"] != pair or len(row["times"]) != args.frames:
                raise ValueError(f"Unexpected order at round {pair}: {variant}")
            if tuple(row[key] for key in COUNTERS) != baseline_counts:
                raise ValueError(f"Changed GPU operations at round {pair}: {variant}")
            expected_creates = 0 if variant.startswith("reuse") else row["pipelineRequests"]
            if (row["nativePipelineCreates"] != expected_creates or row["bufferMaps"] < args.frames
                    or row["maxAbsoluteError"] > 5e-6 or row.get("gpuErrors", 0) != 0):
                raise ValueError(f"Unexpected dispatch or reference result: {variant}")
            for observation in row["times"]:
                readback = observation["inputToReadbackMs"]
                bitmap = observation["inputToBitmapMs"]
                if not (math.isfinite(bitmap) and 0 < readback <= bitmap):
                    raise ValueError(f"Invalid observation: {observation}")
            samples[variant].append(row)

    def per_round(variant, field):
        return [sum(t[field] for t in row["times"]) / args.frames for row in samples[variant]]

    bitmap = {variant: per_round(variant, "inputToBitmapMs") for variant in VARIANTS}
    summary = {
        "adapter_attestation": physical,
        "browser_user_agent": report["userAgent"],
        "scope": "Sigma change through Halide/WebGPU to synchronized float readback and canvas bitmap",
        "pairs": args.pairs,
        "frames_per_variant_per_pair": args.frames,
        "verified_values": 512 * 512 * len(VARIANTS) * args.frames * args.pairs,
        "max_absolute_error": max(row["maxAbsoluteError"] for row in report["results"]),
        "image_file_sha256": report["imageSha256"],
        "input_luma_sha256": report["inputSha256"],
        "bitmap_ms": {variant: median(bitmap[variant]) for variant in VARIANTS},
        "bitmap_ms_per_round": bitmap,
        "readback_ms": {
            variant: median(per_round(variant, "inputToReadbackMs")) for variant in VARIANTS
        },
        "reuse_to_reuse_park_paired_ratio": median(
            before / after for before, after in zip(bitmap["reuse"], bitmap["reuse-park"])
        ),
        "webgpu_calls_per_preview": {
            variant: {
                key: median(row[key] for row in samples[variant]) / args.frames
                for key in (*COUNTERS, "nativePipelineCreates")
            }
            for variant in VARIANTS
        },
    }
    if args.trace:
        summary["poll_sleeps_per_preview"] = {
            variant: {
                kind: median(row["pollCounts"][kind] for row in samples[variant]) / args.frames
                for kind in ("scope", "map", "other")
            }
            for variant in VARIANTS
        }
    if args.failure_probe:
        if [error["variant"] for error in report["errors"]] != ["stock", "park"]:
            raise ValueError("Expected both scoped failure controls")
        summary["error_controls"] = report["errors"]
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--chrome", type=Path, default=Path(
        os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe")
    parser.add_argument("--expect-gpu", default="RTX 4070 Ti SUPER")
    parser.add_argument("--pairs", type=int, choices=(4, 8, 12, 16, 20), default=8)
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=55)
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--failure-probe", action="store_true")
    args = parser.parse_args()
    host_asset = "preview_host_parking.mjs"
    if args.failure_probe:
        ParkingPreviewHandler.variant_path = "/preview_parking_failure.mjs"
        host_asset = "preview_host_failures_parking.mjs"
        args.wasm_asset = "preview_host_failures.wasm"
        run_preview.ASSETS[args.wasm_asset] = "application/wasm"
    for asset in (host_asset, ParkingPreviewHandler.variant_path[1:], "callback_parking.mjs"):
        run_preview.ASSETS[asset] = "text/javascript; charset=utf-8"
    run_preview.PreviewHandler = ParkingPreviewHandler
    run_preview.summarise = summarise
    run_preview.run(args)


if __name__ == "__main__":
    main()
