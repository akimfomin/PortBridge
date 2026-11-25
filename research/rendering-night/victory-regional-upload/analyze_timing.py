"""Verify and summarize the D3D12 regional texture timestamp batches."""

from collections import defaultdict
from csv import DictReader
from hashlib import sha256
import json
from pathlib import Path
import re
from statistics import median


ROOT = Path(__file__).resolve().parent
CASES = {
    "one-tile": (1, 65_536),
    "four-adjacent": (1, 262_144),
    "four-separated": (4, 262_144),
    "eight-separated": (8, 524_288),
}


def audit(path):
    raw = path.read_bytes()
    lines = raw.decode("utf-8-sig").splitlines()
    if not lines:
        raise ValueError(f"{path.name} has no worker receipt")
    receipt = {
        "log": path.name,
        "sha256": sha256(raw).hexdigest(),
        "guard": lines[0],
    }
    if lines[0] == "guard=admission_refused reaped=0 peak_job=0 exit=0 error=0":
        if len(lines) != 1:
            raise ValueError(f"{path.name} has extra output after an admission refusal")
        return receipt, {}
    guard = re.fullmatch(r"guard=returned reaped=1 peak_job=(\d+) exit=0 error=0", lines[0])
    if not guard or not 0 < int(guard[1]) <= 512 * 1024**2 or len(lines) < 3:
        raise ValueError(f"{path.name} lost the worker or returned a partial result")
    status = re.fullmatch(r"status=1 result=00000000 step= frequency=(\d+)", lines[1])
    if not status or not int(status[1]):
        raise ValueError(f"{path.name} device or tick frequency did not validate")
    frequency = int(status[1])
    rows = defaultdict(list)
    for row in DictReader(lines[2:]):
        case = row["case"]
        pair = int(row["pair"])
        order = "RF" if (list(CASES).index(case) + pair) % 2 else "FR"
        geometry = (int(row["boxes"]), int(row["regional_bytes"]))
        if order != row["order"] or geometry != CASES[case] or int(row["matched_bytes"]) != 1_048_576:
            raise ValueError(f"geometry, order or readback mismatch in {path.name}: {row}")
        a, b = (int(row[k]) / frequency * 1e6 for k in ("full_ticks", "region_ticks"))
        if min(a, b) <= 0:
            raise ValueError(f"nonpositive interval in {path.name}: {row}")
        rows[case].append((pair, order, a, b))
    if list(rows) != list(CASES):
        raise ValueError(f"missing or unexpected cases in {path.name}")
    for case_rows in rows.values():
        if [r[0] for r in case_rows] != list(range(13)):
            raise ValueError(f"missing pairs in {path.name}")
    receipt["frequency_hz"] = frequency
    return receipt, {name: times[1:] for name, times in rows.items()}


def metrics(samples):
    return {
        "pairs": len(samples),
        "regional_faster_pairs": sum(r[3] < r[2] for r in samples),
        "full_us": median(r[2] for r in samples),
        "regional_us": median(r[3] for r in samples),
        "regional_over_full": median(r[3] / r[2] for r in samples),
    }


def main():
    cohorts = []
    data = {name: [] for name in CASES}
    for path in sorted(ROOT.glob("timestamp-rtx-*.csv")):
        receipt, rows = audit(path)
        if rows:
            receipt["cases"] = {case: metrics(samples) for case, samples in rows.items()}
        cohorts.append(receipt)
        for case, samples in rows.items():
            data[case].extend(samples)
    report = {
        "completed": sum(bool(cohort.get("cases")) for cohort in cohorts),
        "cohorts": cohorts,
        "cases": {
            case: {"regions": CASES[case][0], "regional_bytes": CASES[case][1],
                   "overall": metrics(samples),
                   "order": {order: metrics([r for r in samples if r[1] == order])
                             for order in ("FR", "RF")}}
            for case, samples in data.items() if samples
        },
    }
    (ROOT / "timestamp-summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["cases"], indent=2))


if __name__ == "__main__":
    main()
