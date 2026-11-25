# SPDX-License-Identifier: GPL-3.0-or-later
"""A/B the optional VIctory pass and evaluate the generated DXIL's stores on the CPU."""

import argparse
import hashlib
import json
import operator
import os
from pathlib import Path
import re
import subprocess


PHI = re.compile(r"(%\d+) = phi i(?:1|32) (.+)")
INCOMING = re.compile(r"\[ ([^ ,]+), (%\d+) \]")
COMPUTE = re.compile(r"(%\d+) = (add|sub|shl|lshr|and|or|xor) i(?:1|32) ([^,]+), (.+)")
COMPARE = re.compile(r"(%\d+) = icmp (eq|ne|ult|ule|ugt|uge) i(?:1|32) ([^,]+), (.+)")
SELECT = re.compile(r"(%\d+) = select i1 ([^,]+), i\d+ ([^,]+), i\d+ (.+)")
EXTRACT = re.compile(r"(%\d+) = extractvalue [^ ]+ (%\d+), (\d+)")
CALL = re.compile(r"(?:(%\d+) = )?call .+? @dx\.op\.([^(]+)\((.*)\)")
BIN_OP = {"add": operator.add, "sub": operator.sub, "shl": operator.lshift, "lshr": operator.rshift,
          "and": operator.and_, "or": operator.or_, "xor": operator.xor}
CMP_OP = {"eq": operator.eq, "ne": operator.ne, "ult": operator.lt, "ule": operator.le,
          "ugt": operator.gt, "uge": operator.ge}


def run(args, *, env=None):
    result = subprocess.run([str(arg) for arg in args], env=env, timeout=15, capture_output=True,
                            encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(f"{args[0]} exited {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result.stdout + result.stderr


def parse_main(asm):
    body = asm.split("define void @main() {", 1)[1].split("\n}", 1)[0]
    current = []
    blocks = {"%0": current}
    for line in body.splitlines():
        label = re.match(r"\s*(?:; <label>:)?(\d+)(?::|\s|$)", line)
        if label:
            current = []
            blocks["%" + label[1]] = current
            continue
        text = line.split(";", 1)[0].strip()
        if text:
            current.append(text)
    return blocks


def stores_on_cpu(blocks, inputs, width):
    """Evaluate the fixture's SSA and branches, with mock dimensions and a single local UAV."""
    values = {}
    stores = {}

    def word(value):
        if value.startswith("%"):
            return values[value]
        if value in ("true", "false"):
            return int(value == "true")
        return int(value) & 0xffffffff

    current, previous = "%0", None
    for _ in range(16):
        instructions = blocks[current]
        entering = {}
        for line in instructions:
            if match := PHI.fullmatch(line):
                incoming = [(value, pred) for value, pred in INCOMING.findall(match[2]) if pred == previous]
                assert len(incoming) == 1, (line, previous)
                entering[match[1]] = word(incoming[0][0])
        values.update(entering)
        for line in instructions:
            if PHI.fullmatch(line):
                continue
            if match := COMPUTE.fullmatch(line):
                values[match[1]] = BIN_OP[match[2]](word(match[3]), word(match[4])) & 0xffffffff
            elif match := COMPARE.fullmatch(line):
                values[match[1]] = int(CMP_OP[match[2]](word(match[3]), word(match[4])))
            elif match := SELECT.fullmatch(line):
                values[match[1]] = word(match[3] if word(match[2]) else match[4])
            elif match := EXTRACT.fullmatch(line):
                values[match[1]] = values[match[2]][int(match[3])]
            elif match := CALL.fullmatch(line):
                dest, op, args = match.groups()
                if op.startswith("createHandle") or op == "annotateHandle":
                    continue  # Resource identity is fixed by the single output fixture.
                if op.startswith("threadIdInGroup."):
                    values[dest] = 0
                elif op == "cbufferLoadLegacy.i32":
                    register = word(args.rsplit(", i32 ", 1)[1])
                    assert register in (0, 1), (register, line)
                    values[dest] = (*inputs, 0, 0) if register == 0 else (0, 0, 0, 0)
                elif op == "getDimensions":
                    values[dest] = (4 * width, 0, 0, 0)
                elif op == "rawBufferStore.i32":
                    fields = args.split(", ")
                    assert fields[0] == "i32 140" and fields[3] == "i32 undef" and fields[8] == "i8 1", line
                    offset = word(fields[2].removeprefix("i32 "))
                    assert offset not in stores, (offset, line)
                    stores[offset] = word(fields[4].removeprefix("i32 "))
                else:
                    raise ValueError(line)
            elif line.startswith("br label "):
                previous, current = current, line.removeprefix("br label ")
                break
            elif line.startswith("br i1 "):
                condition, yes, no = line.removeprefix("br i1 ").split(", label ")
                previous, current = current, yes if word(condition) else no
                break
            elif line == "ret void":
                return stores
            else:
                raise ValueError(line)
        else:
            raise RuntimeError(f"Missing terminator in {current}")
    raise RuntimeError("Fixture exceeded 16 interpreted blocks")


def inspect(path, dxc, width, seeds):
    assert "Validation succeeded" in run([dxc / "dxv.exe", path])
    asm = run([dxc / "dxc.exe", "-dumpbin", path])
    path.with_suffix(".ll").write_text(asm, encoding="utf-8")
    blocks = parse_main(asm)
    for inputs in [(0x13579bdf, 0x2468ace0), (0xffffffff, 0x80000000), (51, 51)]:
        result = stores_on_cpu(blocks, inputs, width)
        expected = {4 * i: inputs[(i + 3) % seeds] for i in range(width)}
        assert result == expected, (path, inputs, result, expected)
    phis = sum(PHI.fullmatch(line) is not None for block in blocks.values() for line in block)
    return {"bytes": path.stat().st_size, "phis": phis, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--dxc-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    exe = args.exe.resolve(strict=True)
    dxc = args.dxc_dir.resolve(strict=True)
    output.mkdir()
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("VICTORY_")}
    env["VICTORY_DXIL"] = str(dxc / "dxil.dll")
    for arm, override in [("control", {"VICTORY_PHI_RINGS_OFF": "1"}), ("candidate", {})]:
        log = run([exe, output / arm], env={**env, **override})
        (output / f"{arm}-emit.log").write_text(log, encoding="utf-8")
    results = {}
    for width in [2, 16, 64]:
        for seeds in [1, 2]:
            name = f"{width}-regs-{seeds}-seeds"
            control, candidate = [output / arm / f"{name}.dxil" for arm in ["control", "candidate"]]
            assert control.with_suffix(".rdna2").read_bytes() == candidate.with_suffix(".rdna2").read_bytes(), name
            before = inspect(control, dxc, width, seeds)
            after = inspect(candidate, dxc, width, seeds)
            if seeds == 1:
                assert before["phis"] - after["phis"] == width and before["bytes"] > after["bytes"], name
            else:
                assert before == after, name
            results[name] = {"control": before, "candidate": after, "oracle_inputs": 3}
            print(f"{name}: {before['phis']} -> {after['phis']} PHIs, {before['bytes']} -> {after['bytes']} bytes, DXV and stores passed")
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
