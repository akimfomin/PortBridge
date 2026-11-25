"""Verify paired frame checksums and summarize benchmark durations."""

import argparse
import csv
import json
from pathlib import Path
from statistics import median


def summarize(document, csv_path):
    rows = document["rows"]
    pairs = {}
    image_hashes = {}
    for row in rows:
        frame = (row["threshold"], row["view"])
        if row["sha256"] != image_hashes.setdefault(frame, row["sha256"]):
            raise ValueError(f"Frame outputs diverge at {frame}")
        trial = pairs.setdefault((row["block"], *frame), {})
        mode = row["mode"]
        if mode in trial:
            raise ValueError(f"Duplicate trial for {frame} and {mode}")
        if sum(row[key] for key in ("edit_ns", "draw_ns", "read_ns")) != row["total_ns"]:
            raise ValueError("Successive elapsed intervals do not sum")
        trial[mode] = row["total_ns"]
    modes = sorted(pairs[next(iter(pairs))])
    if any(sorted(trial) != modes for trial in pairs.values()):
        raise ValueError("Pairs cover different modes")
    if "fused" not in modes or len(set(image_hashes.values())) != 12:
        raise ValueError("Expected three views by four different edits")
    with csv_path.open("x", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    samples = {
        mode: {
            "median_ms": median(trial[mode] for trial in pairs.values()) / 1e6,
            "fused_paired_saving_pct": 100 * median(
                1 - trial["fused"] / trial[mode] for trial in pairs.values()
            ),
            "fused_faster_pairs": sum(trial["fused"] < trial[mode] for trial in pairs.values()),
        }
        for mode in modes
    }
    return {**{k: v for k, v in document.items() if k != "rows"},
            "completion": document.get("completion", "image"), "frames": len(rows),
            "unique_images": len(image_hashes), "pairs": len(pairs), "modes": samples}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("runs", type=Path, nargs="+")
    options = parser.parse_args()
    options.destination.mkdir(parents=True, exist_ok=True)
    answer = {}
    for path in options.runs:
        name = path.parent.name
        if name in answer:
            raise ValueError(f"Duplicate experiment name {name}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        answer[name] = summarize(payload, options.destination / f"{name}.csv")
    with (options.destination / "summary.json").open("x", encoding="utf-8") as output:
        json.dump(answer, output, indent=2)
        output.write("\n")
