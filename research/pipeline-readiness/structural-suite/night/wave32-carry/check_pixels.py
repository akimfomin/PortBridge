# SPDX-License-Identifier: MIT
"""Check expected populations, render coverage and per-shader histograms from RGBA32F."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import struct


GEOMETRIES = {"full": 1024, "diagonal": 1024, "edge": 496, "cropped": 409}


def inspect(raw, expected_covered):
    if len(raw) != 32 * 32 * 16:
        raise ValueError("expected a complete 32 by 32 RGBA32F image")
    coverage = bytearray()
    populations = Counter()
    for red, green, blue, alpha in struct.iter_unpack("<4f", raw):
        if (red, green, blue, alpha) == (-99.,) * 4:
            coverage.append(0)
            continue
        if (blue, alpha) != (1., 1.) or not all(x.is_integer() and 0 <= x <= 32 for x in (red, green)):
            raise ValueError("invalid pixel sentinel or population")
        coverage.append(1)
        populations[int(red), int(green)] += 1
    if sum(coverage) != expected_covered:
        raise ValueError("unexpected primitive coverage")
    return {"covered": sum(coverage), "coverage_sha256": sha256(coverage).hexdigest(),
            "sha256": sha256(raw).hexdigest(),
            "mismatched_pixels": sum(n for (observed, expected), n in populations.items() if observed != expected),
            "red_green": {f"{r}/{g}": n for (r, g), n in sorted(populations.items())}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", type=Path)
    parser.add_argument("arms", nargs="+")
    args = parser.parse_args()
    rows = []
    footprints = {}
    for case in ("wave32-s21-read", "wave32-s21-read-wqm"):
        for arm in args.arms:
            for geometry, count in GEOMETRIES.items():
                name = f"{case}-{arm}-{geometry}.rgba32f"
                result = inspect((args.images / name).read_bytes(), count)
                ref = footprints.setdefault(geometry, result["coverage_sha256"])
                if ref != result["coverage_sha256"]:
                    raise ValueError(f"{name}: raster coverage differs")
                rows.append({"case": case, "arm": arm, "geometry": geometry, **result})
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
