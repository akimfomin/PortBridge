"""Uncertainty across paired processes for the fixed XCL synthetic corpus."""

import argparse
import json
from math import expm1, log
from pathlib import Path
import random
from statistics import fmean, median, quantiles


def compare(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    rounds = data["rounds"]
    rows = data["cases"]
    logs = []
    cases = []
    for row in rows:
        base = row["samples_ms"]["baseline"]
        compact = row["samples_ms"]["compact"]
        if len(base) != rounds or len(compact) != rounds or min(base + compact) <= 0:
            raise ValueError(f"Incomplete or invalid timings for {row['shape']}")
        paired = [log(candidate / control) for control, candidate in zip(base, compact)]
        logs.append(paired)
        cases.append({"case": row["shape"], "paired_median_percent": 100 * expm1(median(paired))})
    # Preserve all fixtures of a matched process pair when resampling.
    round_effects = [fmean(r) for r in zip(*logs)]
    rng = random.Random(1269)
    bootstrap = [fmean(rng.choices(round_effects, k=rounds)) for _ in range(10000)]
    bounds = quantiles(bootstrap, n=40)
    low, high = bounds[0], bounds[-1]
    return {
        "rounds": rounds,
        "cases": len(cases),
        "fixed_corpus_geometric_percent": 100 * expm1(fmean(round_effects)),
        "paired_process_bootstrap_95_percent": [100 * expm1(low), 100 * expm1(high)],
        "median_case_percent": median(c["paired_median_percent"] for c in cases),
        "case_percent": cases,
        "output_sha256": data["output_sha256"],
        "binary_sha256": data["binary_sha256"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    summary = compare(args.input)
    args.result.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("rounds", "cases", "fixed_corpus_geometric_percent",
                                            "paired_process_bootstrap_95_percent", "median_case_percent")}))


if __name__ == "__main__":
    main()
