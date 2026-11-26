# SPDX-License-Identifier: MIT
"""Verify matched SSA projection captures and join timestamps with executable sizes."""
import argparse
import json
import statistics
from pathlib import Path

from summarize import report, stage_stats


def capture(raw, module, result_key, expected_device):
    result = raw[result_key]
    if any(result[key] != value for key, value in expected_device.items()):
        raise ValueError("Mixed physical adapters, driver versions, or subgroup widths")
    if (raw["fragment_sha256"] != module["spirv_sha"]
            or result["fragment_spirv_bytes"] != module["spirv_bytes"]):
        raise ValueError("Measured input differs from the conversion manifest")
    counts = raw["layout"]["structure"]
    if (counts["OpLabel"], counts["OpGroupNonUniformBallot"]) != (module["blocks"], module["ballots"]):
        raise ValueError("Measured control flow differs from the conversion manifest")
    if stage_stats(result, 1)["binary_bytes"] != 768:
        raise ValueError("Vertex stage control differs")
    return stage_stats(result, 16)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", type=Path)
    parser.add_argument("reference_corpus", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    modules = {(m["workload"], m["mode"]): m for m in report(args.experiment / "inputs.json")["modules"]}
    first_draw = report(args.experiment / "draws" / "primary-whole.json")["draw"]
    device = {key: first_draw[key] for key in ("adapter", "vendor_id", "device_id", "driver_version_raw", "subgroup_size")}
    stages = {}
    cameras = {}
    for camera in ("primary", "secondary"):
        reference = report(args.reference_corpus / f"ray800-{camera}" / "scene.json")
        reference_hashes = {v["image"]["sha256"] for pair in reference["pairs"] for v in pair["variants"].values()}
        modes = {}
        for mode in ("whole", "project"):
            raw = report(args.experiment / "draws" / f"{camera}-{mode}.json")
            measured = capture(raw, modules["ray", mode], "draw", device)
            if stages.setdefault(f"ray-{mode}", measured) != measured:
                raise ValueError("Different fragment stage in the two camera captures")
            draw = raw["draw"]
            if (not draw["root_and_readback_guards_intact"] or not draw["capture_statistics"]
                    or (draw["width"], draw["height"], draw["draws_per_interval"]) != (800, 450, 8)):
                raise ValueError("Unexpected image, memory guard or timestamp protocol")
            if (reference_hashes != {raw["output_sha256"]} or raw["references"]["gl"] != reference["gl_image"]["sha256"]
                    or raw["references"]["sgprs"] != reference["sgprs_sha256"]
                    or raw["scene_controls"] != reference["controls"]):
                raise ValueError("Reference image or camera controls differ")
            times = [ticks * draw["timestamp_period_ns"] / (draw["draws_per_interval"] * 1e6) for ticks in draw["gpu_ticks"]]
            if len(times) != 5 or min(times) <= 0:
                raise ValueError("Expected five positive GPU timestamp intervals")
            modes[mode] = {"median_ms": statistics.median(times), "range_ms": [min(times), max(times)]}
            modes["d3d12_vulkan_output_sha256"] = raw["output_sha256"]
        modes["median_time_reduction_fraction"] = 1 - modes["project"]["median_ms"] / modes["whole"]["median_ms"]
        cameras[camera] = modes
    for workload in ("071", "073"):
        for mode in ("whole", "project"):
            raw = report(args.experiment / "physical" / f"{workload}-{mode}.json")
            stages[f"{workload}-{mode}"] = capture(raw, modules[workload, mode], "physical_pipeline", device)
    args.output.write_text(json.dumps({"device": device, "fragment_stages": stages, "cameras": cameras}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
