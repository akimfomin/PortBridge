# SPDX-License-Identifier: MIT
"""Combine disjoint completed cache groups, preserving paired timing order."""

import argparse
from itertools import permutations
import json
from pathlib import Path
from statistics import median


OPERATIONS = ("plain", "blobs", "library")
IDENTITIES = ("same_filename", "fresh_filenames")


def timings(run):
    return {
        "plain": run["plain"]["warm_create_ms"],
        "blobs": run["blobs"]["individual_replay_ms"],
        "library": run["library"]["library_open_ms"] + run["library"]["library_replay_ms"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", type=Path, nargs="+")
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    groups = {}
    binaries = set()
    adapters = set()
    for log in args.logs:
        data = json.loads(log.read_text(encoding="utf-8"))
        binaries.add(data["exe_sha256"])
        for group in data["pairs"]:
            if not all(set(group.get(identity, {})) == set(OPERATIONS) for identity in IDENTITIES):
                continue
            if group["salt"] in groups:
                raise ValueError(f"Two complete groups used salt {group['salt']}")
            for run in (group["seed"], *(group[identity][operation]
                         for identity in IDENTITIES for operation in OPERATIONS)):
                if (run["stage"] != "complete" or run["pipelines"] != 6 or not run["worker_reaped"]
                        or run["root_sha256"] != group["root_sha256"]
                        or run["shader_sha256"] != group["bundle_sha256"]):
                    raise ValueError(f"Invalid worker identity or incomplete measurement in {log}")
                adapters.add((run["adapter_luid"], run["dxgi_driver_version"]))
            groups[group["salt"]] = dict(
                sizes={k: group["seed"][k] for k in ("individual_cache_bytes", "library_bytes")},
                **{identity: {"order": list(group[identity]), "ms": timings(group[identity])}
                   for identity in IDENTITIES},
            )
    if len(groups) != 6 or len(binaries) != 1 or len(adapters) != 1:
        raise ValueError("Expected six complete distinct groups on one binary, adapter and driver")
    expected_orders = set(permutations(OPERATIONS))
    for identity in IDENTITIES:
        if {tuple(group[identity]["order"]) for group in groups.values()} != expected_orders:
            raise ValueError(f"Missing order in {identity}")
    summary = dict(groups=groups, guarded_processes=6 * 7, pipelines_created=6 * 7 * 6)
    for identity in IDENTITIES:
        summary[identity] = {
            "median_ms": {mode: median(g[identity]["ms"][mode] for g in groups.values()) for mode in OPERATIONS},
            "paired_reduction_ms": {
                mode: median(g[identity]["ms"]["plain"] - g[identity]["ms"][mode] for g in groups.values())
                for mode in OPERATIONS[1:]
            },
        }
    args.result.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v["median_ms"] for k, v in summary.items() if k in IDENTITIES}))


if __name__ == "__main__":
    main()
