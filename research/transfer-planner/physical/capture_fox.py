# SPDX-License-Identifier: MIT
"""Capture byte-change ranges of sampled public Fox animation channel values."""

import bisect
import functools
import json
import math
from pathlib import Path
import struct
import sys


def blend(a, b, fraction, rotation):
    if not rotation:
        return tuple(x + fraction * (y - x) for x, y in zip(a, b))
    dot = sum(x * y for x, y in zip(a, b))
    if dot < 0:
        b = tuple(-y for y in b)
        dot = -dot
    if dot > 0.9995:
        value = tuple(x + fraction * (y - x) for x, y in zip(a, b))
    else:
        angle = math.acos(min(1.0, dot))
        scale = 1.0 / math.sin(angle)
        wa = math.sin((1.0 - fraction) * angle) * scale
        wb = math.sin(fraction * angle) * scale
        value = tuple(wa * x + wb * y for x, y in zip(a, b))
    length = math.sqrt(sum(x * x for x in value))
    return tuple(x / length for x in value)


def evaluate(times, values, time, rotation):
    if time <= times[0]:
        return values[0]
    if time >= times[-1]:
        return values[-1]
    upper = bisect.bisect_right(times, time)
    low = upper - 1
    return blend(values[low], values[upper], (time - times[low]) / (times[upper] - times[low]), rotation)


def animations(folder):
    asset = json.loads((folder / "Fox.gltf").read_bytes())
    binary = (folder / "Fox.bin").read_bytes()
    if asset["buffers"] != [{"uri": "Fox.bin", "byteLength": len(binary)}]:
        raise ValueError("expected the pinned Fox buffer")
    default = []
    for node in asset["nodes"]:
        default.append({
            "translation": tuple(node.get("translation", (0, 0, 0))),
            "rotation": tuple(node.get("rotation", (0, 0, 0, 1))),
            "scale": tuple(node.get("scale", (1, 1, 1))),
        })

    @functools.cache
    def access(index):
        row = asset["accessors"][index]
        view = asset["bufferViews"][row["bufferView"]]
        width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[row["type"]]
        if row["componentType"] != 5126 or view["buffer"] != 0 or "sparse" in row:
            raise ValueError("unexpected animation accessor")
        offset = view.get("byteOffset", 0) + row.get("byteOffset", 0)
        stride = view.get("byteStride", 4 * width)
        if stride < 4 * width or offset + (row["count"] - 1) * stride + 4 * width > len(binary):
            raise ValueError("animation accessor out of bounds")
        return tuple(struct.unpack_from(f"<{width}f", binary, offset + i * stride) for i in range(row["count"]))

    for animation in asset["animations"]:
        streams = []
        for channel in animation["channels"]:
            sampler = animation["samplers"][channel["sampler"]]
            node, path = channel["target"]["node"], channel["target"]["path"]
            if sampler.get("interpolation", "LINEAR") != "LINEAR" or path not in default[node]:
                raise ValueError("unexpected animation interpolation or channel")
            times = tuple(x[0] for x in access(sampler["input"]))
            values = access(sampler["output"])
            if len(times) != len(values) or any(a >= b for a, b in zip(times, times[1:])):
                raise ValueError("unexpected animation sample order")
            streams.append((node, path, times, values))
        yield animation["name"], default, streams


def frames(default, streams, instances):
    duration = max(times[-1] for _, _, times, _ in streams)
    for frame in range(181):
        rows = []
        for instance in range(instances):
            time = (frame / 60.0 + duration * instance / instances) % duration
            values = [node.copy() for node in default]
            for node, path, times, samples in streams:
                values[node][path] = evaluate(times, samples, time, path == "rotation")
            for node in values:
                values10 = node["translation"] + node["rotation"] + node["scale"]
                rows.append(struct.pack("<10f24x", *values10))
        yield rows


def emit(name, all_frames, extent):
    print("case", name, extent, extent)
    print("allow", 0, extent)
    before = next(all_frames)
    for i, after in enumerate(all_frames, 1):
        print("frame", i)
        first = None
        for at in range(extent + 1):
            if at < extent and before[at] != after[at]:
                if first is None:
                    first = at
            elif first is not None:
                print("dirty", first, at)
                first = None
        print("endframe")
        before = after
    print("endcase")


def main():
    source = Path(sys.argv[1])
    print("PBTRACE1 64")
    for name, default, streams in animations(source):
        emit("fox_" + name.lower(), frames(default, streams, 1), len(default))
        if name == "Walk":
            emit("fox_walk_replicated_64", frames(default, streams, 64), len(default) * 64)


if __name__ == "__main__":
    main()
