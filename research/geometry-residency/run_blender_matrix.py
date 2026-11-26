"""Reproduce the licensed Blender Particle Simulation measurements."""

import argparse
import hashlib
import os
from pathlib import Path
import subprocess

from analyze import analyze


ASSET_SHA256 = "6c8c381c234030d86a25fb34579e60963973fb20482c9e602196db0380f5ac67"
BUILD = "8657240ced44"
HERE = Path(__file__).resolve().parent


def run(blender, asset, root, pairs, timeout):
    if timeout <= 0:
        raise ValueError("Timeout must be positive")
    with asset.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != ASSET_SHA256:
            raise ValueError("Expected the official CC0 Particle Simulation .blend")
    version = subprocess.check_output([str(blender), "--version"], text=True, timeout=timeout)
    if BUILD not in version:
        raise ValueError(f"Expected Blender WIP build {BUILD}")
    if pairs < 2 or pairs % 2:
        raise ValueError("Use an even number of pairs to balance run ordering")
    root.mkdir(parents=True, exist_ok=False)
    environment = {**os.environ, "BLENDER_USER_RESOURCES": str(root / "user-resources")}
    command = [str(blender), "--background", "--factory-startup", "--disable-autoexec",
               "--gpu-backend", "vulkan", "--debug-gpu-backend-no-fallback", "--python-exit-code", "5"]

    def evaluate(label, arm, last_frame, sample_frames=()):
        observer = [value for frame in sample_frames for value in ("--sample", str(frame))]
        logging = ["--log", "nodes.gpu_field,geom.list", "--log-level", "debug"] if observer else []
        arguments = ["--object", "Particles", "--last-frame", str(last_frame), "--capture", arm]
        log_path = root / f"{label}.log"
        with log_path.open("xb") as output:
            subprocess.run(command + logging + [str(asset), "--python", str(HERE / "blender_measure.py"),
                           "--", str(root / label), *arguments, *observer],
                           stdout=output, stderr=subprocess.STDOUT, cwd=root, env=environment,
                           timeout=timeout, check=True)
        print(label, flush=True)

    for arm in ("cpu", "gpu"):
        evaluate(f"official-{arm}-points", arm, 120, (2, 20, 70, 120))
    for pair in range(1, pairs + 1):
        order = ("cpu", "gpu") if pair % 2 else ("gpu", "cpu")
        for arm in order:
            evaluate(f"official-{pair}-{arm}", arm, 150)
    analyze(root, root / "evidence", pairs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blender", type=Path)
    parser.add_argument("asset", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--pairs", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=60, help="seconds per Blender process")
    args = parser.parse_args()
    run(args.blender.resolve(strict=True), args.asset.resolve(strict=True),
        args.destination.resolve(), args.pairs, args.timeout)
