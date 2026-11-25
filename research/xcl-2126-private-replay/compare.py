# SPDX-License-Identifier: MIT
"""Summarize aggregate-only A/B measurements for XCL #2126."""

import argparse
import itertools
import json
import math
from pathlib import Path
from statistics import median


BASE = "3283da481077c1962f13f1b4078841662f7a4ccb"
PATCH = "2e46a3635ee7725860ceec08ca246a2ab14615b9"
REAL_CASES = {
    ("ef008c0f", "early-exit"): (10, 45632),
    ("ef008c0f", "late-shading"): (10, 45632),
    ("c3ae6819", "representative"): (14, 54240),
    ("fb1c6d2d", "representative"): (14, 54432),
}
SYNTHETIC_CASES = {
    ("upstream-wave32-loops", "synthetic"): (4, 288),
    ("four-piece-fragmentation", "synthetic"): (4, 192),
}
BUILDS = ("baseline", "candidate")
FIELDS = {
    "case", "input", "build", "grid", "pieces", "scratch_dwords_per_group",
    "words_checked", "different_words", "gpu_us_rounds",
}


def positive_int(value):
    return type(value) is int and value > 0


def load_measurements(path, expected_cases):
    measurements = {}
    with path.open(encoding="utf-8") as source:
        for line_no, line in enumerate(source, 1):
            try:
                row = json.loads(line)
            except ValueError as error:
                raise ValueError(f"row {line_no} does not contain JSON") from error
            if type(row) is not dict or set(row) != FIELDS:
                raise ValueError(f"row {line_no} uses fields outside the aggregate schema")
            if any(type(row[name]) is not str for name in ("case", "input", "build")):
                raise ValueError(f"row {line_no} has invalid labels")
            case = row["case"], row["input"]
            if case not in expected_cases or row["build"] not in BUILDS:
                raise ValueError(f"row {line_no} has an unexpected case or build")
            key = (*case, row["build"])
            if key in measurements:
                raise ValueError(f"row {line_no} duplicates an earlier measurement")
            grid = row["grid"]
            if type(grid) is not list or len(grid) != 3 or not all(map(positive_int, grid)):
                raise ValueError(f"row {line_no} needs three positive dispatch dimensions")
            expected_pieces, expected_scratch = expected_cases[case]
            words = row["scratch_dwords_per_group"]
            if not positive_int(row["pieces"]) or row["pieces"] != expected_pieces:
                raise ValueError(f"row {line_no} does not cover the expected split chain")
            if not positive_int(words) or (row["build"] == "baseline" and words != expected_scratch):
                raise ValueError(f"row {line_no} does not match the published baseline or has invalid scratch")
            checked, different = row["words_checked"], row["different_words"]
            if not positive_int(checked) or type(different) is not int or not 0 <= different <= checked:
                raise ValueError(f"row {line_no} has invalid output comparison counts")
            rounds = row["gpu_us_rounds"]
            if type(rounds) is not list or len(rounds) != 4:
                raise ValueError(f"row {line_no} needs four timing rounds")
            for block in rounds:
                if type(block) is not list or len(block) != 20:
                    raise ValueError(f"row {line_no} needs 20 GPU times per round")
                if not all(type(t) in (int, float) and 1e-6 <= t <= 1e9 and math.isfinite(t) for t in block):
                    raise ValueError(f"row {line_no} has invalid GPU times")
            measurements[key] = row
    expected_keys = {(*case, build) for case in expected_cases for build in BUILDS}
    if not expected_keys.issubset(measurements):
        missing = ", ".join("/".join(key) for key in sorted(expected_keys - measurements.keys()))
        raise ValueError(f"incomplete comparison, missing {missing}")
    return measurements


def summarize(measurements, cases):
    rows = []
    for case, kind in cases:
        before, after = (measurements[case, kind, build] for build in BUILDS)
        if before["grid"] != after["grid"] or before["words_checked"] != after["words_checked"]:
            raise ValueError(f"{case}/{kind} must use the same grid and output reference coverage")
        before_words = before["scratch_dwords_per_group"]
        after_words = after["scratch_dwords_per_group"]
        before_rounds, after_rounds = (row["gpu_us_rounds"] for row in (before, after))
        before_us, after_us = (median(itertools.chain.from_iterable(rounds)) for rounds in (before_rounds, after_rounds))
        round_deltas = [
            100 * (median(candidate) / median(baseline) - 1)
            for baseline, candidate in zip(before_rounds, after_rounds, strict=True)
        ]
        rows.append({
            "case": case,
            "input": kind,
            "grid": before["grid"],
            "pieces": before["pieces"],
            "baseline_scratch_dwords_per_group": before_words,
            "candidate_scratch_dwords_per_group": after_words,
            "scratch_reduction_percent": round(100 * (1 - after_words / before_words), 3),
            "baseline_gpu_us_median": round(before_us, 6),
            "candidate_gpu_us_median": round(after_us, 6),
            "candidate_time_delta_percent": round(100 * (after_us / before_us - 1), 3),
            "round_time_delta_percent_min_max": [round(delta, 3) for delta in (min(round_deltas), max(round_deltas))],
            "words_checked_per_build": before["words_checked"],
            "baseline_different_words": before["different_words"],
            "candidate_different_words": after["different_words"],
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("measurements", type=Path, help="local JSON Lines with numerical A/B measurements")
    parser.add_argument("--synthetic", action="store_true", help="validate the synthetic comparison fixtures")
    arguments = parser.parse_args()
    cases = SYNTHETIC_CASES if arguments.synthetic else REAL_CASES
    try:
        measurements = load_measurements(arguments.measurements, cases)
        rows = summarize(measurements, cases)
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")
    output_ok = all(row["baseline_different_words"] == row["candidate_different_words"] == 0 for row in rows)
    scratch_ok = all(row["candidate_scratch_dwords_per_group"] <= row["baseline_scratch_dwords_per_group"] for row in rows)
    print(json.dumps({
        "mode": "synthetic-injected-timings" if arguments.synthetic else "measured",
        "baseline_xcl_revision": BASE,
        "candidate_portbridge_patch_revision": PATCH,
        "rounds": 4,
        "samples_per_build_per_round": 20,
        "output_check": "pass" if output_ok else "fail",
        "scratch_nonincrease_check": "pass" if scratch_ok else "fail",
        "results": rows,
    }, allow_nan=False, indent=2))
    return 0 if output_ok and scratch_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
