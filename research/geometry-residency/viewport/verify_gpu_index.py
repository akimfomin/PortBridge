"""Verify browser-free Blender GPU output on the pinned Tokyo point columns."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import gpu
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stable_gpu_index import EDITED, SOURCE_ID_MASK, StablePartition, cpu_partition


POINT_COUNT = 6_385_097


def load_columns(path):
    with path.open("rb") as handle:
        header = handle.read(8)
    magic, count = struct.unpack("<4sI", header)
    if magic != b"PBPC" or count != POINT_COUNT or path.stat().st_size != 8 + count * 20:
        raise ValueError("expected the pinned Tokyo CPU input export")
    position = np.memmap(path, mode="r", dtype="<f4", offset=8, shape=(count, 3))
    point_class = np.memmap(path, mode="r", dtype="<i4", offset=8 + count * 12, shape=count)
    intensity = np.memmap(path, mode="r", dtype="<i4", offset=8 + count * 16, shape=count)
    return position, point_class, intensity


def observe(partition, positions, point_class, intensity, threshold):
    partition.edit(threshold)
    packed = partition.read_indices()
    expected = cpu_partition(positions[:, 0], point_class, threshold)
    if not np.array_equal(packed, expected):
        mismatch = int(np.flatnonzero(packed != expected)[0])
        raise AssertionError(f"first ordered identity mismatch at logical rank {mismatch}")
    ids = packed & SOURCE_ID_MASK
    edit = (packed & EDITED) != 0
    outgoing_pos = positions[ids].copy()
    outgoing_pos[edit, 2] = 0
    outgoing_class = point_class[ids].copy()
    outgoing_class[edit] = 2
    summary = hashlib.sha256()
    for view in (ids, outgoing_class, intensity[ids], outgoing_pos):
        summary.update(view)
    return summary.hexdigest()


def check_boundaries():
    for count in (1, 4, 31, 32, 33, 511, 512, 513, 65_535, 65_536, 65_537):
        x = np.arange(count, dtype=np.float32)
        point_class = (np.arange(count, dtype=np.int32) % 3 > 0).astype(np.int32)
        partition = StablePartition(x, point_class)
        for threshold in (-1, 0, count // 3, count + 1):
            partition.edit(threshold)
            if not np.array_equal(partition.read_indices(), cpu_partition(x, point_class, threshold)):
                raise AssertionError((count, threshold))
    return 44


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("expected", type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    gpu.init()
    if gpu.platform.backend_type_get() != "VULKAN":
        raise RuntimeError("launch Blender with --gpu-backend vulkan")
    print(json.dumps({"renderer": gpu.platform.renderer_get(), "synthetic_checks": check_boundaries()}))
    positions, point_class, intensity = load_columns(args.input)
    position_storage = gpu.types.GPUStorageBuf(np.ascontiguousarray(positions))
    class_storage = gpu.types.GPUStorageBuf(np.ascontiguousarray(point_class))
    partition = StablePartition.from_gpu(position_storage, class_storage, len(positions), stride=3)
    packed_rows = np.empty((len(positions), 4), dtype=np.float32)
    packed_rows[:, :3] = positions
    packed_rows[:, 3] = point_class
    packed_storage = gpu.types.GPUStorageBuf(packed_rows)
    packed_partition = StablePartition.from_packed_rows(packed_storage, len(positions))
    expected = json.loads(args.expected.read_text(encoding="utf-8"))["validation"]
    layouts = (("column", partition), ("packed", packed_partition))
    for layout, current in layouts:
        for case in expected:
            threshold = case["threshold_x_m"]
            actual = observe(current, positions, point_class, intensity, threshold)
            if actual != case["output_sha256"]:
                raise AssertionError((layout, threshold, actual, case["output_sha256"]))
            print(json.dumps({"layout": layout, "threshold": threshold, "exact_sha256": actual,
                              "rows": current.count, "scratch_bytes": current.scratch_bytes}))


if __name__ == "__main__":
    main()
