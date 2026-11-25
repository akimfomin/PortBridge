"""Verify SGPR-selector gfx1013 encodings and compare DXIL to the RTX evidence."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys


root = Path(__file__).resolve().parents[2]
output = Path(__file__).resolve().parent
workspace = root.parents[1]
proof = workspace / "outputs/portbridge-xbox2windows-2127-proof"
sys.path[:0] = [str(root / "tests"), str(proof)]
from mesh_entry_check import PIXEL, PROGRAM, TRIANGLE, evaluate_depth, fixture, lower, triangle_inputs
from mesh_spill_readback import make_program, prepare_draws
from mesh_entry_aot import Wave

mc = workspace / "work/Leonida-PR-4416-review/llvm/Library/bin/llvm-mc.exe"
llvm_bin = workspace / "work/Leonida-portable-vulkan/tools/llvm-mingw-20261117-ucrt-x86_64/bin"
dxc = workspace / "work/portbridge-anyxboxx-133-warp-alu-check/dxc-v1.9.2609/dxc.exe"
os.environ["PATH"] = str(llvm_bin) + os.pathsep + os.environ["PATH"]
base = [mc, "-triple=amdgcn--amdpal", "-mcpu=gfx1013", "-mattr=+wavefrontsize64,-wavefrontsize32"]


def prepare_program(clear_lane=None, *, wrapped=False, dynamic=False):
    program = make_program(PROGRAM, clear_lane)
    at = next(j for j, line in enumerate(program) if line.startswith("v_writelane_b32"))
    program[at:at] = [
        f"s_mov_b32 s44, {0x48 if wrapped else 8}",
        f"s_mov_b32 s45, {0x68 if wrapped else 40}",
    ]
    lanes = {"8": "s30" if dynamic else "s44", "40": "s45"}
    for j, line in enumerate(program):
        if line.startswith(("v_writelane_b32", "v_readlane_b32")):
            operands, delimiter, lane = line.rpartition(", ")
            program[j] = operands + delimiter + lanes[lane]
    return program


def assemble(label, program):
    asm, obj, code = (output / f"{label}.{ext}" for ext in ("s", "o", "bin"))
    asm.write_text("\n".join(line.replace("prim,", "prim").replace("pos0,", "pos0") for line in program) + "\n")
    subprocess.run([*base, "-filetype=obj", asm, "-o", obj], check=True, timeout=8)
    subprocess.run([llvm_bin / "llvm-objcopy.exe", "-O", "binary", "--only-section=.text", obj, code], check=True, timeout=8)
    raw = code.read_bytes()
    dump = subprocess.run(
        [*base, "--disassemble", "--show-encoding"],
        input=" ".join(f"0x{number:02x}" for number in raw) + "\n",
        capture_output=True, encoding="ascii", check=True, timeout=8,
    ).stdout
    (output / f"{label}.decoded.txt").write_text(dump)
    decoded, offset = [], 0
    for line in dump.splitlines():
        instruction, marker, encoding = line.partition("; encoding:")
        assert marker, line
        bits = bytes(int(item, 16) for item in re.findall(r"0x[\da-f]{2}", encoding))
        decoded.append((offset, instruction.strip()))
        assert bits == raw[offset : offset + len(bits)]
        offset += len(bits)
    assert offset == len(raw)
    print(label, "gfx1013 bytes", len(raw), "SHA-256", hashlib.sha256(raw).hexdigest())
    return decoded


def main():
    cases = (
        ("positive", None, (1, 0x100), 0.5),
        ("drop-low", 8, (0, 0x100), -0.5),
        ("drop-high", 40, (1, 0), -0.5),
    )
    draws = []
    for label, lane, words, depth in cases:
        decoded = assemble(label, prepare_program(lane))
        wave = Wave(0, [4099])
        wave.run(decoded, {})
        assert (wave.scalar("s40"), wave.scalar("s41")) == words, label
        source = lower(decoded, [4099], (3, 1))
        inputs = triangle_inputs()
        assert evaluate_depth(source, inputs) == depth, label
        print(label, "EXEC words", words, "CPU depth", depth)
        positions = [(x, y, depth, w) for x, y, _, w in TRIANGLE]
        draws.append((label, source, inputs, positions, depth >= 0))
    wrapped = assemble("wrapped-selectors", prepare_program(wrapped=True))
    assert lower(wrapped, [4099], (3, 1)) == draws[0][1]
    print("wrapped-selectors: same HLSL as selector words 8 and 40")
    dynamic = assemble("dynamic-selector", prepare_program(dynamic=True))
    try:
        lower(dynamic, [4099], (3, 1))
    except ValueError as error:
        assert "statically known SGPR lane: s30" in str(error), error
        print("dynamic-selector refused:", error)
    else:
        raise AssertionError("Runtime-valued selector accepted")

    prepared = output / "replay"
    prepare_draws(dxc, prepared, draws, fixture, PIXEL)
    for expectation in (proof / "SHA256-RENDER-INPUTS.txt").read_text().splitlines():
        digest, label = expectation.split("  ")
        actual = hashlib.sha256((prepared / label).read_bytes()).hexdigest()
        assert actual == digest, (label, actual, digest)
        print(label, "matches previously verified inline RTX input", actual)


if __name__ == "__main__":
    main()
