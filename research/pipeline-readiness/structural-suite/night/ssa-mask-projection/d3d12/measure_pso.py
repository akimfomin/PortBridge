# SPDX-License-Identifier: MIT
"""Measure one cold, unsubmitted XCL graphics pipeline per guarded process."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


TEST = "gpu::dxil::aperture_tests::aperture_open_pixel_pso"
PHASES = ("before_create", "after_create", "with_blob", "after_release",
          "with_16mib_resource", "after_calibration_release")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def balanced_order(names, block):
    # Williams order. For odd arm counts alternate the mirrored square.
    n = len(names)
    positions = [0]
    for i in range(1, n):
        positions.append((i + 1) // 2 if i % 2 else n - i // 2)
    if n % 2 and (block // n) % 2:
        positions.reverse()
    return [names[(p + block) % n] for p in positions]


def read_sample(log, guard, adapter, length):
    records = re.findall(r"^pso_memory phase=(\w+) (.*)$", log, re.M)
    if [phase for phase, _ in records] != list(PHASES):
        raise ValueError("missing or reordered memory phases")
    memory = {phase: {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", values)}
              for phase, values in records}
    fields = {"local_bytes", "nonlocal_bytes", "local_budget", "nonlocal_budget", "private_bytes", "working_set_bytes"}
    if any(row.keys() != fields for row in memory.values()):
        raise ValueError("incomplete memory counters")
    result = re.search(r"^aperture sample adapter=(.+) native_ms=([\d.]+) opaque_cache_bytes=(\d+) dxil_bytes=(\d+)$", log, re.M)
    peak = re.fullmatch(r"exit=0 peak_process_bytes=(\d+) peak_job_bytes=(\d+)", guard.strip())
    if (not result or not peak or result[1] != adapter or int(result[4]) != length
            or "test result: ok. 1 passed; 0 failed;" not in log):
        raise ValueError("incomplete sample or unexpected hardware/input")
    return {"native_create_ms": float(result[2]), "opaque_cache_bytes": int(result[3]),
            "dxil_bytes": length, "memory": memory, "job_peak_process_bytes": int(peak[1]),
            "job_peak_total_bytes": int(peak[2])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("manifest", "guard", "tests", "dxc_dir", "out"):
        parser.add_argument("--" + key.replace("_", "-"), dest=key, required=True, type=Path)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--small-job", action="store_true", help="Use the 512 MiB cap for both child and job")
    parser.add_argument("--headroom-wait", type=int, default=0, choices=range(0, 301), metavar="SECONDS")
    parser.add_argument("--blocks", type=int, default=4, choices=range(1, 13))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cases = manifest["cases"]
    if not cases or len(cases) > 256 or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("expected 1–256 uniquely named cases")
    inputs = {}
    for case in cases:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", case["id"]) or not 0 <= case["varyings"] <= 16:
            raise ValueError("invalid case name or input count")
        if not 1 <= len(case["arms"]) <= 8:
            raise ValueError("expected 1–8 arms")
        for arm, info in case["arms"].items():
            path = (args.manifest.parent / info["file"]).resolve()
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", arm) or sha(path) != info["sha256"]:
                raise ValueError(f"invalid arm or shader identity in {case['id']}/{arm}")
            inputs[case["id"], arm] = path
    args.out.mkdir(parents=True, exist_ok=False)
    tools = {name: sha(path) for name, path in {
        "guard": args.guard, "tests": args.tests, "dxcompiler": args.dxc_dir / "dxcompiler.dll",
        "dxil_validator": args.dxc_dir / "dxil.dll"}.items()}
    metadata = {"adapter": args.adapter, "test": TEST, "blocks": args.blocks, "tools": tools,
                "job_cap_mib": 512 if args.small_job else 2048,
                "manifest_sha256": sha(args.manifest), "cases": [
                    {"id": c["id"], "varyings": c["varyings"],
                     "arms": {arm: info["sha256"] for arm, info in c["arms"].items()}} for c in cases]}
    (args.out / "identity.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("XCL_")}
    env["XCL_DXC_DIR"] = str(args.dxc_dir.resolve())
    for block in range(args.blocks):
        offset = block % len(cases)
        for n, case in enumerate(cases[offset:] + cases[:offset]):
            for pos, arm in enumerate(balanced_order(list(case["arms"]), block)):
                path = inputs[case["id"], arm]
                log = (args.out / f"{block:02d}-{n:03d}-{pos}-{case['id']}-{arm}.log").resolve()
                env.update(XCL_APERTURE_SAMPLE_PS=str(path), XCL_APERTURE_SAMPLE_VARYINGS=str(case["varyings"]))
                started = time.time()
                command = [args.guard.resolve(), args.tests.resolve(), log, TEST]
                if args.small_job:
                    command.append("--512-mib")
                deadline = time.monotonic() + args.headroom_wait
                refused = 0
                while True:
                    run = subprocess.run(command, capture_output=True, text=True, env=env, timeout=30)
                    if (run.returncode != 2 or run.stderr.strip() != "Insufficient system commit or RAM headroom"
                            or log.exists() or time.monotonic() >= deadline):
                        break
                    # The guard checks headroom before opening the log or creating a child.
                    refused += 1
                    time.sleep(min(5., max(0., deadline - time.monotonic())))
                receipt = {"block": block, "position": pos, "id": case["id"], "arm": arm,
                           "unix_start": started, "guard_exit": run.returncode, "prelaunch_refusals": refused}
                if run.returncode:
                    receipt["error"] = (run.stderr or run.stdout).strip()
                else:
                    try:
                        receipt.update(read_sample(log.read_text(encoding="utf-8", errors="replace"),
                                                   run.stdout, args.adapter, path.stat().st_size))
                    except ValueError as error:
                        receipt["error"] = str(error)
                with (args.out / "samples.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(receipt) + "\n")
                if "error" in receipt:
                    raise SystemExit(f"Stopped at {log.name}: {receipt['error']}")


if __name__ == "__main__":
    main()
