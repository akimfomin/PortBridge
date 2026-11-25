# SPDX-License-Identifier: MIT
"""Validate the two guarded creation logs and summarize paired QPC differences."""

import csv
from pathlib import Path
import re
from statistics import median
import sys


def read_log(directory, mode):
    path = directory / f"{mode}.log"
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    guard, header, *lines = raw.decode(encoding).splitlines()
    if not guard.startswith("guard=returned reaped=1 child_exit=0 win_error=0 "):
        raise ValueError(f"{path.name}: guarded worker did not return cleanly")
    match = re.search(r"\bqpc_hz=(\d+) size=65536 alignment=65536$", header)
    if not match or "diagnostics=0 " not in header or "hresult=00000000 " not in header or "complete=8 started=8 " not in header:
        raise ValueError(f"{path.name}: missing successful allocation metadata")
    hz = int(match.group(1))
    rows = list(csv.DictReader(lines))
    if len(rows) != 8 or not hz:
        raise ValueError(f"{path.name}: missing sample records")
    samples = []
    for trial in range(1, 5):
        order = ("committed", "placed") if (trial % 2 == 1) == (mode == "measure-ab") else ("placed", "committed")
        arms = {}
        for arm, row in zip(order, rows[2 * trial - 2:2 * trial]):
            heap = int(row["create_heap_ticks"])
            resources = int(row["create_buffers_ticks"])
            total = int(row["create_total_ticks"])
            if (row["trial"], row["arm"], row["buffers_created"], row["bytes_checked"], row["mismatched_words"]) != (
                    str(trial), arm, "16", "1048576", "0"):
                raise ValueError(f"{path.name}: bad parity or ordering in pair {trial}")
            if total != heap + resources or resources <= 0 or (heap > 0) != (arm == "placed"):
                raise ValueError(f"{path.name}: invalid timings in pair {trial}")
            arms[arm] = (total * 1_000_000 / hz, heap * 1_000_000 / hz)
        samples.append((mode, trial, arms["committed"][0], arms["placed"][0], arms["placed"][1]))
    return samples


def main(directory):
    rows = [*read_log(directory, "measure-ab"), *read_log(directory, "measure-ba")]
    print("mode,trial,committed_us,placed_us,placed_heap_us,saved_us")
    for mode, trial, committed, placed, heap in rows:
        print(f"{mode},{trial},{committed:.3f},{placed:.3f},{heap:.3f},{committed - placed:.3f}")
    for label, group in (("all", rows), ("first_pair", [r for r in rows if r[1] == 1]),
                         ("later_pairs", [r for r in rows if r[1] > 1])):
        print(f"paired_medians group={label} pairs={len(group)} committed_us={median(r[2] for r in group):.3f} "
              f"placed_us={median(r[3] for r in group):.3f} heap_us={median(r[4] for r in group):.3f} "
              f"saved_us={median(r[2] - r[3] for r in group):.3f} "
              f"saved_percent={100 * median((r[2] - r[3]) / r[2] for r in group):.3f}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python summarize.py <log-directory>")
    try:
        main(Path(sys.argv[1]))
    except (OSError, KeyError, ValueError) as failure:
        raise SystemExit(str(failure)) from failure
