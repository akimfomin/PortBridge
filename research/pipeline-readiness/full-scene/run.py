"""Build, measure, and verify complete-frame Vulkan pipeline readiness."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from statistics import median
import subprocess
from time import monotonic

from PIL import Image
from prepare import compile_shader, digest


ROOT = Path(__file__).resolve().parent
SIZE = (1024, 768)
MODES = ("shared", "reserved", "critical-first", "warm")
ORDERS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))
METRICS = ("demand_ms", "startup_to_frame_ms", "schedule_to_drained_ms",
           "schedule_to_all_frames_ms", "process_commit_before", "process_commit_at_frame",
           "process_commit_sampled_peak", "lifetime_peak_commit", "lifetime_peak_working_set")


def artifact_hash(path):
    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()


def build(output, clang, dlltool, headers):
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / "scene.cpp"
    symbols = sorted(set(re.findall(r"\b(vk[A-Z]\w+)\(", source.read_text(encoding="utf-8"))))
    exports = output / "vulkan.def"
    link = output / "vulkan.a"
    exports.write_text("LIBRARY vulkan-1.dll\nEXPORTS\n" + "\n".join(symbols) + "\n", encoding="ascii")
    subprocess.run([dlltool, "-m", "i386:x86-64", "-d", exports, "-l", link], check=True, timeout=30)
    subprocess.run([clang, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror", "-static", "-I", headers,
                    source, link, "-lpsapi", "-o", output / "scene.exe"], check=True, timeout=45)


def verify(value, mode, manifest):
    jobs = value["jobs"]
    if (value["mode"] != mode or value["draws_per_frame"] != manifest["draws"] or
            value["triangles_per_frame"] != manifest["indexed_triangles"] or
            not 0 < value["demand_ms"] <= value["startup_to_frame_ms"] or
            not 0 < value["schedule_to_drained_ms"] <= value["schedule_to_all_frames_ms"] or
            value["process_commit_sampled_peak"] < value["process_commit_before"] or
            value["lifetime_peak_commit"] < value["process_commit_sampled_peak"] or
            len(jobs) != 6 or len(value["nonclear_pixels"]) != 3):
        raise ValueError("Unexpected draw, timeline, or memory contract")
    expected = 0 if mode == "warm" else 1000297000
    for index, job in enumerate(jobs):
        if (job["id"] != index or job["preflight"] != expected or not job["feedback_flags"] & 1 or
                bool(job["feedback_flags"] & 2) != (mode == "warm") or
                not job["start_ms"] < job["return_ms"] or job["feedback_ns"] <= 0):
            raise ValueError("Unexpected cache classification, feedback, or timing")
    active = sum(job["start_ms"] <= 0 < job["return_ms"] for job in jobs if job["id"] not in (0, 3))
    if active != value["active_at_demand"]:
        raise ValueError("Incorrect overlap calculation")


def run(folder, executable, scene_dir, adapter, dxc, validator, campaign, groups):
    if any(name.startswith(("VK_LOADER_", "VK_DRIVER_", "VK_LAYER_")) or name in
           ("VK_ICD_FILENAMES", "VK_INSTANCE_LAYERS", "VK_ADD_DRIVER_FILES") for name in os.environ):
        raise ValueError("Inherited Vulkan loader overrides must be cleared for the isolated run")
    scene_path = scene_dir / "scene.bin"
    manifest = json.loads((scene_dir / "scene-manifest.json").read_text(encoding="utf-8"))
    if artifact_hash(scene_path) != manifest["scene_sha256"]:
        raise ValueError("Scene manifest mismatch")
    folder.mkdir(exist_ok=False)
    arms = []
    for block in range(groups):
        for index in ORDERS[block % len(ORDERS)]:
            mode = MODES[index]
            directory = folder / f"{block}-{mode}"
            shaders = directory / "shaders"
            const = 1000 * campaign + 10 * block + index + 1
            compile_shader(shaders, dxc, validator, const)
            arms.append((block, mode, directory, shaders, const))
    if len(set(artifact_hash(s / "ps.spv") for _, _, _, s, _ in arms)) != len(arms):
        raise ValueError("Fragment SPIR-V cache keys were not distinct")

    done, reference = [], None
    config = {"exe": artifact_hash(executable), "scene": manifest["scene_sha256"],
              "vs_ps_hlsl": artifact_hash(ROOT / "scene.hlsl"),
              "dxc": artifact_hash(dxc), "spirv_validator": artifact_hash(validator),
              "campaign": campaign, "adapter": adapter, "width": SIZE[0], "height": SIZE[1]}
    with (folder / "runs.jsonl").open("w", encoding="utf-8", newline="\n") as trace:
        trace.write(json.dumps(config) + "\n")
        for block, mode, directory, shaders, key in arms:
            frames = directory / "frames"
            frames.mkdir()
            started = monotonic()
            result = subprocess.run([executable, mode, adapter, scene_path, shaders, frames],
                                    capture_output=True, timeout=12, text=True)
            wall = 1000 * (monotonic() - started)
            if result.returncode:
                (directory / "failed.log").write_text(result.stdout + result.stderr, encoding="utf-8")
                result.check_returncode()
            value = json.loads(result.stdout)
            verify(value, mode, manifest)
            hashes = []
            for index in range(3):
                data = (frames / f"{index}.rgba").read_bytes()
                if len(data) != SIZE[0] * SIZE[1] * 4:
                    raise ValueError("Incomplete frame")
                hashes.append(digest(data))
                if reference is None:
                    Image.frombytes("RGBA", SIZE, data).save(folder / f"reference-{index}.png")
            if reference is None:
                reference = (value["device"], value["driver"], hashes)
            if reference != (value["device"], value["driver"], hashes):
                raise ValueError(f"Complete frame mismatch for block {block}, {mode}")
            if len(set(hashes)) != 3:
                raise ValueError("Diagnostic outputs did not differ")
            row = {"block": block, "cache_key": key, "process_ms": wall, "frame_sha256": hashes, **value}
            done.append(row)
            trace.write(json.dumps(row) + "\n")
            trace.flush()
    summary = dict(config)
    summary.update(frames_compared=len(done) * 3, rgba_bytes_compared=len(done) * 3 * SIZE[0] * SIZE[1] * 4,
                   input_draws=manifest["draws"], input_triangles=manifest["indexed_triangles"],
                   reference_sha256=reference[2], mixes={}, paired_shared_minus_reserved_ms=[])
    for mode in MODES:
        records = [row for row in done if row["mode"] == mode]
        summary["mixes"][mode] = {
            **{name: median(row[name] for row in records) for name in METRICS},
            "active_at_demand": [row["active_at_demand"] for row in records],
            "elapsed_each_ms": [row["demand_ms"] for row in records],
        }
    for block in range(groups):
        rows = {row["mode"]: row for row in done if row["block"] == block}
        summary["paired_shared_minus_reserved_ms"].append(rows["shared"]["demand_ms"] - rows["reserved"]["demand_ms"])
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    tools = sub.add_parser("build")
    tools.add_argument("output", type=Path)
    for name in ("clang", "dlltool", "headers"):
        tools.add_argument("--" + name, type=Path, required=True)
    sweep = sub.add_parser("run")
    sweep.add_argument("output", type=Path)
    for name in ("executable", "scene-dir", "dxc", "validator"):
        sweep.add_argument("--" + name, type=Path, required=True)
    sweep.add_argument("--adapter", required=True)
    sweep.add_argument("--campaign", type=int, choices=range(1, 999), required=True, metavar="1..998")
    sweep.add_argument("--groups", type=int, choices=(4, 8), default=4)
    args = parser.parse_args()
    if args.action == "build":
        build(args.output, args.clang, args.dlltool, args.headers)
    else:
        run(args.output, args.executable.resolve(), args.scene_dir.resolve(), args.adapter, args.dxc,
            args.validator, args.campaign, args.groups)


if __name__ == "__main__":
    main()
