# SPDX-License-Identifier: MIT
"""Validate and summarize matched RTX D3D12 pipeline and scene receipts."""
import argparse
import json
from pathlib import Path
from statistics import median


def summarize(root):
    counter = json.loads((root / "native-identity.json").read_bytes())
    samples = [json.loads(line) for line in (root / "native-samples.jsonl").read_bytes().splitlines()]
    if len(samples) != 24 or len({(r["id"], r["arm"], r["block"]) for r in samples}) != 24:
        raise ValueError("incomplete counterbalanced PSO series")
    if any(r["guard_exit"] != 0 or "error" in r for r in samples):
        raise ValueError("incomplete process receipt")
    native = {}
    for case in counter["cases"]:
        name = case["id"]
        native[name] = {}
        for arm in ("whole", "project"):
            rows = sorted((r for r in samples if (r["id"], r["arm"]) == (name, arm)), key=lambda r:r["block"])
            assert [r["block"] for r in rows] == [0, 1, 2, 3]
            assert len({r["dxil_bytes"] for r in rows}) == len({r["opaque_cache_bytes"] for r in rows}) == 1
            native[name][arm] = {
                "dxil_bytes": rows[0]["dxil_bytes"],
                "opaque_cache_bytes": rows[0]["opaque_cache_bytes"],
                "native_create_ms": [r["native_create_ms"] for r in rows],
                "median_native_ms": median(r["native_create_ms"] for r in rows),
                "median_peak_process_mib": median(r["job_peak_process_bytes"] / 2**20 for r in rows),
                "median_process_private_create_delta_mib": median(
                    (r["memory"]["after_create"]["private_bytes"] - r["memory"]["before_create"]["private_bytes"]) / 2**20
                    for r in rows),
                "median_dxgi_local_create_delta_mib": median(
                    (r["memory"]["after_create"]["local_bytes"] - r["memory"]["before_create"]["local_bytes"]) / 2**20
                    for r in rows),
                "median_dxgi_nonlocal_create_delta_mib": median(
                    (r["memory"]["after_create"]["nonlocal_bytes"] - r["memory"]["before_create"]["nonlocal_bytes"]) / 2**20
                    for r in rows),
            }
    warm = {}
    for family in ("clean", "drafts"):
        rows = json.loads((root / f"warm-draws-{family}.json").read_bytes())
        assert len(rows) == len({(r["view"],r["arm"],r["block"]) for r in rows}) == 8
        assert all(r["complete"] and r["guard_exit"] == 0 for r in rows)
        warm[family] = {}
        for view in ("primary", "secondary"):
            same = [r for r in rows if r["view"] == view]
            assert len({r["raw_sha256"] for r in same}) == 1
            warm[family][view] = {"rgba32f_sha256":same[0]["raw_sha256"]}
            for arm in ("whole","project"):
                times = [r["gpu_ms_per_draw"] for r in same if r["arm"] == arm]
                assert len(times) == 2
                warm[family][view][arm] = {"batch_means_ms":times,"median_ms":median(times)}
    for view in ("primary","secondary"):
        assert warm["clean"][view]["rgba32f_sha256"] == warm["drafts"][view]["rgba32f_sha256"]
    return {"native":native, "warm":warm}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt_directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.receipt_directory), indent=2))
