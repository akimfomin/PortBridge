# SPDX-License-Identifier: MIT
"""Render one audited raylib/XCL SPIR-V and compare with its native OpenGL reference."""
import argparse
import json
import re
import struct
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np

from run_probe import reflect, sha


def classify_access(assembly):
    defs = {}
    instructions = []
    for line in assembly.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        match = re.fullmatch(r"(?:(%\d+) = )?(Op\w+)(?: (.*))?", line)
        if not match:
            raise ValueError("Unexpected SPIR-V assembly syntax")
        result, opcode, operands = match.groups()
        args = (operands or "").split()
        instructions.append((result, opcode, args))
        if result:
            defs[result] = (opcode, args)
    if any(op.startswith("OpAtomic") or op in {"OpCopyMemory", "OpCopyMemorySized", "OpImageWrite"} for _, op, _ in instructions):
        raise ValueError("Unexpected storage side effect")
    physical_types = {r: a[1] for r, op, a in instructions if op == "OpTypePointer" and a[0] == "PhysicalStorageBuffer"}
    uints = {r for r, op, a in instructions if op == "OpTypeInt" and a == ["32", "0"]}
    constants = {r: int(a[1], 0) for r, op, a in instructions if op == "OpConstant" and a[0] in uints}
    push_vars = {r for r, op, a in instructions if op == "OpVariable" and a[1] == "PushConstant"}
    if len(push_vars) != 1:
        raise ValueError("Expected one push block")
    strides4 = {a[0] for _, op, a in instructions if op == "OpDecorate" and a[1:] == ["ArrayStride", "4"]}
    offsets0 = {a[0] for _, op, a in instructions if op == "OpMemberDecorate" and a[1:] == ["0", "Offset", "0"]}
    root_fields, root_values, structures, indexed = {}, {}, {}, {}
    for r, op, a in instructions:
        if op == "OpAccessChain" and a[1] in push_vars:
            if len(a) != 3 or a[2] not in constants or not 0 <= constants[a[2]] < 5:
                raise ValueError("Unbounded push field")
            root_fields[r] = constants[a[2]]
        elif op == "OpLoad" and a[1] in root_fields:
            root_values[r] = root_fields[a[1]]
        if r and a and a[0] in physical_types:
            pointee = physical_types[a[0]]
            if op == "OpBitcast" and a[1] in root_values:
                member_op, members = defs[pointee]
                if member_op != "OpTypeStruct" or len(members) != 1 or pointee not in offsets0:
                    raise ValueError("Unreviewed physical structure")
                arr = members[0]
                arr_op, elements = defs[arr]
                if arr_op != "OpTypeRuntimeArray" or elements[0] not in uints or arr not in strides4:
                    raise ValueError("Physical storage must be a packed uint32 array")
                structures[r] = root_values[a[1]]
            elif op == "OpInBoundsAccessChain" and a[1] in structures:
                index = constants.get(a[3]) if len(a) == 4 else None
                slot = structures[a[1]]
                if (pointee not in uints or constants.get(a[2]) != 0 or index is None or
                        not 0 <= index < (128 if slot == 0 else 64)):
                    raise ValueError("Physical access exceeds the known root range")
                indexed[r] = (slot, index)
            else:
                raise ValueError("Unreviewed physical pointer producer " + op)
    loads = Counter()
    for r, op, a in instructions:
        uses = [x for x in a if x in indexed or x in structures]
        if not uses or op in {"OpName", "OpDecorate"}:
            continue
        if op == "OpInBoundsAccessChain" and r in indexed and uses == [a[1]]:
            continue
        if (op == "OpLoad" and a[0] in uints and a[1] in indexed and uses == [a[1]]
                and a[2:] == ["Aligned|NonPrivatePointer", "4"]):
            loads[indexed[a[1]]] += 1
            continue
        raise ValueError("Unreviewed access through physical pointer " + op)
    if not loads or any(slot != 0 for slot, _ in loads):
        raise ValueError("Ray scene expected loads only from the incoming SGPR file")
    return {"read_only": True, "statically_loaded_sgpr_indices": sorted(index for _, index in loads),
            "static_load_instructions": sum(loads.values())}


def compare(a, b):
    if a.ndim != 2 or a.shape[1] != 4 or b.shape != a.shape:
        raise ValueError("Wrong picture size")
    if not (np.isfinite(a).all() and np.isfinite(b).all()) or np.any(np.all(a == -3, axis=1)):
        raise ValueError("Nonfinite or uncovered pixel")
    error = np.max(np.abs(a.astype(np.float64) - b.astype(np.float64)), axis=1)
    return {"bit_equal_pixels": int(np.all(a.view(np.uint32) == b.view(np.uint32), axis=1).sum()),
            "pixels": len(error), "mean_abs_rgb": float(np.abs(a[:, :3].astype(np.float64) - b[:, :3]).mean()),
            "p50_max_channel_abs": float(np.quantile(error, .5)), "p99_max_channel_abs": float(np.quantile(error, .99)),
            "max_channel_abs": float(np.max(error))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("probe", "vertex", "fragment", "dis", "val", "camera", "out"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--capture-executable", action="store_true", help="query the actual PSO used for timed draws")
    parser.add_argument("--original-source", action="store_true", help="run the original raylib Vulkan GLSL input")
    args = parser.parse_args()
    scene = json.loads((args.camera / "scene.json").read_text(encoding="utf-8"))
    sgprs = args.camera / "sgprs.bin"
    gl_file = args.camera / "gl.rgba32f"
    w, h = scene.get("width", scene.get("size")), scene.get("height", scene.get("size"))
    if (scene["scene"] != "raymarching" or (w, h) not in {(16, 16), (96, 96), (800, 450)} or
            gl_file.stat().st_size != 16 * w * h or
            sha(sgprs) != scene["sgprs_sha256"] or sha(gl_file) != scene["gl_image"]["sha256"]):
        raise ValueError("Camera references or hashes do not match")
    profile = "source" if args.original_source else "xcl-ray-roots"
    layout = reflect(args.fragment, profile, args.dis, args.val)
    subprocess.run([args.val, "--target-env", "vulkan1.3", args.vertex], check=True, timeout=20)
    if args.original_source:
        if (sha(args.fragment) != "ccf143cc12546ad771c4d3a4d75c9e004a3c41686dd11826cc03c486f1d198b8" or
                layout["push_offsets"] != [0, 16, 28, 32]):
            raise ValueError("Expected the pinned native raymarching module and control block")
        safety = {"buffer_device_address": False}
    else:
        assembly = subprocess.run([args.dis, "--raw-id", args.fragment], check=True, timeout=20,
                                  capture_output=True, encoding="utf-8").stdout
        safety = classify_access(assembly)
    evidence = {"scene_controls": scene["controls"], "references": {"gl": sha(gl_file), "sgprs": sha(sgprs)},
                "fragment": args.fragment.name, "fragment_sha256": sha(args.fragment), "vertex_sha256": sha(args.vertex),
                "worker_sha256": sha(args.probe), "layout": layout, "physical_access": safety}
    if not args.validate_only:
        image = args.out.with_suffix(".rgba32f")
        if args.out.exists() or image.exists():
            raise ValueError("Output already exists")
        with tempfile.TemporaryDirectory() as td:
            camera_input = sgprs
            if args.original_source:
                controls = scene["controls"]
                data = struct.pack("<3f4x3ff2f", *controls["viewEye"], *controls["viewCenter"],
                                   controls["runTime"], *controls["resolution"])
                camera_input = Path(td) / "native-camera.bin"
                camera_input.write_bytes(data)
                evidence["native_camera_sha256"] = sha(camera_input)
            cmd = [args.probe.resolve(), args.vertex.resolve(), args.fragment.resolve(), args.device,
                   profile, camera_input.resolve(), image.resolve(), f"{w}x{h}"]
            if args.capture_executable:
                cmd.append("capture")
            result = subprocess.run(cmd, capture_output=True, encoding="utf-8", timeout=45)
        if result.returncode:
            raise RuntimeError(f"Worker exited {result.returncode}: {result.stderr.strip()}")
        evidence["draw"] = json.loads(result.stdout)
        pixels = np.fromfile(image, dtype="<f4").reshape(-1, 4)
        evidence["vs_native_gl"] = compare(pixels, np.fromfile(gl_file, dtype="<f4").reshape(-1, 4))
        evidence["output_sha256"] = sha(image)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(evidence, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
