# SPDX-License-Identifier: MIT
"""Build, prepare, and run the bounded Vulkan pipeline-readiness fixture."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
from time import monotonic


ROOT = Path(__file__).resolve().parent
CPP = ROOT / "native_probe.cpp"
SHADER = ROOT / "native_recipe.hlsl"
MODES = ("cold", "warm", "fifo", "demand-first", "reserved")
ORDERS = (MODES, tuple(reversed(MODES)))
RECIPES = 6
VK_COMPILE_REQUIRED = 1000297000
RUN_SECONDS = 25


def digest(data):
    return hashlib.sha256(data).hexdigest()


def call(command, timeout=10):
    return subprocess.run(command, check=True, capture_output=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def build(output, clang, headers, dlltool):
    output.mkdir(exist_ok=False)
    symbols = sorted(set(re.findall(r"\b(vk[A-Z]\w+)\(", CPP.read_text(encoding="utf-8"))))
    exports = output / "vulkan-1.def"
    exports.write_text("LIBRARY vulkan-1.dll\nEXPORTS\n" + "\n".join(symbols) + "\n", encoding="ascii")
    library = output / "libvulkan-1.a"
    call([dlltool, "-m", "i386:x86-64", "-d", exports, "-l", library])
    call([clang, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror", "-static",
          "-I", headers, CPP, library, "-o", output / "native_probe.exe"], timeout=30)


def module_identity(path, salt):
    data = path.read_bytes()
    if not 20 <= len(data) <= 4096 or len(data) % 4:
        raise ValueError("Invalid shader size")
    words = list(struct.unpack(f"<{len(data) // 4}I", data))
    if words[0] != 0x07230203:
        raise ValueError("Invalid SPIR-V header")
    modified = 0
    position = 5
    while position < len(words):
        size, op = words[position] >> 16, words[position] & 0xffff
        if not size or position + size > len(words):
            raise ValueError("Invalid SPIR-V instruction")
        if op == 43 and size == 4 and words[position + 3] == salt:
            modified += 1
            words[position + 3] = 0
        position += size
    if modified != 1:
        raise ValueError("Expected exactly one salt operand in SPIR-V")
    return {"sha256": digest(data), "shape": digest(struct.pack(f"<{len(words)}I", *words))}


def prepare(output, dxc, validator, campaign, blocks):
    output.mkdir(exist_ok=False)
    rows = []
    for index in range(blocks):
        order = ORDERS[index % len(ORDERS)]
        for mode in order:
            target = output / f"{index}-{mode}"
            target.mkdir()
            salt = 1_000_000 * campaign + 1000 * index + 100 * MODES.index(mode)
            modules = []
            for recipe in range(RECIPES):
                filename = target / f"{recipe}.spv"
                call([dxc, "-spirv", "-fspv-target-env=vulkan1.1", "-O3", "-T", "cs_6_0",
                      "-E", "main", "-D", f"FIXTURE_SALT={salt + recipe}u", "-Fo", filename, SHADER])
                call([validator, "--target-env", "vulkan1.1", filename])
                modules.append(module_identity(filename, salt + recipe))
            rows.append({"mode": mode, "directory": target.name, "salt": salt, "modules": modules})
    manifest = {"campaign": campaign, "source": digest(SHADER.read_bytes()),
                "dxc": digest(dxc.read_bytes()), "validator": digest(validator.read_bytes()), "cases": rows}
    verify(output, manifest)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def verify(prepared, manifest):
    cases = manifest["cases"]
    if (manifest["source"] != digest(SHADER.read_bytes()) or not len(MODES) <= len(cases) <= 4 * len(MODES)
            or len(cases) % len(MODES)):
        raise ValueError("Unexpected fixture source or block count")
    hashes, salts, shapes = set(), set(), set()
    for number, case in enumerate(cases):
        block, index = divmod(number, len(MODES))
        mode = ORDERS[block % len(ORDERS)][index]
        path = prepared / f"{block}-{mode}"
        base = 1_000_000 * manifest["campaign"] + 1000 * block + 100 * MODES.index(mode)
        if case["directory"] != path.name or case["mode"] != mode or case["salt"] != base:
            raise ValueError("Unexpected experiment order or recipe identity")
        found = [module_identity(path / f"{i}.spv", base + i) for i in range(RECIPES)]
        if found != case["modules"]:
            raise ValueError("Prepared SPIR-V differs from the manifest")
        for i, module in enumerate(found):
            hashes.add(module["sha256"])
            shapes.add(module["shape"])
            salts.add(base + i)
    if len(shapes) != 1 or len(hashes) != len(salts) or len(salts) != len(cases) * RECIPES:
        raise ValueError("Fixture recipes are reused or have different shader shapes")


def verify_report(sample, mode):
    expected_ids = [RECIPES - 1] if mode in ("cold", "warm") else list(range(RECIPES))
    jobs = sample["jobs"]
    if ([job["id"] for job in jobs] != expected_ids or sample["mode"] != mode
            or sample["verified_words"] != 512 or sample["intact_guards"] != 2
            or not 0 < sample["dispatch_and_verify_ms"] <= sample["demand_to_verified_ms"] <= sample["full_work_ms"]):
        raise ValueError("Unexpected measured arm or output")
    for job in jobs:
        if (job["preflight_result"] != (0 if mode == "warm" else VK_COMPILE_REQUIRED)
                or not job["feedback_flags"] & 1
                or bool(job["feedback_flags"] & 2) != (mode == "warm")
                or not 0 <= job["requested_ms"] <= job["entered_ms"] <= job["returned_ms"]
                or not job["cpu_wall_ms"] > 0):
            raise ValueError("Invalid creation timeline or measurement qualification")


def run(prepared, executable, adapter, output):
    # Record any inherited loader overrides as a failure rather than silently choosing an ICD or layer.
    overrides = sorted(name for name in os.environ if name.startswith(("VK_LOADER_", "VK_DRIVER_", "VK_LAYER_"))
                       or name in ("VK_ICD_FILENAMES", "VK_INSTANCE_LAYERS", "VK_ADD_DRIVER_FILES"))
    if overrides:
        raise ValueError("Unset Vulkan overrides for this isolated run: " + ", ".join(overrides))
    manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    verify(prepared, manifest)
    identity = None
    deadline = monotonic() + RUN_SECONDS
    with output.open("x", encoding="utf-8") as out:
        input_hash = digest((prepared / "manifest.json").read_bytes())
        out.write(json.dumps({"manifest_sha256": input_hash, "probe_sha256": digest(executable.read_bytes()),
                              "adapter": adapter, "bounded_seconds": RUN_SECONDS}) + "\n")
        for case in manifest["cases"]:
            limit = min(3, deadline - monotonic())
            if limit <= 0:
                raise TimeoutError("The full experiment reached its deadline")
            try:
                process = call([executable, case["mode"], adapter, prepared / case["directory"],
                                str(case["salt"])], timeout=limit)
                sample = json.loads(process.stdout)
                verify_report(sample, case["mode"])
                device = tuple(sample[key] for key in ("vendor", "device", "driver", "api"))
                if identity is None:
                    identity = device
                elif identity != device:
                    raise ValueError("Adapter or driver changed between arms")
                out.write(json.dumps({"case": case["directory"], "salt": case["salt"], **sample}) + "\n")
            except subprocess.CalledProcessError as error:
                out.write(json.dumps({"case": case["directory"], "error": error.stderr.strip()}) + "\n")
                raise
            out.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    tools = commands.add_parser("build")
    tools.add_argument("output", type=Path)
    tools.add_argument("--clang", type=Path, required=True)
    tools.add_argument("--headers", type=Path, required=True)
    tools.add_argument("--dlltool", type=Path, required=True)
    inputs = commands.add_parser("prepare")
    inputs.add_argument("output", type=Path)
    inputs.add_argument("--dxc", type=Path, required=True)
    inputs.add_argument("--validator", type=Path, required=True)
    inputs.add_argument("--campaign", type=int, choices=range(1, 3000), required=True, metavar="1..2999")
    inputs.add_argument("--blocks", type=int, choices=range(1, 5), default=2)
    measurement = commands.add_parser("run")
    measurement.add_argument("prepared", type=Path)
    measurement.add_argument("executable", type=Path)
    measurement.add_argument("output", type=Path)
    measurement.add_argument("--adapter", required=True)
    args = parser.parse_args()
    try:
        if args.action == "build":
            build(args.output.resolve(), args.clang, args.headers, args.dlltool)
        elif args.action == "prepare":
            prepare(args.output.resolve(), args.dxc, args.validator, args.campaign, args.blocks)
        else:
            run(args.prepared.resolve(), args.executable.resolve(), args.adapter, args.output.resolve())
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or str(error)).strip() + "\n")


if __name__ == "__main__":
    main()
