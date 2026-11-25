"""Summarize paired Blender scene timings and validate point snapshots independently."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from statistics import median


def read_run(directory):
    return json.loads((directory / "run.json").read_text(encoding="utf-8"))


def identity(run):
    return tuple(run[key] for key in ("source_sha256", "build", "backend", "device", "driver"))


def verify_points(base, candidate):
    first, second = [read_run(folder) for folder in (base, candidate)]
    if (identity(first) != identity(second) or not all(run["observer"] for run in (first, second))
            or (first["capture_mode"], second["capture_mode"]) != ("cpu", "gpu")):
        raise ValueError("Point checks require both observer arms of the same scene and device")
    first_frames = {row["frame"]: row["points"] for row in first["rows"] if "points" in row}
    second_frames = {row["frame"]: row["points"] for row in second["rows"] if "points" in row}
    if not first_frames or first_frames.keys() != second_frames.keys():
        raise ValueError("Different sampled frames")
    checks = []
    for frame, objects in first_frames.items():
        if objects.keys() != second_frames[frame].keys():
            raise ValueError(f"Different objects at frame {frame}")
        for name, reference in objects.items():
            actual = second_frames[frame][name]
            for directory, snapshot in ((base, reference), (candidate, actual)):
                path = directory / snapshot["positions"]
                if path.parent != directory or path.stat().st_size != 12 * snapshot["count"]:
                    raise ValueError(f"Invalid point artifact: {path}")
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if digest != snapshot["sha256"]:
                    raise ValueError(f"Point digest mismatch: {path}")
            if reference["count"] != actual["count"] or reference["sha256"] != actual["sha256"]:
                raise ValueError(f"Ordered point positions differ at {frame}: {name}")
            checks.append({"frame": frame, "object": name, "points": reference["count"],
                           "sha256": reference["sha256"]})
    if not any(check["points"] for check in checks):
        raise ValueError("Observations contain no points")
    return checks


def mechanism(log):
    upload = re.findall(
        r"Evaluated int32_t field for (\d+) elements on the GPU \((\d+) input buffers?, "
        r"(\d+) values uploaded", log
    )
    read = re.findall(r"Read (\d+) int32_t values from the GPU", log)
    return {"age_dispatches": len(upload),
            "age_element_count": sum(int(elements) for elements, _, _ in upload),
            "age_input_values": sum(int(inputs) for _, _, inputs in upload),
            "age_downloads": len(read), "age_output_values": sum(map(int, read))}


def analyze(root, destination, pair_count):
    if pair_count < 2 or pair_count % 2:
        raise ValueError("Use an even number of pairs to balance run ordering")
    frames_expected = list(range(1, 151))
    expected = identity(read_run(root / "official-1-cpu"))
    records = []
    pairs = []
    for pair in range(1, pair_count + 1):
        totals = {}
        order = ("cpu", "gpu") if pair % 2 else ("gpu", "cpu")
        for arm in order:
            result = read_run(root / f"official-{pair}-{arm}")
            frames = result["rows"]
            if (result["capture_mode"] != arm or result["observer"] or identity(result) != expected
                    or [row["frame"] for row in frames] != frames_expected):
                raise ValueError(f"Wrong run for {pair}/{arm}")
            elapsed = [row["scene_ns"] for row in frames]
            modifiers = [row["modifier_seconds"]["Particles"]["GeometryNodes"] for row in frames]
            if any(not isinstance(ns, int) or ns <= 0 for ns in elapsed):
                raise ValueError("Invalid scene duration")
            records.extend(zip([pair] * len(frames), [arm] * len(frames),
                               frames_expected, elapsed, modifiers))
            totals[arm] = {"all_ms": sum(elapsed) * 1e-6,
                           "frames_21_to_150_ms": sum(elapsed[20:]) * 1e-6}
        pairs.append({"pair": pair, "order": order, **totals,
                      "gpu_over_cpu_pct": 100 * (totals["gpu"]["all_ms"] / totals["cpu"]["all_ms"] - 1)})
    proof_runs = [root / "official-cpu-points", root / "official-gpu-points"]
    if any(identity(read_run(folder)) != expected for folder in proof_runs):
        raise ValueError("Observer runs do not match the timed scene")
    checks = verify_points(*proof_runs)
    cpu, gpu = (mechanism((root / f"official-{arm}-points.log").read_text(encoding="utf-8-sig"))
                for arm in ("cpu", "gpu"))
    if cpu["age_dispatches"] or cpu["age_downloads"] or gpu["age_dispatches"] != 119:
        raise ValueError("Expected the official scene's age capture on each GPU step only")
    if not (gpu["age_dispatches"] == gpu["age_downloads"] and
            gpu["age_input_values"] == gpu["age_element_count"] == gpu["age_output_values"] > 0):
        raise ValueError("Inconsistent age capture and download counts")
    summary = {
        "device": dict(zip(("source_sha256", "build", "backend", "device", "driver"), expected)),
        "pairs": pairs,
        "timed_scene_frames": len(records),
        "cpu_median_full_scene_loop_ms": median(pair["cpu"]["all_ms"] for pair in pairs),
        "gpu_median_full_scene_loop_ms": median(pair["gpu"]["all_ms"] for pair in pairs),
        "paired_gpu_over_cpu_pct": median(pair["gpu_over_cpu_pct"] for pair in pairs),
        "point_observations": checks,
        "diagnostic_mechanism": {"cpu": cpu, "gpu": gpu},
    }
    destination.mkdir(parents=True, exist_ok=False)
    with (destination / "scene_timing.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("pair", "capture", "frame", "scene_ns", "modifier_seconds"))
        writer.writerows(records)
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--pairs", type=int, default=6)
    args = parser.parse_args()
    summary = analyze(args.run_root, args.destination, args.pairs)
    print(json.dumps({key: value for key, value in summary.items() if key != "pairs"}, indent=2))
