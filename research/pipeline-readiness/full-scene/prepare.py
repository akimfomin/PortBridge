"""Prepare the pinned ASWF chess scene and compile fresh Vulkan shader recipes."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
from urllib.request import urlopen

from PIL import Image


ROOT = Path(__file__).resolve().parent
ASSET_COMMIT = "e124e8d8d7330a5372bc2b4d00d39a4a9d7997ea"
ASSET = "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/" + ASSET_COMMIT + "/Models/ABeautifulGame/"
TEX_SIZE = 512


def digest(data):
    return hashlib.sha256(data).hexdigest()


def retrieve(destination, dirname, name):
    if not re.fullmatch(r"[0-9A-Za-z_.-]+", name) or name in (".", ".."):
        raise ValueError(f"Invalid source filename {name!r}")
    url = ASSET + dirname + name
    output = destination / name
    if not output.exists():
        with urlopen(url, timeout=25) as response:
            content = response.read(24_000_001)
        if not 0 < len(content) <= 24_000_000:
            raise ValueError(f"Unexpected source size for {name}")
        output.write_bytes(content)
    return [url, digest(output.read_bytes())]


def compose_scene(output):
    output.mkdir(parents=True, exist_ok=True)
    source = output / "original"
    source.mkdir(exist_ok=True)
    sources = {name: retrieve(source, dirname, name) for name, dirname in
               [("ABeautifulGame.gltf", "glTF/"), ("README.md", "")]}
    model = json.loads((source / "ABeautifulGame.gltf").read_text(encoding="utf-8"))
    if len(model["buffers"]) != 1 or len(model["nodes"]) != 49 or len(model["materials"]) != 15:
        raise ValueError("Pinned model shape mismatch")
    names = [model["buffers"][0]["uri"], *(image["uri"] for image in model["images"])]
    with ThreadPoolExecutor(max_workers=5) as pool:
        sources.update(zip(names, pool.map(lambda n: retrieve(source, "glTF/", n), names)))
    raw = (source / names[0]).read_bytes()
    if len(raw) != model["buffers"][0]["byteLength"]:
        raise ValueError("Geometry buffer length mismatch")

    def contents(index, vector, formats):
        a = model["accessors"][index]
        view = model["bufferViews"][a["bufferView"]]
        fmt = {5126: "f", 5125: "I", 5123: "H"}[a["componentType"]]
        kinds = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}
        width = kinds[a["type"]]
        if width != vector or fmt not in formats or view["buffer"] or "sparse" in a:
            raise ValueError("Unexpected pinned accessor")
        item = struct.Struct("<" + fmt * width)
        offset = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = view.get("byteStride", item.size)
        end = offset + (a["count"] - 1) * stride + item.size
        if a["count"] < 1 or stride < item.size or end > view.get("byteOffset", 0) + view["byteLength"] or end > len(raw):
            raise ValueError("Invalid accessor bounds")
        return (item.unpack_from(raw, offset + i * stride) for i in range(a["count"]))

    vertices, indices = bytearray(), bytearray()
    geometry, packets = {}, []
    def texture_id(info):
        return 0 if info is None else 1 + model["textures"][info["index"]]["source"]

    def walk(index, translation=(0, 0, 0)):
        node = model["nodes"][index]
        if "matrix" in node or "scale" in node:
            raise ValueError("Unexpected node transform")
        position = tuple(a + b for a, b in zip(translation, node.get("translation", (0, 0, 0))))
        rotation = node.get("rotation", (0, 0, 0, 1))
        if "rotation" in node and "children" in node:
            raise ValueError("Unexpected rotated parent")
        for primitive in model["meshes"][node["mesh"]]["primitives"]:
            if primitive.get("mode", 4) != 4 or set(primitive["attributes"]) != {"POSITION", "NORMAL", "TEXCOORD_0"}:
                raise ValueError("Unexpected primitive topology or attributes")
            attrib = primitive["attributes"]
            key = (attrib["POSITION"], attrib["NORMAL"], attrib["TEXCOORD_0"], primitive["indices"])
            if key not in geometry:
                vertex_base = len(vertices) // 32
                first_index = len(indices) // 4
                for vertex, normal, uv in zip(contents(key[0], 3, "f"), contents(key[1], 3, "f"),
                                               contents(key[2], 2, "f"), strict=True):
                    vertices.extend(struct.pack("<8f", *vertex, *normal, *uv))
                vertex_count = len(vertices) // 32 - vertex_base
                for (value,) in contents(key[3], 1, "HI"):
                    if value >= vertex_count:
                        raise ValueError("Index outside primitive's vertices")
                    indices.extend(struct.pack("<I", value))
                geometry[key] = first_index, len(indices) // 4 - first_index, vertex_base
            material = model["materials"][primitive["material"]]
            pbr = material["pbrMetallicRoughness"]
            transmission = material.get("extensions", {}).get("KHR_materials_transmission", {}).get("transmissionFactor", 0)
            distances = texture_id(pbr.get("metallicRoughnessTexture"))
            packets.append((bool(transmission), position, struct.pack(
                "<5I7f4I4f", *geometry[key], bool(transmission), primitive["material"], *position, *rotation,
                texture_id(pbr.get("baseColorTexture")), texture_id(material.get("normalTexture")),
                distances, 0, *pbr.get("baseColorFactor", (1, 1, 1, 1))
            )))
        for child in node.get("children", []):
            walk(child, position)

    for root in model["scenes"][model["scene"]]["nodes"]:
        walk(root)
    if len(packets) != 49:
        raise ValueError("Expected all 49 scene instances")
    with (output / "scene.bin").open("wb") as f:
        f.write(struct.pack("<4s5I", b"PBSC", len(vertices) // 32, len(indices) // 4,
                            len(packets), len(model["images"]) + 1, TEX_SIZE))
        f.write(vertices)
        f.write(indices)
        for _, _, packet in packets:
            f.write(packet)
        f.write(b"\xff" * TEX_SIZE * TEX_SIZE * 4)
        for image in model["images"]:
            with Image.open(source / image["uri"]) as decoded:
                f.write(decoded.convert("RGBA").resize((TEX_SIZE, TEX_SIZE), Image.Resampling.BILINEAR).tobytes())
    manifest = {
        "asset_commit": ASSET_COMMIT, "sources": sources,
        "asset_license": "CC BY 4.0, ASWF (2020) / original model MaterialX Project, Ed Mackey (2022) glTF conversion",
        "scene_sha256": digest((output / "scene.bin").read_bytes()),
        "texture_size": TEX_SIZE, "draws": len(packets), "unique_geometry": len(geometry),
        "indexed_triangles": sum(struct.unpack_from("<I", p, 4)[0] // 3 for _, _, p in packets),
        "vertices": len(vertices) // 32, "indices": len(indices) // 4,
    }
    (output / "scene-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print({k: v for k, v in manifest.items() if k != "sources"})


def compile_shader(output, dxc, validator, salt):
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / "scene.hlsl"
    for stage, entry in (("vs", "vertex"), ("ps", "pixel")):
        target = output / (stage + ".spv")
        subprocess.run([dxc, "-spirv", "-fspv-target-env=vulkan1.3", "-O3", "-T", stage + "_6_0", "-E", entry,
                        "-D", f"CACHE_KEY={salt}", "-Fo", target, source], check=True)
        subprocess.run([validator, "--target-env", "vulkan1.3", target], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    scene = sub.add_parser("scene")
    scene.add_argument("output", type=Path)
    shader = sub.add_parser("shader")
    shader.add_argument("output", type=Path)
    shader.add_argument("--dxc", type=Path, required=True)
    shader.add_argument("--validator", type=Path, required=True)
    shader.add_argument("--salt", type=int, choices=range(1, 1_000_000), required=True, metavar="1..999999")
    args = parser.parse_args()
    if args.action == "scene":
        compose_scene(args.output)
    else:
        compile_shader(args.output, args.dxc, args.validator, args.salt)


if __name__ == "__main__":
    main()
