"""Check Blender's orphan-purge recovery for the add-on's native output."""

from pathlib import Path
import sys

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import point_view_addon as addon


if not bpy.app.background or bpy.data.filepath:
    raise RuntimeError("Use a fresh background Blender run")

addon.register()
try:
    scene = bpy.context.scene
    positions = np.array([[-5, 1, 8], [-2, 2, 9], [0, 3, 10], [5, 4, 11]],
                         dtype=np.float32)
    classes = np.array([1, 2, 1, 3], dtype=np.int32)
    intensity = np.array([20, 21, 22, 23], dtype=np.int32)
    cloud = addon.prepare_cloud(positions, classes, intensity)
    addon._previews[scene.session_uid] = addon.Preview(
        positions, classes, intensity, (0, 0, 0), cloud
    )
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=False)
    try:
        cloud.users
    except ReferenceError:
        pass
    else:
        raise RuntimeError("The deliberate control did not remove the staged cloud")

    scene.portbridge_point_view.cut_x = 0.0
    if bpy.ops.portbridge.commit_point_preview() != {"FINISHED"}:
        raise RuntimeError("The add-on could not rebuild the staged cloud")
    data = bpy.context.view_layer.objects.active.data
    ids = np.empty(4, dtype=np.int32)
    data.attributes["source_id"].data.foreach_get("value", ids)
    if ids.tolist() != [1, 2, 3, 0] or addon.preview_for(scene) is not None:
        raise RuntimeError("Unexpected native order or leftover preview")
    print("Orphan purge removed staging. Native commit rebuilt it and preserved exact order.")
finally:
    addon.unregister()
