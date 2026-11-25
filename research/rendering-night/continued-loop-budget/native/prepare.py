"""Verify and assemble the six finite synthetic modules from Continued #1101."""

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import re
import runpy
import struct
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "shaders"
REVISION = "10ad8809b3ddf9f33c97ff0a52555bffbbb15aa7"
BOUNDARIES = ((0, 5), (1, 1), (1, 3), (4, 3), (4, 4), (4, 5))
CONTROLS = {(4, 3): "natural", (4, 5): "forced", (0, 5): "disabled"}
MODES = ((32, 32), (64, 64), (64, 32))


def sha(contents):
    return hashlib.sha256(contents).hexdigest()


def capture(checkout):
    commit = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if commit != REVISION:
        raise ValueError(f"expected {REVISION}; got {commit}")
    for folder in ("tools", "tests/semantic"):
        changes = subprocess.check_output(
            ["git", "-C", str(checkout), "status", "--porcelain", "--", folder], text=True
        )
        if changes:
            raise ValueError(f"pinned source tree is dirty at {folder}")
    proof = runpy.run_path(str(HERE / "boundary_probe.py"))
    sys.path.insert(0, str(checkout / "tests" / "semantic"))
    upstream = importlib.import_module("test_loop_iteration_guard")
    reference = upstream.run_compute_workgroup
    invocations = []

    def collect(text, lanes, subgroup, *args, **kwargs):
        invocations.append((text, lanes, subgroup))
        return reference(text, lanes, subgroup, *args, **kwargs)

    with patch.object(upstream, "run_compute_workgroup", collect):
        proof["run"](checkout)
    if len(invocations) != len(MODES) * len(BOUNDARIES) + 2:
        raise ValueError("CPU probe call pattern changed")

    selected = {}
    for i, (text, lanes, subgroup) in enumerate(invocations[:-2]):
        if MODES[i // len(BOUNDARIES)] != (lanes, subgroup):
            raise ValueError("unexpected CPU probe wave mode")
        boundary = BOUNDARIES[i % len(BOUNDARIES)]
        if subgroup == 32 and boundary in CONTROLS:
            mode = "native32" if lanes == 32 else "emulated64"
            selected[mode, CONTROLS[boundary]] = (text, lanes, boundary)
    return [(*key, *selected[key]) for case in CONTROLS.values()
            for key in (("native32", case), ("emulated64", case))]


def layout(text, lanes, budget):
    if not re.search(r'^\s*OpEntryPoint GLCompute %main "main"(?:\s|$)', text, re.MULTILINE):
        raise ValueError("expected compute entry point")
    if f"OpExecutionMode %main LocalSize {lanes} 1 1" not in text:
        raise ValueError("unexpected local size")
    if "OpMemoryModel PhysicalStorageBuffer64 GLSL450" not in text or " DescriptorSet " in text or " Binding " in text:
        raise ValueError("unexpected buffer/descriptor ABI")
    if any(f"OpMemberDecorate %UserData {member} Offset {offset}" not in text
           for member, offset in enumerate((0, 128, 132, 136, 140))):
        raise ValueError("unexpected push constant layout")
    if ("%loop_guard_" in text) != bool(budget):
        raise ValueError("unexpected guard presence")
    return re.findall(r"^\s*OpCapability (\w+)\s*$", text, re.MULTILINE)


def checked_sources():
    manifest = json.loads((SOURCES / "manifest.json").read_text(encoding="utf-8"))
    if manifest["revision"] != REVISION:
        raise ValueError("source manifest revision mismatch")
    rows = manifest["fixtures"]
    if len(rows) != 2 * len(CONTROLS):
        raise ValueError("unexpected source count")
    modules = []
    for (budget, natural), control in CONTROLS.items():
        for mode, lanes in (("native32", 32), ("emulated64", 64)):
            key = f"{mode}_{control}"
            data = (SOURCES / f"{key}.spvasm").read_bytes()
            text = data.decode("utf-8")
            count = min(budget, natural) if budget else natural
            marker = 42 if mode == "emulated64" or count == natural else 0xEEEEEEEE
            expected = dict(name=key, lanes=lanes, host_subgroup=32, budget=budget, natural=natural,
                            count=count, marker=marker, capabilities=layout(text, lanes, budget),
                            assembly_sha256=sha(data))
            if expected != rows[len(modules)]:
                raise ValueError(f"source or manifest mismatch for {key}")
            modules.append((mode, control, text, lanes, (budget, natural)))
    return modules, rows


def emit(output, assembler, validator, modules, rows):
    output.mkdir(parents=True)
    declarations = ["// Generated from the unedited finite synthetic SPIR-V modules."]
    values = []
    for (mode, case, text, lanes, _), row in zip(modules, rows, strict=True):
        key = f"{mode}_{case}"
        source = output / f"{key}.spvasm"
        source.write_bytes(text.encode("utf-8"))
        binary = source.with_suffix(".spv")
        subprocess.run([assembler, "--target-env", "vulkan1.3", source, "-o", binary], check=True, timeout=8)
        subprocess.run([validator, "--target-env", "vulkan1.3", binary], check=True, timeout=8)
        blob = binary.read_bytes()
        if not blob or len(blob) > 32 * 1024 or len(blob) % 4:
            raise ValueError("unexpected binary size")
        row.update(binary_sha256=sha(blob), binary_bytes=len(blob))
        words = [f"0x{word:08x}u" for (word,) in struct.iter_unpack("<I", blob)]
        declarations.append(f"constexpr std::uint32_t {key}[] = {{")
        declarations.extend("    " + ", ".join(words[i:i + 8]) + "," for i in range(0, len(words), 8))
        declarations.append("};")
        values.append(f'    {{"{key}", {key}, sizeof({key}), {lanes}, {row["count"]}, 0x{row["marker"]:08x}u}},')
    declarations += ["constexpr Fixture fixtures[] = {", *values, "};"]
    (output / "fixtures.inc").write_text("\n".join(declarations) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"revision": REVISION, "fixtures": rows}, indent=2) + "\n",
                                          encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="new directory for the assembled modules and C++ include")
    parser.add_argument("--checkout", type=Path, help="also retranslate and compare the pinned Continued source")
    parser.add_argument("--assembler", type=Path)
    parser.add_argument("--validator", type=Path)
    a = parser.parse_args()
    if len({bool(a.output), bool(a.assembler), bool(a.validator)}) != 1:
        parser.error("supply --output, --assembler and --validator together to assemble the modules")
    modules, rows = checked_sources()
    if a.checkout and capture(a.checkout.resolve(strict=True)) != modules:
        raise SystemExit("pinned Continued output differs from the bundled sources")
    if a.output:
        emit(a.output, a.assembler, a.validator, modules, rows)
    else:
        print("All six source modules match their manifest.")
