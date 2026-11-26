# SPDX-License-Identifier: MIT
"""Draw one exact bounded XCL Mobile NeRF fragment and compare every sample."""

import argparse
import hashlib
import json
import statistics
import struct
import subprocess
from pathlib import Path

from run_source import ATTACHMENTS, compare


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("worker", "vertex", "fragment", "inputs", "native", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument(
        "--model", choices=("mlp_combo", "mlp_morpheus_combo"), required=True
    )
    p.add_argument("--device", required=True)
    args = p.parse_args()
    manifest = json.loads((args.inputs / "manifest.json").read_bytes())
    w, h = manifest["width"], manifest["height"]
    if (w, h) not in ((16, 16), (320, 180)):
        raise ValueError("Unsupported extent")
    oracle = (args.inputs / (args.model + ".cpu.rgba32f")).read_bytes()
    roots = json.loads((args.inputs / "root-layout.json").read_bytes())
    hashes = {}
    for name in [
        *ATTACHMENTS,
        "weights.bin",
        args.model + ".cpu.rgba32f",
        "sgprs.bin",
        "guest_mem.bin",
    ]:
        hashes[name] = digest((args.inputs / name).read_bytes())
        if (
            hashes[name]
            != (roots if name in ("guest_mem.bin", "sgprs.bin") else manifest)[
                "sha256"
            ][name]
        ):
            raise ValueError("Input digest mismatch: " + name)
    args.out.mkdir(parents=True, exist_ok=True)
    if any(args.out.iterdir()):
        raise ValueError("Output directory must be empty")
    target = args.out / "frame.rgba32f"
    worker = subprocess.run(
        [
            args.worker.resolve(),
            args.vertex.resolve(),
            args.fragment.resolve(),
            args.device,
            "bounded-nerf",
            args.inputs.resolve(),
            target.resolve(),
            f"{w}x{h}",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=50,
    )
    if worker.returncode:
        raise RuntimeError(worker.stderr or f"Code {worker.returncode}")
    gpu = json.loads(worker.stdout)
    pixels = target.read_bytes()
    native = args.native.read_bytes()
    if len(pixels) != len(oracle) or len(native) != len(pixels):
        raise ValueError("Incomplete frame")
    pixel = lambda b: list(struct.iter_unpack("<4f", b))
    pairs = list(zip(pixel(pixels), pixel(oracle)))
    metrics = {
        "alpha_mismatches": sum(a[3] != b[3] for a, b in pairs),
        "diagnostic_alpha": sum(a[3] == -7 for a, b in pairs),
        "max_abs_all": max(abs(x - y) for a, b in pairs for x, y in zip(a, b)),
        "first_pixel_pairs": [
            (i, a, b)
            for i, (a, b) in enumerate(pairs)
            if any(abs(x - y) > 1e-4 for x, y in zip(a, b))
        ][:6],
    }
    try:
        metrics["cpu"] = compare(pixels, oracle, w, h)
        metrics["native"] = compare(pixels, native, w, h)
        ok = True
    except ValueError as exc:
        metrics["mismatch"] = str(exc)
        ok = False
    receipt = {
        "device": args.device,
        "shader": args.model,
        "width": w,
        "height": h,
        "inputs": hashes,
        "worker_sha256": digest(args.worker.read_bytes()),
        "vertex_sha256": digest(args.vertex.read_bytes()),
        "fragment_sha256": digest(args.fragment.read_bytes()),
        "output_sha256": digest(pixels),
        "cpu_sha256": digest(oracle),
        "native_sha256": digest(native),
        "gpu": gpu,
        "median_gpu_ms": statistics.median(gpu["gpu_ms_per_draw"]),
        "metrics": metrics,
    }
    (args.out / "result.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            dict(
                ok=ok,
                sha=receipt["output_sha256"],
                gpu_ms=receipt["median_gpu_ms"],
                **metrics,
            )
        )
    )
    if not ok:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
