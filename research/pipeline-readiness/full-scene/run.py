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
PHASE_MODES = ("phase-reference", "phase-lead")
PHASE_ORDERS = ((0, 1), (1, 0))
RECORD_MODES = ("record-blocking", "record-ordered", "record-eager")
RECORD_ORDERS = ((0, 1, 2), (2, 1, 0), (1, 2, 0), (0, 2, 1), (2, 0, 1), (1, 0, 2))
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


def verify(value, mode, manifest, materials=False):
    jobs = value["jobs"]
    if (value["mode"] != mode or value["draws_per_frame"] != manifest["draws"] or
            value["triangles_per_frame"] != manifest["indexed_triangles"] or
            not 0 < value["demand_ms"] <= value["startup_to_frame_ms"] or
            not 0 < value["schedule_to_drained_ms"] <= value["schedule_to_all_frames_ms"] or
            value["process_commit_sampled_peak"] < value["process_commit_before"] or
            value["lifetime_peak_commit"] < value["process_commit_sampled_peak"] or
            len(jobs) != (19 if materials else 6) or len(value["nonclear_pixels"]) != 3 or
            sum(job["first_frame"] for job in jobs) != (15 if materials else 2)):
        raise ValueError("Unexpected draw, timeline, or memory contract")
    expected = 0 if mode == "warm" else 1000297000
    for index, job in enumerate(jobs):
        if (job["id"] != index or job["preflight"] != expected or not job["feedback_flags"] & 1 or
                bool(job["feedback_flags"] & 2) != (mode == "warm") or
                not job["start_ms"] < job["return_ms"] or job["feedback_ns"] <= 0):
            raise ValueError("Unexpected cache classification, feedback, or timing")
    active = sum(job["start_ms"] <= 0 < job["return_ms"] for job in jobs if not job["first_frame"])
    if active != value["active_at_demand"]:
        raise ValueError("Incorrect overlap calculation")
    if mode in PHASE_MODES:
        begin, end = value["upload_begin_ms"], value["upload_end_ms"]
        if not begin < end <= 0:
            raise ValueError("Invalid scene upload window")
        overlaps = [j["id"] for j in jobs if j["start_ms"] < end and j["return_ms"] > begin]
        if mode == "phase-reference" and overlaps:
            raise ValueError("Reference arm compiled during upload")
        if mode == "phase-lead" and (not overlaps or set(overlaps) - {0, 3}):
            raise ValueError("Could not establish first-frame compilation during upload")
        value["pipelines_overlapping_upload"] = overlaps
    if mode in RECORD_MODES:
        if any(job["start_ms"] < 0 for job in jobs):
            raise ValueError("Recorded graphics arm started compilation before the common boundary")
        if mode == "record-blocking" and parallel_time(jobs):
            raise ValueError("Blocking arm overlapped native creates within a graphics pass")


def parallel_time(jobs):
    events = sorted((job[field], change) for job in jobs
                    for field, change in (("start_ms", 1), ("return_ms", -1)))
    active = 0
    elapsed = 0
    last = events[0][0]
    for time, change in events:
        if active >= 2:
            elapsed += time - last
        active += change
        last = time
    return elapsed


def run(folder, executable, scene_dir, adapter, dxc, validator, campaign, groups, phase, record=False,
        area_nodes=0, compact_area=False, materials=False):
    if any(name.startswith(("VK_LOADER_", "VK_DRIVER_", "VK_LAYER_")) or name in
           ("VK_ICD_FILENAMES", "VK_INSTANCE_LAYERS", "VK_ADD_DRIVER_FILES") for name in os.environ):
        raise ValueError("Inherited Vulkan loader overrides must be cleared for the isolated run")
    scene_path = scene_dir / "scene.bin"
    manifest = json.loads((scene_dir / "scene-manifest.json").read_text(encoding="utf-8"))
    if artifact_hash(scene_path) != manifest["scene_sha256"]:
        raise ValueError("Scene manifest mismatch")
    folder.mkdir(exist_ok=False)
    arms = []
    modes, orders, comparison = MODES, ORDERS, "prewarm-admission"
    if phase:
        modes, orders, comparison = PHASE_MODES, PHASE_ORDERS, "upload-overlap"
    if record:
        modes, orders, comparison = RECORD_MODES, RECORD_ORDERS, "ordered-graphics"
    for block in range(groups):
        for index in orders[block % len(orders)]:
            mode = modes[index]
            directory = folder / f"{block}-{mode}"
            shaders = directory / "shaders"
            const = 1000 * campaign + 10 * block + index + 1
            compile_shader(shaders, dxc, validator, const, area_nodes, compact_area, materials)
            arms.append((block, mode, directory, shaders, const))
    if len(set(artifact_hash(s / "ps.spv") for _, _, _, s, _ in arms)) != len(arms):
        raise ValueError("Fragment SPIR-V cache keys were not distinct")

    done, reference = [], None
    config = {"exe": artifact_hash(executable), "scene": manifest["scene_sha256"],
              "scene_cpp": artifact_hash(ROOT / "scene.cpp"),
              "ordered_graphics_hpp": artifact_hash(ROOT.parent / "ordered_graphics.hpp"),
              "vs_ps_hlsl": artifact_hash(ROOT / "scene.hlsl"),
              "dxc": artifact_hash(dxc), "spirv_validator": artifact_hash(validator),
              "campaign": campaign, "adapter": adapter, "width": SIZE[0], "height": SIZE[1],
              "comparison": comparison, "material_recipes": materials}
    if area_nodes:
        config.update(area_nodes=area_nodes, area_shader=artifact_hash(ROOT / "area-light.hlsli"),
                      area_loop="compact" if compact_area else "unrolled")
    with (folder / "runs.jsonl").open("w", encoding="utf-8", newline="\n") as trace:
        trace.write(json.dumps(config) + "\n")
        for block, mode, directory, shaders, key in arms:
            frames = directory / "frames"
            frames.mkdir()
            started = monotonic()
            command = [executable, mode, adapter, scene_path, shaders, frames]
            if materials:
                command.append("--materials")
            result = subprocess.run(command,
                                    capture_output=True, timeout=45 if area_nodes else 12, text=True)
            wall = 1000 * (monotonic() - started)
            if result.returncode:
                (directory / "failed.log").write_text(result.stdout + result.stderr, encoding="utf-8")
                result.check_returncode()
            value = json.loads(result.stdout)
            verify(value, mode, manifest, materials)
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
            pixel = shaders / "ps.spv"
            row = {"block": block, "cache_key": key, "pixel_bytes": pixel.stat().st_size,
                   "pixel_sha256": artifact_hash(pixel), "process_ms": wall, "frame_sha256": hashes, **value}
            done.append(row)
            trace.write(json.dumps(row) + "\n")
            trace.flush()
    summary = dict(config)
    summary.update(frames_compared=len(done) * 3, rgba_bytes_compared=len(done) * 3 * SIZE[0] * SIZE[1] * 4,
                   input_draws=manifest["draws"], input_triangles=manifest["indexed_triangles"],
                   reference_sha256=reference[2], mixes={})
    for mode in modes:
        records = [row for row in done if row["mode"] == mode]
        summary["mixes"][mode] = {
            **{name: median(row[name] for row in records) for name in METRICS},
            "active_at_demand": [row["active_at_demand"] for row in records],
            "elapsed_each_ms": [row["demand_ms"] for row in records],
        }
        if phase:
            summary["mixes"][mode]["overlapping_per_run"] = [
                row["pipelines_overlapping_upload"] for row in records]
        if record:
            summary["mixes"][mode]["first_frame_parallel_native_ms"] = [
                parallel_time([job for job in row["jobs"] if job["first_frame"]]) for row in records]
    checked_fields = METRICS + ("explicit_vk_allocation_total_bytes",)
    comparison = "paired_reference_minus_lead" if phase else "paired_shared_minus_reserved"
    by_block = {(row["block"], row["mode"]): row for row in done}

    def differences(first, second):
        return {name: [by_block[block, first][name] - by_block[block, second][name] for block in range(groups)]
                for name in checked_fields}

    if record:
        comparison = "paired_blocking_minus_ordered"
        summary["paired_eager_minus_ordered"] = differences(modes[2], modes[1])
    summary[comparison] = differences(modes[0], modes[1])
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
    sweep.add_argument("--groups", type=int, choices=(1, 4, 6, 8), default=4)
    treatment = sweep.add_mutually_exclusive_group()
    treatment.add_argument("--phase", action="store_true", help="compare critical-first creation during vs after uploads")
    treatment.add_argument("--record", action="store_true", help="compare first-use, ordered and eager graphics recording")
    sweep.add_argument("--area-nodes", type=int, choices=(32, 64, 128, 192, 256), default=0)
    sweep.add_argument("--compact-area", action="store_true", help="preserve one loop in the area-light shader")
    sweep.add_argument("--material-recipes", action="store_true", help="compile exact material-specialized graphics keys")
    args = parser.parse_args()
    if args.action == "build":
        build(args.output, args.clang, args.dlltool, args.headers)
    else:
        if (args.area_nodes or args.groups == 1 or args.material_recipes) and not args.record:
            parser.error("area lighting and single-group pilots require --record")
        if args.compact_area and not args.area_nodes:
            parser.error("--compact-area requires --area-nodes")
        run(args.output, args.executable.resolve(), args.scene_dir.resolve(), args.adapter, args.dxc,
            args.validator, args.campaign, args.groups, args.phase, args.record, args.area_nodes,
            args.compact_area, args.material_recipes)


if __name__ == "__main__":
    main()
