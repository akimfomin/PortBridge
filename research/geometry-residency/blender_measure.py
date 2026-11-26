"""Measure Blender scene evaluation and independently sample evaluated point geometry.

Run in Blender with auto-execution disabled. No scene changes are saved.
"""

from array import array
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter_ns

import bpy
import gpu


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--object", action="append", required=True)
    parser.add_argument("--last-frame", type=int, required=True)
    parser.add_argument("--sample", type=int, action="append", default=[])
    parser.add_argument("--capture", choices=("saved", "cpu", "gpu"), default="saved")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


def patch_capture_modes(objects, mode):
    if mode == "saved":
        return []
    groups = {modifier.node_group for obj in objects for modifier in obj.modifiers
              if modifier.type == "NODES" and modifier.node_group}
    edited = []
    for group in sorted(groups, key=lambda tree: tree.name):
        for node in group.nodes:
            if node.bl_idname != "GeometryNodeCaptureAttribute":
                continue
            switches = [prop for prop in node.bl_rna.properties
                        if prop.type == "ENUM" and not prop.is_readonly
                        and {item.name for item in prop.enum_items} >= {"Auto", "Custom"}]
            if len(switches) != 1:
                raise RuntimeError(f"Capture mode is unavailable for {group.name}/{node.name}")
            prop = switches[0]
            state = "Custom" if mode == "gpu" else "Auto"
            identifier = next(item.identifier for item in prop.enum_items if item.name == state)
            setattr(node, prop.identifier, identifier)
            if mode == "gpu":
                allow = node.inputs.get("Allow GPU")
                if allow is None or allow.is_linked or not allow.enabled:
                    raise RuntimeError(f"Cannot explicitly enable GPU for {group.name}/{node.name}")
                allow.default_value = True
            edited.append([group.name, node.name, prop.identifier, identifier])
    if not edited:
        raise RuntimeError("No capture nodes selected")
    return edited


def add_observer(obj):
    node_tree = bpy.data.node_groups.new("PortBridge point observer", "GeometryNodeTree")
    for direction in ("INPUT", "OUTPUT"):
        node_tree.interface.new_socket(name="Geometry", in_out=direction,
                                       socket_type="NodeSocketGeometry")
    source = node_tree.nodes.new("NodeGroupInput")
    convert = node_tree.nodes.new("GeometryNodePointsToVertices")
    sink = node_tree.nodes.new("NodeGroupOutput")
    node_tree.links.new(source.outputs["Geometry"], convert.inputs["Points"])
    node_tree.links.new(convert.outputs["Mesh"], sink.inputs["Geometry"])
    modifier = obj.modifiers.new("PortBridge point observer", "NODES")
    modifier.node_group = node_tree


def source_sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def save_points(obj, graph, output):
    mesh = obj.evaluated_get(graph).data
    if not isinstance(mesh, bpy.types.Mesh):
        raise RuntimeError(f"Probe did not produce a mesh for {obj.name}")
    count = len(mesh.vertices)
    coordinates = array("f", [0.0]) * (count * 3)
    mesh.vertices.foreach_get("co", coordinates)
    if not all(math.isfinite(value) for value in coordinates):
        raise RuntimeError(f"Non-finite output for {obj.name}")
    if coordinates.itemsize != 4 or sys.byteorder != "little":
        raise RuntimeError("The point artifact requires little-endian float32")
    with output.open("xb") as stream:
        coordinates.tofile(stream)
    return {"count": count, "positions": output.name, "sha256": source_sha(output)}


def run(args):
    scene = bpy.context.scene
    first_frame = scene.frame_start
    if not first_frame + 1 <= args.last_frame <= scene.frame_end:
        raise ValueError("Last frame must be after the start and within the original scene range")
    if any(not first_frame <= frame <= args.last_frame for frame in args.sample):
        raise ValueError("Sample frame outside evaluated frame range")
    objects = [scene.objects[name] for name in args.object]
    if len(set(objects)) != len(objects):
        raise ValueError("Object names must be unique")
    baseline = {obj.name: [modifier.name for modifier in obj.modifiers if modifier.type == "NODES"]
                for obj in objects}
    if any(not names for names in baseline.values()):
        raise ValueError("Each measured object must have a Geometry Nodes modifier")
    gpu.init()
    if gpu.platform.backend_type_get() != "VULKAN":
        raise RuntimeError("Vulkan backend was not selected")
    edits = patch_capture_modes(objects, args.capture)
    if args.sample:
        for obj in objects:
            add_observer(obj)
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for frame in range(first_frame, args.last_frame + 1):
        start = perf_counter_ns()
        scene.frame_set(frame)
        graph = bpy.context.evaluated_depsgraph_get()
        evaluated = [obj.evaluated_get(graph) for obj in objects]
        elapsed = perf_counter_ns() - start
        row = {"frame": frame, "scene_ns": elapsed, "modifier_seconds": {
            obj.name: {name: obj.modifiers[name].execution_time for name in baseline[obj.name]}
            for obj in evaluated}}
        if frame in args.sample:
            row["points"] = {
                obj.name: save_points(obj, graph, args.output / f"{frame}-{index}.f32")
                for index, obj in enumerate(objects)
            }
        rows.append(row)
    result = {
        "source_sha256": source_sha(Path(bpy.data.filepath)),
        "build": bpy.app.build_hash.decode(),
        "device": gpu.platform.renderer_get(),
        "driver": gpu.platform.version_get(),
        "backend": gpu.platform.backend_type_get(),
        "capture_mode": args.capture,
        "edited_captures": edits,
        "observer": bool(args.sample),
        "first_frame": first_frame,
        "rows": rows,
    }
    with (args.output / "run.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(f"PortBridge evaluated {len(rows)} scene frames for {args.capture}; observer={bool(args.sample)}")


if __name__ == "__main__":
    run(arguments())
