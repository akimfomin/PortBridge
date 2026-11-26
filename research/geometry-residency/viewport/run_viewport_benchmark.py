"""Benchmark the Tokyo edit and the same Vulkan framebuffer in five Blender paths."""

import argparse
from hashlib import sha256
import itertools
import json
from pathlib import Path
import struct
import sys
from time import perf_counter_ns
import zlib

import bpy
import gpu
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

from point_preview import PointRenderer, pack_source, storage, test_projection, update_storage
import point_view_addon as addon
from preview_cpu import CpuPreview
from stable_gpu_index import StablePartition
from tokyo_stock_point_edit import THRESHOLDS, create_object


MODES = ("graph", "cpu", "cpu-mask", "compact", "mask", "fused")


def read_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("cpu_library", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--blocks", type=int, default=10)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--completion", choices=("image", "pixel"), default="image")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=MODES)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


class StockGraph:
    def __init__(self, positions, classes, intensity):
        self.obj, self.threshold = create_object(positions, classes, intensity)
        self.layer = bpy.context.view_layer
        self.positions = np.empty_like(positions)
        self.classes = np.empty_like(classes)
        self.output = np.empty((len(classes), 4), dtype=np.float32)

    def edit(self, threshold):
        self.threshold.default_value = threshold
        self.layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        geometry = self.obj.evaluated_get(graph).evaluated_geometry()
        cloud = geometry.pointcloud
        if cloud is None or len(cloud.points) != len(self.classes):
            raise RuntimeError("The reference graph changed the point count")
        cloud.attributes["position"].data.foreach_get("vector", self.positions.reshape(-1))
        cloud.attributes["point_class"].data.foreach_get("value", self.classes)
        self.output[:, :3] = self.positions
        self.output[:, 3] = self.classes
        return self.output


def write_png(path, width, height, pixels):
    rgba = np.frombuffer(pixels, dtype=np.uint8).reshape(height, width, 4)
    payload = b"".join(b"\x00" + row.tobytes() for row in rgba[::-1])

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    info = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", info) +
                     chunk(b"IDAT", zlib.compress(payload)) + chunk(b"IEND", b""))


def sample_order(modes, blocks):
    order = list(modes)
    for block in range(blocks):
        offset = (block // 2) % len(order)
        rotated = order[offset:] + order[:offset]
        yield block, rotated if block % 2 == 0 else rotated[::-1]


def run(args):
    if not bpy.app.background or bpy.data.filepath:
        raise RuntimeError("Run from a fresh Blender background process")
    if args.blocks <= 0 or not (1 <= args.width <= 4096 and 1 <= args.height <= 4096):
        raise ValueError("Invalid block or frame size")
    modes = args.modes
    if len(set(modes)) != len(modes) or "fused" not in modes or "graph" not in modes:
        raise ValueError("Use unique modes including graph and fused")
    args.output.mkdir(parents=True, exist_ok=False)
    addon.register()
    scene = bpy.context.scene
    settings = scene.portbridge_point_view
    settings.archive = str(args.archive.resolve(strict=True))
    if bpy.ops.portbridge.load_point_preview() != {"FINISHED"}:
        raise RuntimeError("Could not load the preview through the add-on")
    point_data = addon.preview_for(scene)
    positions, classes, intensity = point_data.positions, point_data.classes, point_data.intensity
    gpu.init()
    if gpu.platform.backend_type_get() != "VULKAN":
        raise RuntimeError("Blender did not use the Vulkan backend")

    renderer = PointRenderer(positions, classes)
    point_data.renderer = renderer
    stock = StockGraph(positions, classes, intensity)
    source = pack_source(positions, classes)
    cpu = CpuPreview(args.cpu_library, source, args.workers) if any(mode in modes for mode in ("cpu", "cpu-mask")) else None
    partition = StablePartition.from_packed_rows(renderer.input, len(classes)) if (
        "compact" in modes or "mask" in modes
    ) else None
    mutable = storage(source)
    cpu_bits = storage(np.zeros_like(cpu.bits)) if "cpu-mask" in modes else None
    offscreen = gpu.types.GPUOffScreen(args.width, args.height, format="RGBA8")
    results = []
    hashes = {}
    dimensions = (args.height, args.width, 4)
    pixels = np.empty(dimensions, dtype=np.uint8)
    readback = gpu.types.Buffer("UBYTE", dimensions, pixels)
    marker = gpu.types.Buffer("UBYTE", (1, 1, 4))

    def draw(mode, threshold, view):
        projection = test_projection(view)
        rows = None
        order = None
        layout = 1
        with offscreen.bind():
            frame = gpu.state.active_framebuffer_get()
            start = perf_counter_ns()
            settings.cut_x = threshold
            if mode == "graph":
                update_storage(mutable, stock.edit(threshold))
                rows, layout = mutable, 0
            elif mode == "cpu":
                update_storage(mutable, cpu.edit(threshold))
                rows, layout = mutable, 0
            elif mode == "cpu-mask":
                update_storage(cpu_bits, cpu.mask(threshold))
                order, layout = cpu_bits, 4
            elif mode == "compact":
                order, layout = partition.edit(threshold), 2
            elif mode == "mask":
                order, layout = partition.classify(threshold), 3
            edit = perf_counter_ns()
            frame.clear(color=(0.0, 0.0, 0.0, 1.0), depth=1.0)
            if mode == "fused":
                if not addon.draw_scene_preview(scene, projection):
                    raise RuntimeError("The add-on preview did not draw")
            else:
                renderer.draw(projection, threshold, layout, rows=rows, order=order)
            issued = perf_counter_ns()
            if args.completion == "pixel":
                frame.read_color(args.width // 2, args.height // 2, 1, 1, 4, 0, "UBYTE", data=marker)
                ready = perf_counter_ns()
                frame.read_color(0, 0, args.width, args.height, 4, 0, "UBYTE", data=readback)
            else:
                frame.read_color(0, 0, args.width, args.height, 4, 0, "UBYTE", data=readback)
                ready = perf_counter_ns()
        image = memoryview(pixels)
        checksum = sha256(image).hexdigest()
        key = (threshold, view)
        if key not in hashes:
            array = np.frombuffer(image, dtype=np.uint8).reshape(-1, 4)
            if np.count_nonzero(array[:, :3]) < args.width * args.height // 20:
                raise RuntimeError("Expected a visible point cloud")
            hashes[key] = checksum
        if hashes[key] != checksum:
            raise RuntimeError(f"Pixels differ for {mode} {threshold} {view}: {checksum}")
        return (edit - start, issued - edit, ready - issued, ready - start, checksum,
                image.tobytes() if mode == "fused" and threshold == THRESHOLDS[0] and view == 0 else None)

    try:
        for view in range(3):
            for threshold in THRESHOLDS:
                draw("graph", threshold, view)
            if len({hashes[threshold, view] for threshold in THRESHOLDS}) != 4:
                raise RuntimeError("Edits produced identical images")
        for mode in modes:
            for threshold, view in zip(THRESHOLDS, itertools.cycle(range(3))):
                sample = draw(mode, threshold, view)
                if sample[-1] is not None:
                    write_png(args.output / "point-preview.png", args.width, args.height, sample[-1])
        for block, order in sample_order(modes, args.blocks):
            for mode in order:
                for edit_index, threshold in enumerate(THRESHOLDS):
                    view = (block + edit_index) % 3
                    edit_ns, draw_ns, read_ns, total_ns, checksum, _ = draw(mode, threshold, view)
                    results.append({"block": block, "mode": mode, "threshold": threshold,
                                    "view": view, "edit_ns": edit_ns, "draw_ns": draw_ns,
                                    "read_ns": read_ns, "total_ns": total_ns, "sha256": checksum})
            print(f"Verified block {block + 1}/{args.blocks} {order}", flush=True)
        evidence = {
            "schema": 1,
            "build": bpy.app.build_hash.decode("ascii"),
            "gpu": gpu.platform.renderer_get(),
            "driver": gpu.platform.version_get(),
            "backend": gpu.platform.backend_type_get(),
            "point_count": renderer.count,
            "dimensions": [args.width, args.height],
            "scope": "property edit through synchronized framebuffer completion in the shared renderer",
            "completion": args.completion,
            "workers": args.workers,
            "partition_scratch_bytes": partition.scratch_bytes if partition else 0,
            "rows": results,
        }
        with (args.output / "frames.json").open("x", encoding="utf-8") as stream:
            json.dump(evidence, stream, indent=2)
            stream.write("\n")
    finally:
        if cpu is not None:
            cpu.close()
        offscreen.free()
        addon.unregister()


if __name__ == "__main__":
    run(read_args())
