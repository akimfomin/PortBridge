"""Verify the add-on's actual operators and native point cloud output."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import bpy
import gpu
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

import point_view_addon as addon
from point_preview import test_projection
from tokyo_stock_point_edit import POINT_COUNT, validate


def parse():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reopen", action="store_true")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


def edit_to_frame(scene, target, cut):
    start = perf_counter_ns()
    scene.portbridge_point_view.cut_x = cut
    with target.bind():
        frame = gpu.state.active_framebuffer_get()
        frame.clear(color=(0.0, 0.0, 0.0, 1.0), depth=1.0)
        if not addon.draw_scene_preview(scene, test_projection(0)):
            raise RuntimeError("Expected an active preview")
        pixels = frame.read_color(0, 0, 960, 720, 4, 0, "UBYTE")
    ready = perf_counter_ns()
    rgba = np.frombuffer(pixels, dtype=np.uint8).reshape(-1, 4)
    if np.count_nonzero(rgba[:, :3]) < 50000:
        raise RuntimeError("The preview did not draw the point cloud")
    return {"sha256": sha256(rgba).hexdigest(), "cold_edit_to_frame_ns": ready - start}


def verify(args):
    if bpy.data.filepath or not bpy.app.background:
        raise RuntimeError("Use a fresh background process for the operator check")
    args.output.mkdir(parents=True, exist_ok=False)
    stock = json.loads((HERE.parent / "evidence/tokyo-stock-point-edit.json").read_text())
    expected = {float(row["threshold_x_m"]): row["output_sha256"] for row in stock["validation"]}
    results = []
    gpu.init()
    if gpu.platform.backend_type_get() != "VULKAN":
        raise RuntimeError("Expected Vulkan")
    target = gpu.types.GPUOffScreen(960, 720, format="RGBA8")
    addon.register()
    try:
        scene = bpy.context.scene
        scene.portbridge_point_view.archive = str(args.archive.resolve(strict=True))
        for cut, digest in expected.items():
            started_load = perf_counter_ns()
            if bpy.ops.portbridge.load_point_preview() != {"FINISHED"}:
                raise RuntimeError("Native load operator failed")
            load_ns = perf_counter_ns() - started_load
            data = addon.preview_for(scene)
            result = edit_to_frame(scene, target, cut)
            start = perf_counter_ns()
            if bpy.ops.portbridge.commit_point_preview() != {"FINISHED"}:
                raise RuntimeError("Native commit operator failed")
            elapsed = perf_counter_ns() - start
            obj = bpy.context.view_layer.objects.active
            if obj.type != "POINTCLOUD" or addon.preview_for(scene) is not None:
                raise RuntimeError("The native object was not created or the preview remains live")
            details = validate(obj.data, data.positions, data.classes, data.intensity, cut)
            if details["output_sha256"] != digest:
                raise RuntimeError("Native object differs from the exact stock result")
            results.append({"cut": cut, "points": POINT_COUNT, "load_ns": load_ns, "commit_ns": elapsed,
                            "preview": result, "native_sha256": details["output_sha256"]})
            print(f"Verified actual add-on load, draw and commit at {cut}: {digest}", flush=True)
            if cut != 125.0:
                cloud = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.pointclouds.remove(cloud)
    finally:
        addon.unregister()
        target.free()
    if len({row["preview"]["sha256"] for row in results}) != len(expected):
        raise RuntimeError("Expected distinct edited images")
    bpy.ops.wm.save_as_mainfile(filepath=str((args.output / "committed-cloud.blend").resolve()),
                                compress=True)
    with (args.output / "operators.json").open("x", encoding="utf-8") as stream:
        json.dump({"build": bpy.app.build_hash.decode("ascii"), "gpu": gpu.platform.renderer_get(),
                   "driver": gpu.platform.version_get(), "results": results}, stream, indent=2)
        stream.write("\n")


def verify_reopen(args):
    if not bpy.data.filepath:
        raise RuntimeError("Open the saved native point cloud first")
    report = json.loads((args.output / "operators.json").read_text(encoding="utf-8"))
    row = next(value for value in report["results"] if value["cut"] == 125.0)
    obj = next(obj for obj in bpy.context.scene.objects
               if obj.type == "POINTCLOUD" and obj.get("portbridge_cut_x_m") == row["cut"])
    cloud = obj.data
    digest = sha256()
    for name in ("source_id", "point_class", "intensity"):
        column = np.empty(POINT_COUNT, dtype=np.int32)
        cloud.attributes[name].data.foreach_get("value", column)
        digest.update(column)
    positions = np.empty((POINT_COUNT, 3), dtype=np.float32)
    cloud.attributes["position"].data.foreach_get("vector", positions.reshape(-1))
    digest.update(positions)
    if digest.hexdigest() != row["native_sha256"]:
        raise RuntimeError("Native point cloud changed after reopen")
    print(f"Reopened native point cloud with exact SHA-256 {digest.hexdigest()}")


if __name__ == "__main__":
    args = parse()
    verify_reopen(args) if args.reopen else verify(args)
