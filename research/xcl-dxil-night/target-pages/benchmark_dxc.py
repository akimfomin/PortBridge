"""Pair exact-source DXC process times for the target lookup experiment."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess
import time


def run(dxc, target, source):
    started = time.perf_counter_ns()
    subprocess.run(
        [dxc, "-T", "cs_6_6", "-E", "main", "-O3", "-Qstrip_reflect",
         "-Fo", target, source],
        capture_output=True, check=True, timeout=20,
    )
    return (time.perf_counter_ns() - started) / 1e6


def compare(dxc, fixtures, scratch):
    manifest = json.loads((fixtures / "results.json").read_text(encoding="utf-8"))
    scratch.mkdir(exist_ok=False)
    target = scratch / "output.dxil"
    results = []
    for index, fixture in enumerate(manifest["fixtures"]):
        ordered = ("blocks", "case_count", "shape", "existing_words")
        stem = "-".join(str(fixture[key]) for key in ordered)
        raw = []
        for pair in range(12):
            order = ("inline", "pages") if (pair + index) % 2 == 0 else ("pages", "inline")
            measurements = {}
            for name in order:
                source = fixtures / f"{stem}-{name}.hlsl"
                record = fixture["variants"][name]
                assert source.stat().st_size == record["source_bytes"]
                measurements[name] = run(dxc, target, source)
                assert sha256(target.read_bytes()).hexdigest() == record["container_sha256"]
            raw.append({"order": order, "ms": measurements})
        results.append({
            "fixture": stem,
            "median_inline_ms": median(pair["ms"]["inline"] for pair in raw),
            "median_pages_ms": median(pair["ms"]["pages"] for pair in raw),
            "median_paired_ratio": median(pair["ms"]["pages"] / pair["ms"]["inline"] for pair in raw),
            "pairs": raw,
        })
    target.unlink()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dxc", type=Path)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("scratch", type=Path)
    args = parser.parse_args()
    results = compare(args.dxc.resolve(strict=True), args.fixtures.resolve(strict=True), args.scratch)
    (args.scratch / "dxc-times.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    for item in results:
        print(
            f"{item['fixture']}: {item['median_inline_ms']:.2f} -> {item['median_pages_ms']:.2f} ms, "
            f"paired ratio {item['median_paired_ratio']:.3f}"
        )


if __name__ == "__main__":
    main()
