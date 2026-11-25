"""Shared Blender Vulkan point preview for the pinned Tokyo workflow."""

import gpu
from mathutils import Matrix
import numpy as np


PALETTE = """
vec3 point_color(float class_id)
{
  if (class_id == 2.0) return vec3(1.0, 7.0, 3.0) / 255.0;
  if (class_id == 3.0) return vec3(7.0, 4.0, 1.0) / 255.0;
  return vec3(2.0, 3.0, 7.0) / 255.0;
}
"""


def storage(array):
    if array.dtype not in (np.dtype("float32"), np.dtype("uint32")):
        raise TypeError(f"Unsupported GPU array type: {array.dtype}")
    if not array.flags.c_contiguous:
        raise ValueError("GPU buffer requires contiguous data")
    return gpu.types.GPUStorageBuf(array)


def update_storage(buffer, array):
    if array.dtype not in (np.dtype("float32"), np.dtype("uint32")) or not array.flags.c_contiguous:
        raise ValueError("Upload requires contiguous float32 or uint32 values")
    buffer.update(array)


def pack_source(positions, classes):
    rows = np.empty((len(classes), 4), dtype=np.float32)
    rows[:, :3] = positions
    rows[:, 3] = classes
    return rows


def make_shader():
    varyings = gpu.types.GPUStageInterfaceInfo("pb_point_varying")
    varyings.flat("VEC3", "point_color_out")
    info = gpu.types.GPUShaderCreateInfo()
    info.storage_buf(0, "vec4", "point_rows[]", qualifiers={"READ"})
    info.storage_buf(1, "uint", "order_rows[]", qualifiers={"READ"})
    info.push_constant("MAT4", "view_projection")
    info.push_constant("FLOAT", "cut_x")
    info.push_constant("INT", "layout_mode")
    info.vertex_in(0, "FLOAT", "base_offset")
    info.vertex_out(varyings)
    info.fragment_out(0, "VEC4", "out_color")
    info.vertex_source(PALETTE + """
void main()
{
  uint id = uint(gpu_InstanceIndex);
  bool edit = false;
  if (layout_mode == 2) {
    uint entry = order_rows[id];
    id = entry & 0x7fffffffu;
    edit = (entry & 0x80000000u) != 0u;
  }
  vec4 point = point_rows[id];
  if (layout_mode == 1) edit = point.x < cut_x && point.w == 1.0;
  if (layout_mode == 3 || layout_mode == 4) {
    uint stride = layout_mode == 3 ? 2u : 1u;
    edit = (order_rows[stride * (id >> 5u)] & (1u << (id & 31u))) != 0u;
  }
  if (edit) {
    point.z = 0.0;
    point.w = 2.0;
  }
  point_color_out = point_color(point.w);
  gl_Position = view_projection * vec4(point.xyz, 1.0);
  gl_Position.x += base_offset;
  gl_PointSize = 1.0;
}
""")
    info.fragment_source("""
void main()
{
  out_color = vec4(point_color_out, 1.0);
}
""")
    return gpu.shader.create_from_info(info)


class PointRenderer:
    """Draw opaque-to-order point density. Geometry materialization is separate."""

    def __init__(self, positions, classes):
        self.input = storage(pack_source(positions, classes))
        self.count = len(classes)
        self.empty_order = storage(np.zeros(4, dtype=np.uint32))
        self.shader = make_shader()
        format = gpu.types.GPUVertFormat()
        format.attr_add(id="base_offset", comp_type="F32", len=1, fetch_mode="FLOAT")
        vertex = gpu.types.GPUVertBuf(format=format, len=1)
        vertex.attr_fill(id="base_offset", data=(0.0,))
        self.batch = gpu.types.GPUBatch(type="POINTS", buf=vertex)

    def draw(self, matrix, threshold, layout, *, rows=None, order=None):
        """Set the caller's HDR-independent additive pass and draw its point view."""
        previous_blend = gpu.state.blend_get()
        previous_depth = gpu.state.depth_test_get()
        previous_depth_mask = gpu.state.depth_mask_get()
        try:
            gpu.state.blend_set("ADDITIVE")
            gpu.state.depth_test_set("NONE")
            gpu.state.depth_mask_set(False)
            self.shader.bind()
            self.shader.uniform_float("view_projection", matrix)
            self.shader.uniform_float("cut_x", threshold)
            self.shader.uniform_int("layout_mode", layout)
            self.shader.storage_block("point_rows", self.input if rows is None else rows)
            self.shader.storage_block("order_rows", self.empty_order if order is None else order)
            self.batch.draw_instanced(self.shader, instance_count=self.count)
        finally:
            gpu.state.depth_mask_set(previous_depth_mask)
            gpu.state.depth_test_set(previous_depth)
            gpu.state.blend_set(previous_blend)


def test_projection(view):
    """Orthographic oblique views of the centered 500 x 500 m tile."""
    skew = (0.29, -0.43, 0.54)[view]
    return Matrix(((0.0033, 0.0003 * (view - 1), 0.0002, 0.0),
                   (0.0002 * (view - 1), 0.0032, skew * 0.0032, 0.0),
                   (0.0, 0.0, 0.001, 0.0),
                   (0.0, 0.0, 0.0, 1.0)))
