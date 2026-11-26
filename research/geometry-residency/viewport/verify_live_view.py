"""Exercise two edits through Blender's real 3D view event loop, then exit."""

import json
from pathlib import Path
import sys
from time import monotonic

import bpy
import gpu

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import point_view_addon as addon


def run(archive, output):
    if bpy.app.background or bpy.data.filepath or output.exists():
        raise RuntimeError("Use a new GUI factory-startup session and fresh output path")
    addon.register()
    start = monotonic()
    cuts = (-125.0, 125.0)
    rendered = {}
    state = {"position": -1}
    wrapped = addon.draw_scene_preview

    def track(scene, matrix):
        drawn = wrapped(scene, matrix)
        if drawn:
            value = scene.portbridge_point_view.cut_x
            if value in cuts and value not in rendered:
                _, _, width, height = gpu.state.viewport_get()
                rendered[value] = {"cut": value, "viewport": [width, height],
                                   "device": gpu.platform.renderer_get(),
                                   "backend": gpu.platform.backend_type_get()}
        return drawn

    def finish(status, error=None):
        with output.open("x", encoding="utf-8") as stream:
            json.dump({"status": status, "error": error, "draws": list(rendered.values()),
                       "blender": bpy.app.build_hash.decode("ascii")}, stream, indent=2)
            stream.write("\n")
        addon.draw_scene_preview = wrapped
        addon.unregister()
        bpy.ops.wm.quit_blender()

    def step():
        if monotonic() - start >= 30:
            finish("timeout", "No two observed interactive viewport draws")
            return None
        try:
            window = next(iter(bpy.context.window_manager.windows), None)
            if window is None:
                return 0.1
            scene = window.scene
            area = next((area for area in window.screen.areas if area.type == "VIEW_3D"), None)
            if area is None:
                return 0.1
            region = next(region for region in area.regions if region.type == "WINDOW")
            settings = scene.portbridge_point_view
            if state["position"] < 0:
                with bpy.context.temp_override(window=window, area=area, region=region):
                    settings.archive = str(archive.resolve(strict=True))
                    settings.cut_x = cuts[0]
                    if bpy.ops.portbridge.load_point_preview() != {"FINISHED"}:
                        raise RuntimeError("Could not load the tile")
                    if bpy.ops.portbridge.frame_point_preview() != {"FINISHED"}:
                        raise RuntimeError("Could not frame the preview")
                state["position"] = 0
            elif cuts[state["position"]] in rendered:
                if state["position"] == len(cuts) - 1:
                    finish("passed")
                    return None
                state["position"] += 1
                settings.cut_x = cuts[state["position"]]
            if (preview := addon.preview_for(scene)) is not None and preview.error:
                raise RuntimeError(preview.error)
        except Exception as exc:
            finish("failed", str(exc))
            return None
        return 0.1

    addon.draw_scene_preview = track
    bpy.app.timers.register(step, first_interval=0.2)


if __name__ == "__main__":
    run(*map(Path, sys.argv[sys.argv.index("--") + 1:]))
