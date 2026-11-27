"""Summarize a single, already clipped VIctory heap-profile log locally."""
import argparse
import json
from pathlib import Path
import re
from statistics import median


_NUMBER = r"(\d+(?:\.\d+)?)"
_FRAME = re.compile(
    rf"{_NUMBER} ms/frame \([^\r\n]*\), (\d+) draws/frame,\s+dropped (\d+) without a host pipeline"
)
_PHASES = re.compile(
    rf"indexed texture CPU phases per frame, all threads: {_NUMBER} ms queue upkeep,\s*"
    rf"{_NUMBER} ms due selection and accounting,\s*{_NUMBER} ms slot processing"
)
_QUEUE = re.compile(r"textures picked by index, the queue: (\d+) slots, (\d+) of them due")


def summarize(lines):
    def collect(pattern):
        return [[] for _ in range(pattern.groups)]

    frames, phases, queue = (_FRAME, _PHASES, _QUEUE)
    samples = {pattern: collect(pattern) for pattern in (frames, phases, queue)}
    for line in lines:
        for pattern, columns in samples.items():
            match = pattern.search(line)
            if match:
                for column, value in zip(columns, match.groups(), strict=True):
                    column.append(float(value))

    frame_ms, draws, dropped = samples[frames]
    upkeep_ms, selection_ms, slot_ms = samples[phases]
    _, due = samples[queue]
    if min(len(frame_ms), len(slot_ms)) < 3:
        raise ValueError("need at least three frame summaries and three indexed texture CPU phase rows in each clipped log")
    return {
        "frame_summary_rows": len(frame_ms),
        "profile_rows": len(slot_ms),
        "frame_ms_median": median(frame_ms),
        "draws_per_frame_median": median(draws),
        "dropped_per_frame_median": median(dropped),
        "upkeep_ms_per_frame_median": median(upkeep_ms),
        "selection_ms_per_frame_median": median(selection_ms),
        "slot_ms_per_frame_median": median(slot_ms),
        "queue_rows": len(due),
        "queue_due_median": median(due) if due else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path, help="UTF-8 log clipped to the reference driving interval")
    parser.add_argument("candidate", type=Path, help="UTF-8 log clipped to the same driving interval")
    args = parser.parse_args()
    reports = {}
    for label, path in (("reference", args.reference), ("candidate", args.candidate)):
        try:
            with path.open(encoding="utf-8-sig") as lines:
                reports[label] = summarize(lines)
        except (OSError, ValueError) as error:
            parser.exit(2, f"{label}: {error}\n")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
