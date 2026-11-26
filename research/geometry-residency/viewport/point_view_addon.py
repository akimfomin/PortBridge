"""Interactive Blender preview and explicit PointCloud materialization for the Tokyo tile."""
from dataclasses import dataclass
from pathlib import Path
import sys

import bpy
from bpy.app.handlers import persistent
from bpy.props import FloatProperty, PointerProperty, StringProperty
import gpu
from mathutils import Vector
import numpy as np


bl_info = {
    "name": "PortBridge Point View",
    "author": "PortBridge",
    "version": (0, 1, 0),
    "blender": (5, 3, 0),
    "location": "3D View > Sidebar > PortBridge",
    "category": "3D View",
}

HERE = Path(__file__).resolve().parent
for folder in (HERE, HERE.parent):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from point_preview import PointRenderer
from tokyo_stock_point_edit import ARCHIVE_SHA256, create_cloud, create_tree, load_las


@dataclass
class Preview:
    positions: np.ndarray
    classes: np.ndarray
    intensity: np.ndarray
    origin: tuple
    cloud: bpy.types.PointCloud
    renderer: PointRenderer | None = None
    error: str | None = None


_previews = {}
_draw_handle = None


def preview_for(scene):
    return _previews.get(scene.session_uid)


def redraw_scene(scene):
    for window_manager in bpy.data.window_managers:
        for window in window_manager.windows:
            if window.scene == scene and window.screen:
                for area in window.screen.areas:
                    if area.type == "VIEW_3D":
                        area.tag_redraw()


def settings_changed(settings, _context):
    redraw_scene(settings.id_data)


def draw_scene_preview(scene, matrix):
    data = preview_for(scene)
    if data is None or data.error:
        return False
    if gpu.platform.backend_type_get() != "VULKAN":
        raise RuntimeError("Start Blender with Vulkan for the GPU preview")
    if data.renderer is None:
        data.renderer = PointRenderer(data.positions, data.classes)
    data.renderer.draw(matrix, scene.portbridge_point_view.cut_x, 1)
    return True


def draw_preview():
    context = bpy.context
    scene = context.scene
    if scene is None or context.region_data is None:
        return
    data = preview_for(scene)
    if data is None or data.error:
        return
    try:
        draw_scene_preview(scene, context.region_data.perspective_matrix)
    except Exception as exc:
        data.renderer = None
        data.error = str(exc)
        print(f"PortBridge Point View: {exc}")
        redraw_scene(scene)


def release(data):
    if data is None:
        return
    try:
        if data.cloud.users == 0:
            bpy.data.pointclouds.remove(data.cloud)
    except ReferenceError:
        # Blender may already have removed the transient datablock.
        pass


def close_preview(scene):
    release(_previews.pop(scene.session_uid, None))


@persistent
def clear_previews(_filepath):
    for data in _previews.values():
        release(data)
    _previews.clear()


def prepare_cloud(positions, classes, intensity):
    """Stage the native source once while loading this project tile."""
    cloud = create_cloud(positions, classes, intensity)
    try:
        radius = cloud.attributes.get("radius")
        if radius is None:
            radius = cloud.attributes.new("radius", "FLOAT", "POINT")
        radius.data.foreach_set("value", np.full(len(classes), 0.45, dtype=np.float32))
    except Exception:
        bpy.data.pointclouds.remove(cloud)
        raise
    return cloud


def materialize(context, data, threshold):
    """Make the ordered native result through Blender's checked modifier path."""
    previous = context.view_layer.objects.active
    try:
        cloud = data.cloud.copy()
    except ReferenceError:
        data.cloud = prepare_cloud(data.positions, data.classes, data.intensity)
        cloud = data.cloud.copy()
    tree = None
    obj = None
    try:
        tree, cut = create_tree()
        cut.default_value = threshold
        obj = bpy.data.objects.new("PortBridge Tokyo points", cloud)
        modifier = obj.modifiers.new("PortBridge point edit", "NODES")
        modifier.node_group = tree
        context.scene.collection.objects.link(obj)
        context.view_layer.objects.active = obj
        with context.temp_override(object=obj, active_object=obj):
            result = bpy.ops.object.modifier_apply(modifier=modifier.name)
        if result != {"FINISHED"}:
            raise RuntimeError("Blender could not materialize the point edit")
        obj["portbridge_cut_x_m"] = float(np.float32(threshold))
        obj["portbridge_source_sha256"] = ARCHIVE_SHA256
        obj["portbridge_source_origin_m"] = data.origin
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        if cloud.users == 0:
            bpy.data.pointclouds.remove(cloud)
        context.view_layer.objects.active = previous
        raise
    finally:
        if tree is not None and tree.users == 0:
            bpy.data.node_groups.remove(tree)
    return obj


class PortBridgePointSettings(bpy.types.PropertyGroup):
    archive: StringProperty(name="Tokyo ZIP", subtype="FILE_PATH")
    cut_x: FloatProperty(
        name="Cut X (m)",
        description="Flatten class 1 points below this local X and reclassify them",
        default=-25.0,
        soft_min=-300.0,
        soft_max=300.0,
        update=settings_changed,
    )


class PORTBRIDGE_OT_load_point_preview(bpy.types.Operator):
    bl_idname = "portbridge.load_point_preview"
    bl_label = "Load Tokyo Tile"

    def execute(self, context):
        scene = context.scene
        archive = scene.portbridge_point_view.archive
        if not archive:
            self.report({"ERROR"}, "Choose the pinned Tokyo ZIP from the reproduction instructions")
            return {"CANCELLED"}
        try:
            path = Path(bpy.path.abspath(archive))
            positions, classes, intensity, origin = load_las(path)
            cloud = prepare_cloud(positions, classes, intensity)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        live_scenes = {item.session_uid for item in bpy.data.scenes}
        for uid in tuple(_previews):
            if uid not in live_scenes:
                release(_previews.pop(uid))
        close_preview(scene)
        _previews[scene.session_uid] = Preview(positions, classes, intensity, tuple(origin), cloud)
        redraw_scene(scene)
        return {"FINISHED"}


class PORTBRIDGE_OT_frame_point_preview(bpy.types.Operator):
    bl_idname = "portbridge.frame_point_preview"
    bl_label = "Frame Preview"

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "VIEW_3D" and preview_for(context.scene) is not None

    def execute(self, context):
        positions = preview_for(context.scene).positions
        low = positions.min(axis=0)
        high = positions.max(axis=0)
        view = context.space_data.region_3d
        view.view_location = Vector(((low + high) * 0.5).tolist())
        view.view_rotation = Vector((0.1, 1.0, -0.85)).to_track_quat("-Z", "Y")
        view.view_distance = max(1.15 * float(np.linalg.norm(high - low)), 10.0)
        context.space_data.clip_end = max(context.space_data.clip_end, 4.0 * view.view_distance)
        view.view_perspective = "ORTHO"
        context.area.tag_redraw()
        return {"FINISHED"}


class PORTBRIDGE_OT_unload_point_preview(bpy.types.Operator):
    bl_idname = "portbridge.unload_point_preview"
    bl_label = "Close Preview"

    def execute(self, context):
        scene = context.scene
        close_preview(scene)
        redraw_scene(scene)
        return {"FINISHED"}


class PORTBRIDGE_OT_commit_point_preview(bpy.types.Operator):
    bl_idname = "portbridge.commit_point_preview"
    bl_label = "Create Blender Point Cloud"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return (context.mode == "OBJECT" and context.scene is not None
                and preview_for(context.scene) is not None)

    def execute(self, context):
        scene = context.scene
        data = preview_for(scene)
        try:
            obj = materialize(context, data, scene.portbridge_point_view.cut_x)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        close_preview(scene)
        context.view_layer.update()
        if context.view_layer.objects.get(obj.name) is not None:
            obj.select_set(True)
            context.view_layer.objects.active = obj
        redraw_scene(scene)
        self.report({"INFO"}, "Created a native Blender point cloud")
        return {"FINISHED"}


class PORTBRIDGE_PT_point_view(bpy.types.Panel):
    bl_label = "Tokyo Point View"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PortBridge"

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        settings = scene.portbridge_point_view
        layout.prop(settings, "archive")
        layout.operator("portbridge.load_point_preview")
        data = preview_for(scene)
        if data is None:
            return
        layout.prop(settings, "cut_x", slider=True)
        if data.error:
            layout.label(text=data.error, icon="ERROR")
        layout.operator("portbridge.frame_point_preview")
        layout.operator("portbridge.commit_point_preview")
        layout.operator("portbridge.unload_point_preview")


_classes = (
    PortBridgePointSettings,
    PORTBRIDGE_OT_load_point_preview,
    PORTBRIDGE_OT_frame_point_preview,
    PORTBRIDGE_OT_unload_point_preview,
    PORTBRIDGE_OT_commit_point_preview,
    PORTBRIDGE_PT_point_view,
)


def register():
    global _draw_handle
    if _draw_handle is not None:
        return
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.portbridge_point_view = PointerProperty(type=PortBridgePointSettings)
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_post,
                     bpy.app.handlers.redo_post):
        handlers.append(clear_previews)
    _draw_handle = bpy.types.SpaceView3D.draw_handler_add(draw_preview, (), "WINDOW", "POST_VIEW")


def unregister():
    global _draw_handle
    if _draw_handle is None:
        return
    bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, "WINDOW")
    _draw_handle = None
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_post,
                     bpy.app.handlers.redo_post):
        handlers.remove(clear_previews)
    clear_previews(None)
    del bpy.types.Scene.portbridge_point_view
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
