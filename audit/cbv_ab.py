"""Summarize six alternating CBV runs from a single PresentMon process/swapchain."""
import argparse
import csv
import json
import math
from pathlib import Path
import re
from statistics import median


FIELDS = ("hits", "misses", "bytes_avoided", "invalidated")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
COUNTER = re.compile(r"\b(" + "|".join(FIELDS) + r")=(\d+)\b")


def summarize(path, enabled):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        if not rows.fieldnames or "MsBetweenPresents" not in rows.fieldnames:
            raise ValueError(f"{path}: need PresentMon MsBetweenPresents")
        frames = [float(row["MsBetweenPresents"]) for row in rows]
    if len(frames) < 100 or any(not math.isfinite(x) or x <= 0 for x in frames):
        raise ValueError(f"{path}: need at least 100 positive frame intervals from the measured window")
    frames.sort()
    tail = frames[-math.ceil(len(frames) / 100):]
    report = {"frames": len(frames), "seconds": round(sum(frames) / 1000, 2),
              "median_ms": round(median(frames), 3), "p95_ms": round(frames[math.ceil(len(frames) * .95) - 1], 3),
              "one_percent_low_fps": round(1000 / (sum(tail) / len(tail)), 3),
              "frames_over_50ms": sum(value > 50 for value in frames)}
    if enabled:
        windows = [dict(COUNTER.findall(ANSI.sub("", line)))
                   for line in path.with_suffix(".log").read_text(encoding="utf-8").splitlines()
                   if "CBV snapshots since last frame report" in line]
        if not windows or any(row.keys() != set(FIELDS) for row in windows):
            raise ValueError(f"{path}: need complete CBV diagnostic lines from the measured window")
        counts = {key: sum(int(row[key]) for row in windows) for key in FIELDS}
        eligible = counts["hits"] + counts["misses"]
        report["eligible_reuse_percent"] = round(100 * counts["hits"] / eligible, 2) if eligible else None
        report["cbv_counts"] = counts
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs=6, metavar="CSV", help="ordered OFF ON OFF ON OFF ON")
    args = parser.parse_args()
    if len(set(p.resolve() for p in args.runs)) != 6:
        parser.error("Use six separate captures")
    reports = []
    try:
        for index, path in enumerate(args.runs):
            enabled = bool(index % 2)
            reports.append({"run": index + 1, "reuse": enabled, **summarize(path, enabled)})
    except (OSError, ValueError) as exc:
        parser.exit(2, str(exc) + "\n")
    pairs = [round(reports[i + 1]["median_ms"] - reports[i]["median_ms"], 3) for i in range(0, 6, 2)]
    print(json.dumps({"runs": reports, "paired_median_on_minus_off_ms": pairs}, indent=2))


if __name__ == "__main__":
    main()
