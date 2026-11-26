# SPDX-License-Identifier: MIT
"""Verify the shader/layout contract, then compile and inspect one Vulkan graphics PSO."""
import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reflect(path, profile, disassembler, validator):
    subprocess.run([validator, "--target-env", "vulkan1.3", path], timeout=20, check=True)
    dis = subprocess.run([disassembler, "--raw-id", path], timeout=20, check=True,
                         encoding="utf-8", stdout=subprocess.PIPE).stdout
    declarations = dict(re.findall(r"^\s*(%\d+) = (OpType.*|OpVariable .*)$", dis, re.M))
    decorations = {}
    for var, key, value in re.findall(r"OpDecorate (%\d+) (DescriptorSet|Binding) (\d+)", dis):
        decorations.setdefault(var, {})[key] = int(value)
    locations = {v: int(n) for v, n in re.findall(r"OpDecorate (%\d+) Location (\d+)", dis)}
    builtins = dict(re.findall(r"OpDecorate (%\d+) BuiltIn (\w+)", dis))
    push_offsets = []
    resources = []
    varyings = []
    for var, op in declarations.items():
        if not op.startswith("OpVariable "):
            continue
        _, ptr, storage, *_ = op.split()
        if storage in ("Input", "Output"):
            if var in builtins:
                if storage != "Input" or builtins[var] not in {"FragCoord", "SubgroupLocalInvocationId"}:
                    raise ValueError("Unexpected built-in stage interface")
            else:
                location = locations.get(var)
                expected = (4 if location == 0 else None) if storage == "Output" else (
                    {0: 2, 1: 4}.get(location) if profile == "source" else None)
                data = declarations[declarations[ptr].split()[2]].split()
                if (not expected or len(data) != 3 or data[0] != "OpTypeVector" or int(data[2]) != expected
                        or declarations[data[1]] != "OpTypeFloat 32"):
                    raise ValueError("Stage varying does not match the reviewed vertex / color interface")
                varyings.append({"direction": storage, "location": location, "float32_components": expected})
        if storage == "PushConstant":
            struct = declarations[ptr].split()[2]
            offsets = re.findall(r"OpMemberDecorate " + re.escape(struct) + r" (\d+) Offset (\d+)", dis)
            push_offsets = [int(n) for _, n in sorted(offsets, key=lambda x: int(x[0]))]
        if storage in ("StorageBuffer", "Uniform"):
            raise ValueError("Unexpected descriptor storage class " + storage)
        if storage == "UniformConstant":
            # Translated bindless fragment programs alias numeric sample types of one image slot.
            resource = declarations[declarations[ptr].split()[2]]
            if not resource.startswith("OpTypeRuntimeArray "):
                raise ValueError("Expected a runtime descriptor array")
            image = declarations[resource.split()[1]].split()
            if image[0] != "OpTypeImage" or image[2:] != ["2D", "0", "0", "0", "1", "Unknown"]:
                raise ValueError("Expected a sampled 2D image")
            slot = decorations.get(var, {})
            if slot != {"DescriptorSet": 0, "Binding": 0}:
                raise ValueError("Unexpected image descriptor set or binding")
            resources.append({"set": 0, "binding": 0, "type": "sampled_image_2d", "scalar": declarations[image[1]]})
    caps = re.findall(r"OpCapability (\w+)", dis)
    verified_caps = {"Shader", "Int64", "GroupNonUniform", "GroupNonUniformBallot",
                     "GroupNonUniformShuffle", "GroupNonUniformQuad", "GroupNonUniformArithmetic",
                     "RuntimeDescriptorArray", "SampledImageArrayNonUniformIndexing",
                     "VulkanMemoryModel", "PhysicalStorageBufferAddresses", "DemoteToHelperInvocation"}
    if set(caps) - verified_caps:
        raise ValueError(f"Unaudited module capabilities: {set(caps) - verified_caps}")
    if profile == "source":
        if resources or not push_offsets or max(push_offsets) >= 64 or set(caps) != {"Shader"}:
            raise ValueError("Source fragment does not match the reviewed raylib push layout")
    else:
        if push_offsets != [0, 8, 16, 24, 32] or "OpMemoryModel PhysicalStorageBuffer64 Vulkan" not in dis:
            raise ValueError("Missing translated five-root BDA contract")
        if profile == "xcl-ray-roots" and resources:
            raise ValueError("Ray root layout has no descriptors")
        if profile == "xcl-nerf-roots" and sorted(x["scalar"] for x in resources) != [
                "OpTypeFloat 32", "OpTypeInt 32 0", "OpTypeInt 32 1"]:
            raise ValueError("NeRF layout must alias three numeric interpretations of binding zero")
    if not re.search(r'OpEntryPoint Fragment %\d+ "main"', dis):
        raise ValueError("No fragment main")
    if not any(v["direction"] == "Output" for v in varyings):
        raise ValueError("No color attachment")
    opcodes = Counter(re.findall(r"^\s*(?:%\d+ = )?(Op\w+)\b", dis, re.M))
    tracked = {"OpLoopMerge", "OpSelectionMerge", "OpLabel", "OpBitwiseAnd", "OpBitwiseOr",
               "OpShiftRightLogical", "OpShiftLeftLogical"}
    structure = {op: n for op, n in opcodes.items() if op in tracked or op.startswith("OpGroupNonUniform")}
    return {"capabilities": caps, "push_offsets": push_offsets, "resources": resources,
            "varyings": varyings, "structure": structure}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("probe", "vertex", "fragment", "dis", "val", "out"):
        p.add_argument("--" + name, required=True, type=Path)
    p.add_argument("--device", required=True)
    p.add_argument("--profile", required=True, choices=["source", "xcl-ray-roots", "xcl-nerf-roots"])
    p.add_argument("--validate-only", action="store_true")
    options = p.parse_args()
    if options.fragment.stat().st_size > 8 * 1024 * 1024 or options.vertex.stat().st_size > 1024 * 1024:
        p.error("Input exceeds the reviewed size limit")
    layout = reflect(options.fragment, options.profile, options.dis, options.val)
    subprocess.run([options.val, "--target-env", "vulkan1.3", options.vertex], timeout=20, check=True)
    result = {"profile": options.profile, "fragment_name": options.fragment.name,
              "fragment_sha256": sha(options.fragment), "vertex_sha256": sha(options.vertex),
              "probe_sha256": sha(options.probe), "validator_sha256": sha(options.val),
              "disassembler_sha256": sha(options.dis), "layout": layout, "physical_pipeline": None}
    if not options.validate_only:
        cmd = [options.probe.resolve(), options.vertex.resolve(), options.fragment.resolve(), options.device, options.profile]
        physical = subprocess.run(cmd, timeout=45, check=True, capture_output=True)
        result["physical_pipeline"] = json.loads(physical.stdout)
    with options.out.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
