"""Verify and optionally dispatch the two bounded, source-generated target fixtures."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import runpy
import subprocess
import time


HERE = Path(__file__).resolve().parent
WORK = HERE.parent
ADAPTER = "NVIDIA GeForce RTX 4070 Ti SUPER"
RUNNER = WORK / "portbridge-anyxboxx-133-4a67f676/.trial-native/anyxboxx_gpu_run.exe"
RUNNER_SHA = "290c45ac185c3cc5999a887ac9941656f3d1f1e21d2850986edd01a27db68682"
HEADROOM = WORK / "portbridge-xbox2windows-1998-spill-84ce2942/out/mesh-spill/run-guarded.py"
STEM = "96-1-clustered-3"


def sha(data):
    return sha256(data).hexdigest()


def verified_inputs(directory):
    info = json.loads((directory / "readback-meta.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "results.json").read_text(encoding="utf-8"))
    small = manifest["fixtures"][0]
    assert small["blocks"] == info["groups"] == 96 and small["encoded_cases"] == [0]
    assert info["bytes"] == info["words"] * 4 == 96 * 64 * 4
    initial = (directory / "readback-initial.bin").read_bytes()
    reference = (directory / "readback-reference.bin").read_bytes()
    assert len(initial) == len(reference) == info["bytes"]
    assert initial != reference and sha(reference) == info["expected_hash"]
    for name in ("inline", "pages"):
        shader = (directory / f"{STEM}-{name}.dxil").read_bytes()
        record = small["variants"][name]
        assert shader[:4] == b"DXBC" and len(shader) == record["container_bytes"] <= 4096
        assert sha(shader) == record["container_sha256"]
    return initial, reference


def admitted(headroom, deadline):
    consecutive = 0
    while time.monotonic() < deadline:
        commit, ram = headroom()
        consecutive = consecutive + 1 if commit >= 4 and ram >= 6 else 0
        if consecutive == 2:
            return commit, ram
        time.sleep(0.75)
    raise SystemExit("No stable memory admission window. No further child was launched.")


def measure(directory, result_dir, initial, reference):
    assert sha(RUNNER.read_bytes()) == RUNNER_SHA
    headroom = runpy.run_path(str(HEADROOM), run_name="portbridge_guard")["headroom"]
    guard = HERE / "readback_guard.exe"
    result_dir.mkdir(exist_ok=False)
    env = {**os.environ, "ANYXBOXX_GPU": ADAPTER}
    deadline = time.monotonic() + 34
    for name in ("inline", "pages"):
        mem = result_dir / f"{name}-memory.bin"
        log = result_dir / f"{name}-driver.log"
        mem.write_bytes(initial)
        commit, ram = admitted(headroom, deadline)
        print(f"{name}: {commit:.2f} GiB commit and {ram:.2f} GiB physical available", flush=True)
        result = subprocess.run(
            [guard, "readback", RUNNER, directory / f"{STEM}-{name}.dxil", mem, log],
            env=env, capture_output=True, text=True, timeout=5, check=False,
        )
        (result_dir / f"{name}-guard.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        print(result.stdout.strip(), flush=True)
        guard_result = json.loads(result.stdout)
        if (result.returncode or guard_result["guard"] != "returned" or
                not guard_result["reaped"] or guard_result["peak_bytes"] > 512 * 1024 * 1024):
            raise SystemExit("Guarded arm did not finish. No retry or subsequent launch.")
        driver_log = log.read_text(encoding="utf-8", errors="replace")
        if "96 groupe(s)" not in driver_log:
            raise SystemExit(f"Unexpected runner output in {log}")
        actual = mem.read_bytes()
        if actual != reference:
            if len(actual) != len(reference):
                raise SystemExit("Unexpected readback length")
            first = next(i for i, (a, b) in enumerate(zip(actual, reference)) if a != b)
            raise SystemExit(f"{name} readback differs at byte {first}")
        print(f"{name}: {len(actual) // 4} exact output words, SHA-256 {sha(actual)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--native-result-dir", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve(strict=True)
    initial, reference = verified_inputs(directory)
    print(f"Verified the paired fixtures and independently interpreted {len(reference)//4} words", flush=True)
    if args.native_result_dir:
        measure(directory, args.native_result_dir.resolve(), initial, reference)


if __name__ == "__main__":
    main()
