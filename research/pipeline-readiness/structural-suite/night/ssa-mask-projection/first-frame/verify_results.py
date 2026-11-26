# SPDX-License-Identifier: MIT
"""Check six image receipts and optionally reconnect an XCL runtime build to their shader hashes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
CASES = ("first-cold-pair", "counterbalanced-cold-pairs")
MODES = ("whole", "project")
CLOCKS = ("runtime_api_ms", "native_create_ms", "setup_submit_readback_ms", "guest_input_to_verified_image_wall_ms")


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def verify(raw_dirs):
    result = {"renderer_runs": 0, "pairs": [], "medians": {}}
    samples = {m: [] for m in MODES}
    reference = read(HERE / "fixture/scene.json")
    require(digest(HERE / "fixture/sgprs.bin") == reference["sgprs_sha256"], "wrong scalar fixture")
    gold = reference["reference_rgba32f_sha256"]
    current = read(HERE.parent / "runtime/cache-evidence.json")
    fixture = HERE / "fixture/raylib-synthetic.dxbc"
    require(digest(fixture) == current["fixture_sha256"], "wrong shader container")
    emitted = {m: {r["sha256"] for r in current["runs"] if r["mode"] == m} for m in MODES}
    require(all(len(v) == 1 for v in emitted.values()), "reference runtime has inconsistent DXIL")
    hashes = {m: next(iter(v)) for m, v in emitted.items()}
    require(hashes["whole"] != hashes["project"], "reference bytecode arms are identical")
    for ci, case in enumerate(CASES):
        trial = read(HERE / "measurements" / (case + ".json"))
        require(trial["reference_rgba32f_sha256"] == gold and trial["expected_dxil_sha256"] == hashes,
                "mismatch between prior framebuffer, recorded run and reference translator")
        for start in range(0, len(trial["rows"]), 2):
            a, b = trial["rows"][start:start + 2]
            require({a["mode"], b["mode"]} == set(MODES), "incomplete pair")
            for row in (a, b):
                require(row["qualified"] and row["draw_requested"] and row["cache"] == "cold" and
                        row["translated_cache_hits"] == 0 and len(row["new_cache_entries"]) == 1,
                        "invalid acquisition or cache state")
                require(row["rgba32f_sha256"] == gold and row["dxil_sha256"] == hashes[row["mode"]],
                        "wrong image or shader digest")
                if raw_dirs:
                    raw = raw_dirs[ci] / row["id"] / "frame.rgba32f"
                    require(raw.stat().st_size == 800 * 450 * 16 and digest(raw) == gold,
                            "archived framebuffer bytes disagree with the receipt")
                logs = row["worker_output"]
                renderer = "\n".join(logs["renderer.log"])
                require("1 passed; 0 failed" in renderer and "full_target_pixels=360000" in renderer and
                        not any(tag in renderer for tag in ("SKIPPED", "pso_cache_blob", "gpu_ms_per_draw")),
                        "invalid renderer receipt")
                guard = "\n".join(logs["guard.log"])
                require(re.search(r"\bexit=0\b", guard) and
                        f"peak_process_bytes={row['peak_render_process_bytes']}" in guard,
                        "missing guard completion or memory receipt")
                for key, log_name, label in (
                    ("runtime_api_ms", "runtime.log", "runtime_api_ms"),
                    ("native_create_ms", "renderer.log", "native_create_ms"),
                    ("setup_submit_readback_ms", "renderer.log", "scene_native_setup_submit_readback_ms"),
                ):
                    match = re.search(r"\b" + label + r"=([\d.]+)", "\n".join(logs[log_name]))
                    require(match and float(match[1]) == row[key], "timer disagrees with raw worker log")
                require(0 < row["native_create_ms"] <= row["setup_submit_readback_ms"] <
                        row["guest_input_to_verified_image_wall_ms"], "inconsistent nested intervals")
                samples[row["mode"]].append(row)
                result["renderer_runs"] += 1
            by_mode = {r["mode"]: r for r in (a, b)}
            delta = by_mode["whole"][CLOCKS[-1]] - by_mode["project"][CLOCKS[-1]]
            result["pairs"].append({"order": [a["mode"], b["mode"]], "outer_wall_saving_ms": round(delta, 4)})
    require(result["renderer_runs"] == 6 and len(result["pairs"]) == 3, "wrong record count")
    require(result["pairs"][1]["order"] == ["project", "whole"], "missing reversed order control")
    for key in CLOCKS:
        result["medians"][key] = {m: statistics.median(row[key] for row in samples[m]) for m in MODES}
    result["raw_frames_rehashed"] = 6 if raw_dirs else 0
    result["rgba32f_sha256"] = gold
    result["expected_dxil_sha256"] = hashes
    return result, current


def replay(runtime, dxc_dir, reference, result):
    binary_sha = digest(runtime)
    require(binary_sha == reference["observer_sha256"], "runtime differs from the pinned 0c8a01c observer")
    with tempfile.TemporaryDirectory(prefix="portbridge-first-frame-") as name:
        out = Path(name)
        for mode in MODES:
            dest = out / (mode + ".dxil")
            env = {k: v for k, v in os.environ.items() if not k.startswith("XCL_")}
            env.update(XCL_DXC_DIR=str(dxc_dir), XCL_DIRECT_DXIL="all", XCL_DXIL_CACHE=str(out / "cache"),
                       XCL_DIRECT_PIXEL_MASK_PROJECTION=str(int(mode == "project")))
            subprocess.run([runtime, HERE / "fixture/raylib-synthetic.dxbc", dest], env=env, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=45)
            require(digest(dest) == result["expected_dxil_sha256"][mode], f"new {mode} bytecode differs")
    result["live_runtime_check"] = {"revision": "0c8a01c7fe0e7364803262bbcd700f869776362b",
                                     "observer_sha256": binary_sha, "matched_modes": list(MODES),
                                     "new_gpu_runs": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=lambda p: Path(p).resolve())
    parser.add_argument("--dxc-dir", type=lambda p: Path(p).resolve())
    parser.add_argument("--raw-dirs", nargs=2, type=Path, metavar=("INITIAL_PAIR", "TWO_PAIRS"),
                        help="rehash all six locally archived RGBA32F readbacks")
    args = parser.parse_args()
    report, known = verify(args.raw_dirs)
    if bool(args.runtime) != bool(args.dxc_dir):
        parser.error("--runtime and --dxc-dir must be used together")
    if args.runtime:
        replay(args.runtime, args.dxc_dir, known, report)
    print(json.dumps(report, indent=2))
