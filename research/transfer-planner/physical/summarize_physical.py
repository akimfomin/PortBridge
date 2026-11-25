#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Summarize checked, paired Vulkan CSV and D3D12 JSON benchmark replays."""

import argparse
import csv
import gzip
import json
import math
from pathlib import Path
from statistics import median

STRATEGIES = ("exact", "greedy", "optimal")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def samples_valid(samples):
    return bool(samples) and all(
        all(math.isfinite(number) and number >= 0 for number in sample)
        and sample[0] > 0 and sum(sample[1:]) <= sample[0] + 0.3
        for sample in samples
    )


def names_valid(plans):
    return set(plans) == set(STRATEGIES)


def open_text(path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open(encoding="utf-8-sig", newline="")


def from_vulkan(path):
    with open_text(path) as source:
        adapter = next(source).rstrip()
        allocation = dict(item.split("=") for item in next(source).split())
        canary = next(source).rstrip()
        mode = dict(item.split("=") for item in next(source).split())
        require(adapter.startswith("device=NVIDIA GeForce RTX 4070 Ti SUPER type=DISCRETE_GPU "),
                "expected RTX 4070 Ti SUPER Vulkan device")
        require(int(allocation["target_flags"]) & 3 == 1,
                "Vulkan target must be device-local and non-host-visible")
        require(canary == "negative_control=detected forbidden upload",
                "missing Vulkan forbidden-copy canary")
        require(mode["mode"] == "traced_upload_and_compute" and int(mode["atom_bytes"]) == 64
                and int(mode["cost_unit"]) == 1, "unexpected Vulkan replay mode")
        repeat_count = int(mode["repeats"])
        frame_limit = int(mode["frame_limit"])
        cases = {}
        for row in csv.DictReader(source):
            case_frames = int(row["case_frames"])
            case = cases.setdefault(row["case"], (case_frames, {}))
            require(case[0] == case_frames, "inconsistent Vulkan case count")
            frame = int(row["frame_index"]), int(row["frame_id"])
            dirty = int(row["dirty_atoms"])
            epoch = case[1].setdefault(frame, (dirty, {}))
            require(epoch[0] == dirty, "inconsistent Vulkan dirty count")
            stats = tuple(int(row[key]) for key in ("regions", "copied_bytes", "modeled_cost"))
            plan = epoch[1].setdefault(row["strategy"], (stats, []))
            require(plan[0] == stats and int(row["sample"]) == len(plan[1]),
                    "inconsistent Vulkan plan or duplicate sample")
            plan[1].append(tuple(float(row[key]) / 1000 for key in
                                 ("total_ns", "plan_ns", "stage_ns")))
    for case_frames, frames in cases.values():
        require(len(frames) == min(frame_limit, case_frames), "incomplete Vulkan data")
        for _, plans in frames.values():
            require(names_valid(plans), "missing Vulkan strategy")
            require(all(len(samples) == repeat_count for _, samples in plans.values()),
                    "missing Vulkan sample")
    return int(mode["cost_setup"]), cases


def from_d3d12(path):
    with open_text(path) as source:
        report = json.load(source)
    require(report["backend"] == "D3D12" and report["adapter"] == "NVIDIA GeForce RTX 4070 Ti SUPER"
            and report["software"] is False and report["bytes_per_atom"] == 64
            and report["single_submission"] is True, "unexpected physical D3D12 replay mode")
    require(report["sample_columns_us"][:3] == ["plan_to_consumer_fence", "plan", "stage"],
            "unexpected D3D12 timing columns")
    repeat_count = report["samples_per_strategy"]
    cases = {}
    for case in report["cases"]:
        frames = {}
        require(case["name"] not in cases, "duplicate D3D12 case")
        for epoch in case["epochs"]:
            frame = epoch["index"], epoch["frame"]
            require(frame not in frames and epoch["verified"] is True, "duplicate or unverified D3D12 epoch")
            plans = {}
            for plan in epoch["plans"]:
                name = plan["strategy"]
                require(name not in plans and len(plan["samples"]) == repeat_count,
                        "duplicate or incomplete D3D12 plan")
                stats = plan["regions"], plan["copied_bytes"], plan["model_score"]
                plans[name] = (stats, [tuple(sample[:3]) for sample in plan["samples"]])
            require(names_valid(plans), "missing D3D12 strategy")
            frames[frame] = epoch["dirty_atoms"], plans
        require(len(frames) == case["selected_frames"], "incomplete D3D12 data")
        cases[case["name"]] = case["available_frames"], frames
    return report["setup_units"], cases


def parse(path):
    input_path = path.with_suffix("") if path.suffix == ".gz" else path
    if input_path.suffix.lower() == ".csv":
        backend, parsed = "Vulkan", from_vulkan(path)
    else:
        backend, parsed = "D3D12", from_d3d12(path)
    setup, cases = parsed
    require(cases, "missing cases")
    for _, frames in cases.values():
        require(frames and all(samples_valid(samples)
                               for _, plans in frames.values() for _, samples in plans.values()),
                "missing or invalid timing samples")
    return backend, setup, cases


def signature(cases):
    return {name: (total, {frame: (dirty, {key: stats for key, (stats, _) in plans.items()})
                           for frame, (dirty, plans) in frames.items()})
            for name, (total, frames) in cases.items()}


def summary(cases):
    result = {}
    for name, (available, frames) in cases.items():
        strategy_result = {}
        for strategy in STRATEGIES:
            plans = [plans[strategy] for _, plans in frames.values()]
            wall = sorted(sample[0] for _, samples in plans for sample in samples)
            stage = [sample[2] for _, samples in plans for sample in samples]
            planning = [sample[1] for _, samples in plans for sample in samples]
            strategy_result[strategy] = {
                "timed_chains": len(wall),
                "chain_p50_us": round(median(wall), 3),
                "chain_p95_us": round(wall[math.ceil(len(wall) * 0.95) - 1], 3),
                "epoch_median_chain_sum_us": sum(median(row[0] for row in samples) for _, samples in plans),
                "plan_p50_us": round(median(planning), 3),
                "stage_p50_us": round(median(stage), 3),
                "copied_bytes_across_selected_epochs": sum(stats[1] for stats, _ in plans),
                "regions_across_selected_epochs": sum(stats[0] for stats, _ in plans),
                "model_score_across_selected_epochs": sum(stats[2] for stats, _ in plans),
            }
        optimal = strategy_result["optimal"]["epoch_median_chain_sum_us"]
        relative = {
            strategy: round(100 * (optimal / strategy_result[strategy]["epoch_median_chain_sum_us"] - 1), 3)
            for strategy in STRATEGIES[:2]
        }
        result[name] = {
            "available": available, "selected": len(frames),
            "selected_active": sum(dirty > 0 for dirty, _ in frames.values()),
            "optimal_chain_pct_vs_baseline": relative,
            "strategies": strategy_result,
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    outputs = {}
    first = None
    for path in args.paths:
        backend, setup, cases = parse(path)
        current = setup, signature(cases)
        if first is None:
            first = current
        require(first == current, f"{path.name} used unequal frames or copy plans")
        outputs.setdefault(backend, []).append({"file": path.name.removesuffix(".gz"), "cases": summary(cases)})
    print(json.dumps({"cost_setup": first[0], "matched_epoch_and_plan_signatures": True,
                      "runs_by_backend": outputs}, indent=2))


if __name__ == "__main__":
    main()
