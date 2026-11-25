"""Stock Blender point edit to completed native viewport frame on the Tokyo LiDAR tile."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

import bpy
import gpu
from mathutils import Vector
import numpy as np


def options():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("stock_source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--warmup-rounds", type=int, default=2)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--radius", type=float, default=0.45)
    parsed = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if not bpy.app.background or bpy.data.filepath:
        parser.error("Start Blender in background factory mode with no input scene")
    if parsed.rounds < 1 or parsed.warmup_rounds < 1:
        parser.error("Run and warmup counts must be positive")
    if min(parsed.width, parsed.height) < 32 or max(parsed.width, parsed.height) > 4096:
        parser.error("Use image dimensions between 32 and 4096")
    if parsed.radius <= 0:
        parser.error("Point radius must be positive")
    if parsed.output.exists():
        parser.error("Use a new output path")
    if not (parsed.stock_source / "tokyo_stock_point_edit.py").is_file():
        parser.error("Stock script is missing")
    return parsed


def camera_and_view(scene, width, height):
    area = next(a for a in bpy.context.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    view = area.spaces.active
    view.overlay.show_overlays = False
    view.shading.type = "SOLID"
    view.shading.light = "FLAT"
    view.shading.color_type = "SINGLE"
    view.shading.single_color = (0.35, 0.66, 1.0)
    view.shading.background_type = "WORLD"
    view.shading.show_shadows = False
    view.shading.show_cavity = False
    view.shading.show_specular_highlight = False
    scene.display.viewport_aa = "OFF"
    scene.world.color = (0.025, 0.025, 0.025)
    eye = Vector((125.0, -1200.0, 1200.0))
    camera_data = bpy.data.cameras.new("Tokyo viewport camera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 1360.0
    camera_data.clip_end = 6000.0
    camera = bpy.data.objects.new("Tokyo viewport camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = eye
    camera.rotation_euler = (-eye).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera
    view.clip_end = camera_data.clip_end
    view.region_3d.view_perspective = "ORTHO"
    bpy.context.view_layer.update()
    view_matrix = camera.matrix_world.inverted()
    projection_matrix = camera.calc_matrix_camera(
        bpy.context.evaluated_depsgraph_get(), x=width, y=height
    )
    return area, region, view, eye, view_matrix, projection_matrix


def run(args):
    sys.path.insert(0, str(args.stock_source))
    from tokyo_stock_point_edit import ARCHIVE_SHA256, POINT_COUNT, THRESHOLDS, create_object, load_las

    scene = bpy.context.scene
    layer = bpy.context.view_layer
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    positions, classes, intensity, origin = load_las(args.archive)
    obj, threshold = create_object(positions, classes, intensity)
    radius = obj.data.attributes.get("radius")
    if radius is None:
        radius = obj.data.attributes.new("radius", "FLOAT", "POINT")
    radius.data.foreach_set("value", np.full(POINT_COUNT, args.radius, dtype=np.float32))
    area, region, view, eye, view_matrix, projection_matrix = camera_and_view(scene, args.width, args.height)
    gpu.init()
    print(f"DEVICE {gpu.platform.backend_type_get()} {gpu.platform.renderer_get()}", flush=True)
    dimensions = (args.height, args.width, 4)
    pixels = np.empty(dimensions, dtype=np.uint8)
    readback = gpu.types.Buffer("UBYTE", dimensions, pixels)
    offscreen = gpu.types.GPUOffScreen(args.width, args.height, format="RGBA8")

    def evaluate(value):
        started = time.perf_counter_ns()
        threshold.default_value = value
        layer.update()
        evaluated = time.perf_counter_ns()
        with bpy.context.temp_override(window=bpy.context.window, area=area, region=region):
            offscreen.draw_view3d(scene, layer, view, region, view_matrix, projection_matrix,
                                  do_color_management=False, draw_background=True)
        submitted = time.perf_counter_ns()
        with offscreen.bind():
            gpu.state.active_framebuffer_get().read_color(
                0, 0, args.width, args.height, 4, 0, "UBYTE", data=readback
            )
        completed = time.perf_counter_ns()
        return {
            "threshold_x_m": value,
            "edit_evaluate_ms": (evaluated - started) / 1_000_000.0,
            "draw_call_ms": (submitted - evaluated) / 1_000_000.0,
            "image_read_wait_ms": (completed - submitted) / 1_000_000.0,
            "edit_to_completed_image_ms": (completed - started) / 1_000_000.0,
            "image_sha256": hashlib.sha256(pixels).hexdigest(),
            "noncorner_pixels": int(np.count_nonzero(np.any(pixels != pixels[0, 0], axis=2))),
        }

    try:
        for _ in range(args.warmup_rounds):
            for value in THRESHOLDS:
                result = evaluate(value)
                print("WARM", json.dumps(result), flush=True)

        results = []
        for round_index in range(1, args.rounds + 1):
            for value in THRESHOLDS:
                result = evaluate(value)
                results.append({"round": round_index, **result})
                print("MEASURE", json.dumps(results[-1]), flush=True)
    finally:
        offscreen.free()

    by_threshold = {
        value: [trial for trial in results if trial["threshold_x_m"] == value]
        for value in THRESHOLDS
    }
    if any(row["noncorner_pixels"] < args.width * args.height * 0.005 for row in results):
        raise RuntimeError("Native point cloud draw returned a nearly empty image")
    image_variants = {value: sorted({row["image_sha256"] for row in rows})
                      for value, rows in by_threshold.items()}
    if len({variant[0] for variant in image_variants.values()}) != len(THRESHOLDS):
        raise RuntimeError("Native viewport images did not all react to the edit")
    scope = (
        "Set stock Geometry Nodes cut threshold, evaluate view layer, draw the native Blender "
        "3D viewport into the same RGBA8 offscreen target, and wait for complete image readback. "
        "View is SOLID Workbench with overlays and AA disabled. Initialization, render target "
        "allocation, image hashing, checks and disk I/O are outside measurement."
    )
    answer = {
        "scope": scope,
        "data_sha256": ARCHIVE_SHA256,
        "data_origin": origin,
        "points": POINT_COUNT,
        "blender": bpy.app.version_string,
        "build_hash": bpy.app.build_hash.decode(),
        "backend": gpu.platform.backend_type_get(),
        "renderer": gpu.platform.renderer_get(),
        "width": args.width,
        "height": args.height,
        "point_radius_m": args.radius,
        "camera_eye": list(eye),
        "view_matrix": [list(row) for row in view_matrix],
        "projection_matrix": [list(row) for row in projection_matrix],
        "warmup_rounds": args.warmup_rounds,
        "trials": results,
        "image_hashes_by_threshold": image_variants,
        "repeat_exact": all(len(variants) == 1 for variants in image_variants.values()),
        "median_ms_by_threshold": {
            value: {field: statistics.median(row[field] for row in rows)
                    for field in ("edit_evaluate_ms", "draw_call_ms", "image_read_wait_ms",
                                  "edit_to_completed_image_ms")}
            for value, rows in by_threshold.items()
        },
    }
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(answer, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    run(options())
