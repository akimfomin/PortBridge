"""Check the raw order-balanced detile measurements."""

from collections import Counter, defaultdict
from csv import DictReader
from hashlib import sha256
import json
from pathlib import Path
from statistics import median


DATA = Path(__file__).resolve().parent / "prepared"
CASES = {"rgba8-512-S": 1048576, "rgba8-1024-D": 4194304,
         "bc7-1024-D": 1048576, "bc7-2048-S": 4194304}
STEPS = ("full", "tile", "checked")


def collect(glob):
    cases = defaultdict(list)
    hashes = {}
    for log in sorted(DATA.glob(glob)):
        rows = defaultdict(list)
        hashes[log.name] = sha256(log.read_bytes()).hexdigest()
        with log.open(encoding="utf-8-sig", newline="") as source:
            for sample in DictReader(source):
                name = sample["case"]
                pair = int(sample["pair"])
                if int(sample["texture_bytes"]) != CASES[name]:
                    raise ValueError("subresource dimensions changed")
                delta = 1 if pair % 2 == 0 else 2
                begin = (list(CASES).index(name) + pair) % 3
                order = "-".join(STEPS[(begin + delta * n) % 3] for n in range(3))
                if order != sample["order"]:
                    raise ValueError("wrong timing order")
                times = [int(sample[k]) for k in ("full_ns", "tile_ns", "checked_tile_ns")]
                if min(times) <= 0:
                    raise ValueError("missing interval")
                rows[name].append((pair, order, times))
        if list(rows) != list(CASES) or any([r[0] for r in group] != list(range(13)) for group in rows.values()):
            raise ValueError(f"not a complete cohort: {log.name}")
        for case, group in rows.items():
            cases[case].extend(group[1:])
    if not hashes:
        raise ValueError(f"no results found for {glob}")
    return {
        "raw_sha256": hashes,
        "cases": {
            case: {
                "pairs": len(group),
                "orders": dict(Counter(row[1] for row in group)),
                "median_us": [median(row[2][i] for row in group) / 1000 for i in range(3)],
                "checked_faster": sum(row[2][2] < row[2][0] for row in group),
            }
            for case, group in cases.items()
        },
    }


if __name__ == "__main__":
    result = {"main": collect("cpu-*.csv"), "pr_2026": collect("next-*.csv")}
    (DATA / "cpu-summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for branch, values in result.items():
        for case, metrics in values["cases"].items():
            print(branch, case, *metrics["median_us"], metrics["checked_faster"], "/", metrics["pairs"])
