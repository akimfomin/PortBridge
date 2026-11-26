# SPDX-License-Identifier: MIT
"""Recompute coverage and the interaction between pending XCL compiler changes."""
import argparse
import gzip
import json
from pathlib import Path


def load(path):
    data = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    return json.loads(data)


def validated(census):
    return {(r["group"], r["id"]): r for r in census["rows"]
            if r.get("variants") and all("error" not in v for v in r["variants"].values())}


def changed(row):
    variants = row["variants"]
    return variants["project"]["dxil_sha256"] != variants["whole"]["dxil_sha256"]


def compare(left, right):
    a, b = validated(left), validated(right)
    if set(a) != set(b):
        raise ValueError("The comparison has different validated shader entries")
    deltas = []
    for key, first in a.items():
        second = b[key]
        if first["rdna"]["sha256"] != second["rdna"]["sha256"] or first["source_sha256"] != second["source_sha256"]:
            raise ValueError(f"Source or PAL input changed for {key}")
        before, after = first["variants"], second["variants"]
        if any(before[mode]["dxil_sha256"] != after[mode]["dxil_sha256"] for mode in ("whole", "project")):
            deltas.append({"group": key[0], "id": key[1], "source": first["source"],
                           "before_bytes": {mode: before[mode]["dxil_bytes"] for mode in ("whole", "project")},
                           "after_bytes": {mode: after[mode]["dxil_bytes"] for mode in ("whole", "project")}})
    entries = list(b.values())
    unique = {}
    for entry in entries:
        unique.setdefault(entry["rdna"]["sha256"], set()).add(changed(entry))
    if any(len(decisions) != 1 for decisions in unique.values()):
        raise ValueError("An identical PAL input has inconsistent projection acceptance")
    counts = {"attempted": len(right["rows"]), "validated": len(entries), "projection_changed": sum(map(changed, entries)),
              "unique_pal": len(unique), "changed_unique_pal": sum(True in decisions for decisions in unique.values()),
              "ballot_count_changes": sum(r["variants"]["project"]["ballots"] != r["variants"]["whole"]["ballots"] for r in entries),
              "dxil_growth": sum(r["variants"]["project"]["dxil_bytes"] > r["variants"]["whole"]["dxil_bytes"] for r in entries)}
    return counts, deltas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("stock_census", type=Path, help="Matching independent clean-main projection census, JSON or gzip")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = {}
    for label in ("paired", "fixed-mini"):
        first = load(args.directory / f"{label}-2501-2503.json.gz")
        second = load(args.directory / f"{label}-2501-2503-2557.json.gz")
        counts, deltas = compare(first, second)
        report[label] = {"new_stack": counts, "changes_from_known_bits": deltas}
        if label == "paired":
            stock = load(args.stock_census)
            compare(stock, first)
            initial, stacked = validated(stock), validated(first)
            report[label]["whole_changed_from_stock"] = sum(
                stacked[key]["variants"]["whole"]["dxil_sha256"] != row["variants"]["whole"]["dxil_sha256"]
                for key, row in initial.items())
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
