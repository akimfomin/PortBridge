"""Verify full control reads and summarize balanced synthetic scratch timings."""

import argparse
from collections import defaultdict
from csv import DictReader
from hashlib import sha256
import json
from pathlib import Path
import re
from statistics import median


SHAPES = {
    32: (32, 4, 3, 110_592),
    64: (64, 4, 8, 1_179_648),
}


def summarize(rows):
    return {
        "pairs": len(rows),
        "scalar_us_median": median(a for _, a, _ in rows),
        "tiled_us_median": median(b for _, _, b in rows),
        "tiled_over_scalar_median": median(b / a for _, a, b in rows),
        "tiled_faster_equal_slower": [sum(test(a, b) for _, a, b in rows)
                                     for test in (lambda a, b: b < a, lambda a, b: b == a,
                                                  lambda a, b: b > a)],
        "scalar_us_range": [min(a for _, a, _ in rows), max(a for _, a, _ in rows)],
        "tiled_us_range": [min(b for _, _, b in rows), max(b for _, _, b in rows)],
    }


def audit(path):
    raw = path.read_bytes()
    lines = raw.decode("utf-8-sig").splitlines()
    guard = re.fullmatch(r"guard=returned reaped=1 peak_job=(\d+) exit=0 error=0", lines[0])
    status = re.fullmatch(r"status=1 debug=(0|1) result=00000000 step= frequency=(\d+)", lines[1])
    if not guard or not 0 < int(guard[1]) <= 512 * 1024**2 or not status or not int(status[2]):
        raise ValueError(f"did not finish cleanly: {path.name}")
    frequency = int(status[2])
    for i, (lanes, (x, y, z, matched)) in enumerate(SHAPES.items(), start=2):
        if lines[i] != f"lanes={lanes} grid={x}x{y}x{z} matched_words_per_arm={matched}":
            raise ValueError(f"incomplete readback: {path.name}")
    raw_cases = defaultdict(list)
    for row in DictReader(lines[4:]):
        lanes, pair = int(row["lanes"]), int(row["pair"])
        arm = "TS" if (pair + list(SHAPES).index(lanes)) % 2 else "ST"
        scalar = int(row["scalar_ticks"]) * 1e6 / frequency
        tiled = int(row["tiled_ticks"]) * 1e6 / frequency
        if row["order"] != arm or not min(scalar, tiled) > 0:
            raise ValueError(f"invalid timing/order: {path.name}: {row}")
        raw_cases[lanes].append((pair, arm, scalar, tiled))
    if (list(raw_cases) != list(SHAPES) or
            any([r[0] for r in case] != list(range(9)) for case in raw_cases.values())):
        raise ValueError(f"missing pairs: {path.name}")
    return sha256(raw).hexdigest(), int(guard[1]), bool(int(status[1])), {
        lane: [row[1:] for row in rows[1:]] for lane, rows in raw_cases.items()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    cohorts = []
    combined = defaultdict(list)
    for log in sorted(args.results.glob("rtx-*.csv")):
        fingerprint, peak, debug, cases = audit(log)
        cohorts.append({"name": log.name, "sha256": fingerprint, "peak_job_bytes": peak,
                        "debug_layer": debug, "cases": {lane: summarize(rows) for lane, rows in cases.items()}})
        for lane, rows in cases.items():
            combined[lane].extend(rows)
    if not cohorts:
        raise ValueError("no successful guarded cohort")
    refusals = [path.read_text(encoding="utf-8-sig").strip()
                for path in sorted(args.results.glob("*-refused.txt"))]
    result = {"cohorts": cohorts, "refusals": refusals,
              "overall": {lane: summarize(rows) for lane, rows in combined.items()}}
    (args.results / "transport-summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["overall"], indent=2))


if __name__ == "__main__":
    main()
