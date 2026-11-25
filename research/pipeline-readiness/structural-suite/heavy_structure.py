# SPDX-License-Identifier: MIT
"""Count IR and RDNA structures in the physically timed open pixel examples."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess


def live_instruction_stats(instructions):
    # Preserve branches and any call whose observability is unclassified. Treat wave
    # transport results as potentially removable only when no retained result needs them.
    wave_prefixes = ("dx.op.waveActiveBallot", "dx.op.quadOp.", "dx.op.quadReadLaneAt.")
    value_call_prefixes = wave_prefixes + (
        "dx.op.unary.", "dx.op.binary.", "dx.op.tertiary.", "dx.op.loadInput.",
        "dx.op.annotateHandle", "dx.op.createHandleFromBinding", "dx.op.cbufferLoadLegacy.",
    )
    effectful_opcodes = {"br", "switch", "ret", "unreachable", "store", "atomicrmw", "cmpxchg", "fence"}
    value_names = {}
    operands = []
    calls_by_index = {}
    worklist = []
    for index, instruction in enumerate(instructions):
        lhs, sep, rhs = instruction.partition(" = ")
        if not sep:
            rhs = lhs
        else:
            assert re.fullmatch(r"%\d+", lhs), instruction
            value_names[lhs] = index
        operands.append(re.findall(r"%\d+", rhs))
        opcode = rhs.split(" ", 1)[0]
        if opcode == "call":
            called = re.search(r"@([^\s(]+)", rhs).group(1)
            calls_by_index[index] = called
            if not called.startswith(value_call_prefixes):
                worklist.append(index)
        elif opcode in effectful_opcodes or not sep:
            worklist.append(index)

    live = set(worklist)
    while worklist:
        for name in operands[worklist.pop()]:
            definition = value_names.get(name)
            if definition is not None and definition not in live:
                live.add(definition)
                worklist.append(definition)

    return {
        "observability_roots": "Terminators, stores, atomics and unclassified calls. Static liveness only.",
        "unsunk_named_values": len(value_names) - sum(index in live for index in value_names.values()),
        "unsunk_wave_calls": dict(Counter(called for index, called in calls_by_index.items()
                                         if index not in live and called.startswith(wave_prefixes))),
    }


def disassembly_stats(path):
    text = path.read_text(encoding="utf-8")
    body = text.split("define void @main() {", 1)[1].split("\n}", 1)[0]
    instructions = [line.partition(";")[0].strip() for line in body.splitlines()]
    instructions = [line for line in instructions if line and not line.startswith(("]", "i32 "))]
    ops = Counter(line.split(" = ")[-1].split(" ", 1)[0] for line in instructions)
    calls = Counter(re.findall(r"\bcall [^\n]*?@([^\s(]+)", body))
    return {
        "instruction_count": len(instructions),
        "opcodes": dict(ops),
        "calls": dict(calls),
        "liveness": live_instruction_stats(instructions),
        "phi_incoming_edges": sum(line.count("[") for line in instructions if " = phi " in line),
        "sha256": sha256(path.read_bytes()).hexdigest(),
    }


def rdna_stats(objdump, source):
    text = subprocess.run([objdump, "-d", "--mcpu=gfx1030", source], capture_output=True,
                          encoding="utf-8", check=True, timeout=20).stdout
    operations = re.findall(r"^\s+([a-z_][a-z0-9_]+)\s+(.*?)\s*//", text, re.M)
    pair_count = sum(
        name == "v_add_co_u32" and next_name == "v_add_co_ci_u32_e32"
        and ", vcc_lo," in operands and next_operands.endswith(", vcc_lo")
        for (name, operands), (next_name, next_operands) in zip(operations, operations[1:])
    )
    return {
        "opcodes": dict(Counter(op for op, _ in operations)),
        "adjacent_vcc_carry_pairs": pair_count,
        "elf_sha256": sha256(source.read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("corpus", "matrix", "objdump", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    index = json.loads((args.matrix / "combined-results.json").read_text(encoding="utf-8"))
    result = {"scope": "Static DXIL and RDNA structure counts, not pass-level native driver profiling.",
              "xcl_revision": index["xcl_revision"],
              "objdump_sha256": sha256(args.objdump.read_bytes()).hexdigest(),
              "cases": []}
    for shader in (71, 73):
        observation = next(row for row in index["observations"] if row.get("id") == shader)
        case = args.matrix / f"{shader:03d}"
        elf = args.corpus / f"{shader:03d}" / "shader.elf"
        result["cases"].append({
            "id": shader, "source": observation["source"], "source_sha256": observation["source_sha256"],
            "rdna": rdna_stats(args.objdump, elf),
            "baseline": disassembly_stats(case / "off.ll"), "combined": disassembly_stats(case / "ags.ll"),
            "structural_metrics": {arm: observation["arms"][arm] for arm in ("off", "ags")},
        })
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    for row in result["cases"]:
        print(row["id"], row["source"], row["rdna"]["adjacent_vcc_carry_pairs"],
              row["baseline"]["instruction_count"], row["combined"]["instruction_count"])


if __name__ == "__main__":
    main()
