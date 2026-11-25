"""Evaluate the emitted test fixture's i32 DXIL subset without a GPU."""

import hashlib
import operator
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parent
DXC = ROOT.parent / "portbridge-xcl-925-evidence/dxc-v1.9.2602/bin/x64/dxc.exe"
SHAPES = (("constant2", 2), ("dynamic2", 2), ("dynamic16", 16), ("dynamic64", 64), ("two-seeds16", 16))
TOKEN = r"(?:%\d+|-?\d+)"
ARITHMETIC = {"add": operator.add, "sub": operator.sub, "mul": operator.mul, "xor": operator.xor, "and": operator.and_}
MASK = (1 << 32) - 1


def program(blob):
    ir = subprocess.check_output([str(DXC), "-dumpbin", str(blob)], text=True, timeout=8)
    body = ir.split("define void @main() {\n", 1)[1].split("\n}", 1)[0]
    blocks = {0: []}
    block = 0
    for line in body.splitlines():
        target = re.match(r"^; <label>:(\d+)", line)
        if target:
            block = int(target[1])
            blocks[block] = []
        else:
            line = line.partition(";")[0].strip()
            if line:
                blocks[block].append(line)
    return blocks, len(re.findall(r" = phi i32 ", body))


def readback(blocks, lane):
    values, memory = {}, {}
    block, previous = 0, None

    def value(operand):
        return values[operand] if operand.startswith("%") else int(operand) & MASK

    for _ in range(16):
        phis = {}
        for line in blocks[block]:
            dest, separator, expr = line.partition(" = ")
            if separator and expr.startswith("phi i32 "):
                pairs = re.findall(rf"\[ ({TOKEN}), %(\d+) \]", expr)
                incoming = [v for v, pred in pairs if int(pred) == previous]
                assert len(incoming) == 1, line
                phis[dest] = value(incoming[0])
                continue
            if phis:
                values.update(phis)
                phis.clear()
            if separator and expr.startswith(("call %dx.types.Handle @dx.op.createHandleFromBinding(",
                                              "call %dx.types.Handle @dx.op.annotateHandle(")):
                values[dest] = 0
                continue
            if separator and expr == "call i32 @dx.op.threadId.i32(i32 93, i32 0)":
                values[dest] = lane
                continue
            arithmetic = re.fullmatch(rf"(add|sub|mul|xor|and) i32 ({TOKEN}), ({TOKEN})", expr)
            if arithmetic:
                op, a, b = arithmetic.groups()
                values[dest] = ARITHMETIC[op](value(a), value(b)) & MASK
                continue
            compare = re.fullmatch(rf"icmp ne i32 ({TOKEN}), ({TOKEN})", expr)
            if compare:
                values[dest] = value(compare[1]) != value(compare[2])
                continue
            store = re.match(rf"call void @dx\.op\.rawBufferStore\.i32\(i32 140, %dx.types.Handle %\d+, i32 ({TOKEN}), i32 undef, i32 ({TOKEN}), i32 undef, i32 undef, i32 undef, i8 1, i32 4\)$", line)
            if store:
                addr = value(store[1])
                assert addr not in memory, (line, addr)
                memory[addr] = value(store[2])
                continue
            branch = re.fullmatch(r"br label %(\d+)", line)
            conditional = re.fullmatch(r"br i1 (%\d+), label %(\d+), label %(\d+)", line)
            if branch or conditional:
                target = branch[1] if branch else conditional[2 if value(conditional[1]) else 3]
                previous, block = block, int(target)
                break
            if line == "ret void":
                return memory
            raise AssertionError(f"unsupported DXIL in fixture: {line}")
        else:
            raise AssertionError(f"unterminated block {block}")
    raise AssertionError("fixture exceeded its bounded loop")


def expected(shape, width, lane):
    seed = 17 if shape.startswith("constant") else lane ^ 17
    offset = lane * width * 4
    iterations = (lane & 3) + 1
    return {offset + 4 * i: 53 if shape.startswith("two-seeds") and (i + iterations) % 2 else seed for i in range(width)}


def main():
    for shape, width in SHAPES:
        files = [ROOT / arm / f"{shape}.dxil" for arm in ("baseline", "candidate")]
        for arm, file in zip(("baseline", "candidate"), files):
            blocks, phis = program(file)
            retain_cycle = arm == "baseline" or shape == "two-seeds16"
            assert phis == (width + 1 if retain_cycle else 1), (shape, arm, phis)
            for lane in range(32):
                assert readback(blocks, lane) == expected(shape, width, lane), (shape, arm, lane)
            data = file.read_bytes()
            print(f"{arm}/{shape} size={len(data)} phis={phis} words={32 * width} sha256={hashlib.sha256(data).hexdigest()}")
        if shape == "two-seeds16":
            assert files[0].read_bytes() == files[1].read_bytes()
    print("PASS: all ten emitted shaders match the CPU readback oracle for all 32 fixture lanes")


if __name__ == "__main__":
    main()
