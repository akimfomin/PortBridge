# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarize complete paired results, leaving raw timing and outliers intact."""

import argparse
import csv
import json
import statistics
from pathlib import Path


PLAN = {"dense": (16, 1, 1048576, 1048576),
        "overlap": (3, 1, 114688, 98304),
        "sparse": (16, 16, 1048576, 1048576)}


def parse(path):
    guard, status, *lines = path.read_text(encoding="utf-8-sig").splitlines()
    raw = dict(part.split("=", 1) for part in guard.split())
    if raw.get("guard") != "returned" or raw.get("reaped") != "1" or raw.get("exit") != "0":
        raise ValueError(f"worker did not return and reap: {path}")
    value = dict(part.split("=", 1) for part in status.split())
    if value.get("status") != "1" or value.get("code") != "00000000" or value.get("windows") != "54":
        raise ValueError(f"worker verification incomplete: {path}")
    if int(value["checked_bytes"]) != 54 * (1048576 + 512):
        raise ValueError(f"incorrect checked byte total: {path}")
    polarity = value["polarity"]
    frequency = int(value["frequency"])
    if polarity not in ("a", "b") or frequency <= 0:
        raise ValueError(f"invalid run metadata: {path}")
    rows = list(csv.DictReader(lines))
    locations = set()
    metrics = {name: [] for name in PLAN}
    for i, name in enumerate(PLAN):
        shape = [r for r in rows if r["case"] == name]
        if [int(r["pair"]) for r in shape] != list(range(9)):
            raise ValueError(f"incomplete pairs for {name}: {path}")
        for r in shape:
            pair = int(r["pair"])
            first = "PS" if (i + pair + (polarity == "b")) % 2 else "SP"
            if r["order"] != first:
                raise ValueError(f"unbalanced run order: {path}")
            plan = tuple(int(r[k]) for k in ("stock_commands", "packed_commands", "stock_bytes", "packed_bytes"))
            if plan != PLAN[name]:
                raise ValueError(f"plan changed for {name}: {path}")
            a, b = int(r["stock_slot"]), int(r["packed_slot"])
            if a == b or a in locations or b in locations:
                raise ValueError(f"output window reused: {path}")
            locations.update((a, b))
            if pair:
                cpua, cpub = (int(r[f"{arm}_cpu_ns"]) for arm in ("stock", "packed"))
                gpua, gpub = (int(r[f"{arm}_gpu_ticks"]) * 1e6 / frequency for arm in ("stock", "packed"))
                metrics[name].append((cpua, cpub, gpua, gpub))
    if len(rows) != 27 or locations != set(range(54)):
        raise ValueError(f"unexpected result shape: {path}")
    return polarity, frequency, int(raw["peak_job"]), metrics


def summary(rows):
    a, b, g, h = zip(*rows, strict=True)
    med = statistics.median
    return dict(pairs=len(rows), baseline_cpu_ns=med(a), packed_cpu_ns=med(b),
                paired_cpu_ns=med(x - y for x, y in zip(a, b, strict=True)),
                baseline_gpu_us=med(g), packed_gpu_us=med(h),
                paired_gpu_us=med(x - y for x, y in zip(g, h, strict=True)),
                cpu_packed_faster=sum(y < x for x, y in zip(a, b, strict=True)),
                gpu_packed_faster=sum(y < x for x, y in zip(g, h, strict=True)))


def main():
    argp = argparse.ArgumentParser()
    argp.add_argument("results", type=Path, nargs="+")
    args = argp.parse_args()
    runs = {}
    pooled = {name: [] for name in PLAN}
    for path in args.results:
        name, freq, peak, metrics = parse(path)
        if name in runs:
            raise ValueError(f"duplicate polarity: {name}")
        runs[name] = dict(frequency=freq, peak_job_bytes=peak, cases={k: summary(v) for k, v in metrics.items()})
        for case, samples in metrics.items():
            pooled[case].extend(samples)
    print(json.dumps(dict(runs=runs, pooled={k: summary(v) for k, v in pooled.items()}), indent=2))


if __name__ == "__main__":
    main()
