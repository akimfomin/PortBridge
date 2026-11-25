"""Time stock Blender on a point-cloud cut, flatten, reclassification, and join."""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import struct
import sys
import time
import zipfile

import bpy
import numpy as np


ARCHIVE_SHA256 = "47b03aa5cbecf2b3c3ad4cf8f00a7f420bf034ec33de8f7b206809dd7c4b5b3a"
POINT_COUNT = 6_385_097
THRESHOLDS = (-125.0, -25.0, 35.0, 125.0)
SOURCE_URL = "https://japan-pointcloud.s3.ap-northeast-1.amazonaws.com/Tokyo/2024/01/LP/Original/LAS/09/LD/16/09LD1638.zip"


def load_las(archive_path):
    with archive_path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != ARCHIVE_SHA256:
            raise ValueError("Tokyo archive checksum differs from the pinned public download")
    with zipfile.ZipFile(archive_path) as archive:
        data = archive.read("09LD1638.las")
    if data[:4] != b"LASF" or data[24:26] != b"\x01\x02" or data[104] != 3:
        raise ValueError("Expected uncompressed LAS 1.2 point format 3")
    offset = struct.unpack_from("<I", data, 96)[0]
    stride = struct.unpack_from("<H", data, 105)[0]
    count = struct.unpack_from("<I", data, 107)[0]
    if stride != 34 or count != POINT_COUNT or offset + count * stride != len(data):
        raise ValueError("Unexpected point count or file layout")
    scale = struct.unpack_from("<3d", data, 131)
    external_offset = struct.unpack_from("<3d", data, 155)
    bounds = struct.unpack_from("<6d", data, 179)
    raw_position = np.ndarray((count, 3), dtype="<i4", buffer=data,
                              offset=offset, strides=(stride, 4))
    positions = np.empty((count, 3), dtype=np.float32)
    origin = []
    for axis in range(3):
        center = (bounds[2 * axis] + bounds[2 * axis + 1]) / 2
        raw_origin = round((center - external_offset[axis]) / scale[axis])
        origin.append(raw_origin * scale[axis] + external_offset[axis])
        np.subtract(raw_position[:, axis], raw_origin, out=positions[:, axis], casting="unsafe")
        positions[:, axis] *= np.float32(scale[axis])
    raw_intensity = np.ndarray(count, dtype="<u2", buffer=data,
                               offset=offset+12, strides=(stride,))
    raw_class = np.ndarray(count, dtype="u1", buffer=data,
                           offset=offset+15, strides=(stride,))
    return positions, np.asarray(raw_class & 31, dtype=np.int32), raw_intensity.astype(np.int32), origin


def required_socket(sockets, name):
    active = [socket for socket in sockets if socket.name == name and socket.enabled]
    if len(active) != 1:
        raise ValueError(f"Expected exactly one active socket named {name!r}: {active}")
    return active[0]


def create_tree():
    tree = bpy.data.node_groups.new("Tokyo point edit", "GeometryNodeTree")
    tree.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    group_in = tree.nodes.new("NodeGroupInput")
    group_out = tree.nodes.new("NodeGroupOutput")
    position = tree.nodes.new("GeometryNodeInputPosition")
    split_axes = tree.nodes.new("ShaderNodeSeparateXYZ")
    spatial_compare = tree.nodes.new("FunctionNodeCompare")
    spatial_compare.data_type = "FLOAT"
    spatial_compare.operation = "LESS_THAN"
    source_class = tree.nodes.new("GeometryNodeInputNamedAttribute")
    source_class.data_type = "INT"
    source_class.inputs["Name"].default_value = "point_class"
    class_compare = tree.nodes.new("FunctionNodeCompare")
    class_compare.data_type = "INT"
    class_compare.operation = "EQUAL"
    required_socket(class_compare.inputs, "B").default_value = 1
    region_mask = tree.nodes.new("FunctionNodeBooleanMath")
    region_mask.operation = "AND"
    separate = tree.nodes.new("GeometryNodeSeparateGeometry")
    separate.domain = "POINT"
    recombine_axes = tree.nodes.new("ShaderNodeCombineXYZ")
    recombine_axes.inputs["Z"].default_value = 0
    move = tree.nodes.new("GeometryNodeSetPosition")
    classify = tree.nodes.new("GeometryNodeStoreNamedAttribute")
    classify.domain = "POINT"
    classify.data_type = "INT"
    classify.inputs["Name"].default_value = "point_class"
    required_socket(classify.inputs, "Value").default_value = 2
    join = tree.nodes.new("GeometryNodeJoinGeometry")

    tree.links.new(position.outputs["Position"], split_axes.inputs["Vector"])
    tree.links.new(split_axes.outputs["X"], required_socket(spatial_compare.inputs, "A"))
    tree.links.new(required_socket(source_class.outputs, "Attribute"),
                   required_socket(class_compare.inputs, "A"))
    tree.links.new(spatial_compare.outputs["Result"], region_mask.inputs[0])
    tree.links.new(class_compare.outputs["Result"], region_mask.inputs[1])
    tree.links.new(group_in.outputs["Geometry"], separate.inputs["Geometry"])
    tree.links.new(region_mask.outputs[0], separate.inputs["Selection"])
    tree.links.new(separate.outputs["Selection"], move.inputs["Geometry"])
    tree.links.new(split_axes.outputs["X"], recombine_axes.inputs["X"])
    tree.links.new(split_axes.outputs["Y"], recombine_axes.inputs["Y"])
    tree.links.new(recombine_axes.outputs["Vector"], move.inputs["Position"])
    tree.links.new(move.outputs["Geometry"], classify.inputs["Geometry"])
    tree.links.new(classify.outputs["Geometry"], join.inputs["Geometry"])
    tree.links.new(separate.outputs["Inverted"], join.inputs["Geometry"])
    tree.links.new(join.outputs["Geometry"], group_out.inputs["Geometry"])
    return tree, required_socket(spatial_compare.inputs, "B")


def create_object(positions, classes, intensity):
    cloud = bpy.data.pointclouds.new("Tokyo data 09LD1638")
    cloud.resize(len(positions))
    cloud.attributes["position"].data.foreach_set("vector", positions.reshape(-1))
    cloud.attributes.new("source_id", "INT", "POINT").data.foreach_set(
        "value", np.arange(len(positions), dtype=np.int32))
    cloud.attributes.new("point_class", "INT", "POINT").data.foreach_set("value", classes)
    cloud.attributes.new("intensity", "INT", "POINT").data.foreach_set("value", intensity)
    obj = bpy.data.objects.new("Tokyo LiDAR", cloud)
    bpy.context.scene.collection.objects.link(obj)
    tree, threshold_socket = create_tree()
    mod = obj.modifiers.new("Edit LiDAR", "NODES")
    mod.node_group = tree
    return obj, threshold_socket


def validate(cloud, coordinates, original_classes, intensities, threshold):
    selected = (coordinates[:, 0] < np.float32(threshold)) & (original_classes == 1)
    kept = np.flatnonzero(~selected).astype(np.int32)
    changed = np.flatnonzero(selected).astype(np.int32)
    if len(kept) + len(changed) != POINT_COUNT or len(cloud.points) != POINT_COUNT:
        raise AssertionError("Geometry count changed when both partitions were joined")
    attribute = cloud.attributes["source_id"]
    output_ids = np.empty(POINT_COUNT, dtype=np.int32)
    attribute.data.foreach_get("value", output_ids)
    if np.array_equal(output_ids[:len(kept)], kept) and np.array_equal(output_ids[len(kept):], changed):
        join_order = ["retained", "edited"]
    elif np.array_equal(output_ids[:len(changed)], changed) and np.array_equal(output_ids[len(changed):], kept):
        join_order = ["edited", "retained"]
    else:
        raise AssertionError("Join lost stable order, membership or point IDs")

    observed_class = np.empty(POINT_COUNT, dtype=np.int32)
    cloud.attributes["point_class"].data.foreach_get("value", observed_class)
    observed_intensity = np.empty(POINT_COUNT, dtype=np.int32)
    cloud.attributes["intensity"].data.foreach_get("value", observed_intensity)
    observed_position = np.empty((POINT_COUNT, 3), dtype=np.float32)
    cloud.attributes["position"].data.foreach_get("vector", observed_position.reshape(-1))
    for start in range(0, POINT_COUNT, 65_536):
        end = min(start + 65_536, POINT_COUNT)
        ids = output_ids[start:end]
        changed_chunk = selected[ids]
        expected_class = original_classes[ids]
        expected_class[changed_chunk] = 2
        expected_position = coordinates[ids, :]
        expected_position[changed_chunk, 2] = 0
        if not np.array_equal(observed_class[start:end], expected_class):
            raise AssertionError("Incorrect point classification")
        if not np.array_equal(observed_intensity[start:end], intensities[ids]):
            raise AssertionError("Unedited intensity attribute changed")
        if not np.array_equal(observed_position[start:end], expected_position):
            raise AssertionError("Point coordinates changed outside the requested flatten operation")
    digest = hashlib.sha256()
    for array in (output_ids, observed_class, observed_intensity, observed_position):
        digest.update(array)
    return {"threshold_x_m": threshold, "selected_points": len(changed),
            "join_order": join_order, "output_sha256": digest.hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--rounds", type=int, default=3)
    options = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if options.rounds < 1:
        parser.error("rounds must be positive")
    if not bpy.app.background or bpy.data.filepath:
        parser.error("Start Blender in background factory mode with no input scene")
    if options.output.exists():
        parser.error("Use a new JSON output path")
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    positions, classes, intensity, origin = load_las(options.archive)
    obj, threshold = create_object(positions, classes, intensity)
    layer = bpy.context.view_layer

    def evaluate(value):
        start = time.perf_counter_ns()
        threshold.default_value = value
        layer.update()
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        return elapsed_ms, evaluated.evaluated_geometry()

    for value in THRESHOLDS:
        elapsed, geometry = evaluate(value)
        if geometry.pointcloud is None:
            raise AssertionError("Expected point-cloud modifier output")
    trials = []
    for index in range(options.rounds):
        for value in THRESHOLDS:
            elapsed, geometry = evaluate(value)
            cloud = geometry.pointcloud
            if cloud is None or len(cloud.points) != POINT_COUNT:
                raise AssertionError("Timed recompute did not produce the required point count")
            trials.append({"round": index+1, "threshold_x_m": value, "elapsed_ms": elapsed})
            print("TIMED", index+1, value, elapsed, flush=True)
    validation = []
    for value in THRESHOLDS:
        elapsed, geometry = evaluate(value)
        validation.append(validate(geometry.pointcloud, positions, classes, intensity, value))
    for item in validation:
        print("VALIDATED", json.dumps(item), flush=True)
    summary = {
        "blender": bpy.app.version_string,
        "build_hash": bpy.app.build_hash.decode("ascii"),
        "source": SOURCE_URL,
        "license": "CC BY 4.0, Tokyo Metropolitan Government Bureau of Digital Services",
        "archive_sha256": ARCHIVE_SHA256,
        "points": POINT_COUNT,
        "coordinate_origin": origin,
        "scope": "Stock dependency-graph update after changing a local-X point-selection threshold; no viewport draw or export included",
        "trials": trials,
        "median_ms_by_threshold": {
            str(value): statistics.median(t["elapsed_ms"] for t in trials if t["threshold_x_m"] == value)
            for value in THRESHOLDS
        },
        "validation": validation,
    }
    with options.output.open("x", encoding="utf-8") as output:
        json.dump(summary, output, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
