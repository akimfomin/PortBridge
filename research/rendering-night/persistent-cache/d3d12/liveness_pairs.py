# SPDX-License-Identifier: MIT
"""Produce equivalent straight-line shader pairs and audit measured DXIL live ranges."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parent
DEFAULT_DXC = ROOT.parent / "portbridge-xcl-925-evidence/dxc-v1.9.2602/bin/x64/dxc.exe"
DEFINITION = re.compile(r"^(%\d+)\s*=\s*(.*)$")
VALUE = re.compile(r"%\d+\b")
MAIN = re.compile(r"define\s+void\s+@main\([^)]*\)\s*[^\n{]*\{(.*?)^\}", re.M | re.S)


def source(width, salt, long_lived, shared_input):
    # The source and destination regions do not overlap at any fixture size.
    def read(i):
        value = "seed" if shared_input else f"Data.Load({4 * i})"
        return f"    uint v{i} = {value} ^ {salt + 37 * i}u;"

    def write(i):
        return f"    Data.Store({1024 + 4 * i}, v{i});"

    head = [
        'RWByteAddressBuffer Data : register(u0);',
        '[RootSignature("UAV(u0)")]',
        '[numthreads(1,1,1)]',
        'void main() {',
    ]
    if shared_input:
        head.append("    uint seed = Data.Load(0);")
    if long_lived:
        body = [read(i) for i in range(width)] + [write(i) for i in range(width)]
    else:
        body = [line for i in range(width) for line in (read(i), write(i))]
    return "\n".join(head + body + ["}", ""])


def command(args):
    return subprocess.check_output([str(x) for x in args], encoding="utf-8", stderr=subprocess.STDOUT,
                                   timeout=20, errors="replace")


def inspect(disassembly):
    function = MAIN.search(disassembly)
    if not function:
        raise ValueError("Could not find a simple DXIL main function")
    definitions, last_uses = {}, {}
    opcodes = Counter()
    listing = []
    memory_order = []
    for line in function[1].splitlines():
        line = line.split(";", 1)[0].strip()
        if not line or line.endswith(":"):
            continue
        definition = DEFINITION.match(line)
        if definition:
            name, operation = definition.groups()
            definitions[name] = len(listing)
        else:
            operation = line
        for value in VALUE.findall(operation):
            last_uses[value] = len(listing)
        key = operation.split()[0]
        if "call" in operation and "@dx.op." in operation:
            key = operation.split("@dx.op.", 1)[1].split("(", 1)[0]
            if key.startswith(("rawBufferLoad.", "rawBufferStore.")):
                memory_order.append(key)
        opcodes[key] += 1
        listing.append(operation)
    if opcodes["br"] or opcodes["phi"]:
        raise ValueError("Unexpected control flow in generated fixture")
    live = []
    for position in range(len(listing)):
        count = sum(begin <= position < last_uses.get(name, -1) for name, begin in definitions.items())
        live.append(count)
    return dict(instruction_count=len(listing), opcode_counts=dict(sorted(opcodes.items())),
                max_live=max(live, default=0), live_by_instruction=live, memory_order=memory_order)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dxc", type=Path, default=DEFAULT_DXC)
    parser.add_argument("--widths", type=int, nargs="+", default=[4, 8, 12])
    parser.add_argument("--seeds", type=int, nargs="+", default=[17, 223, 1009])
    parser.add_argument("--shared-input", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "liveness")
    args = parser.parse_args()
    assert all(2 <= width <= 32 for width in args.widths)
    assert all(0 <= salt < (1 << 31) for salt in args.seeds)
    dxc = args.dxc.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    for width in args.widths:
        for salt in args.seeds:
            suffix = f"{width}-{salt}"
            pair = {}
            root_contents = None
            for shape in ("short", "long"):
                stem = output / f"{shape}-{suffix}"
                source_file = stem.with_suffix(".hlsl")
                binary = stem.with_suffix(".dxil")
                signature = stem.with_suffix(".rootsig")
                source_file.write_text(source(width, salt, shape == "long", args.shared_input),
                                       encoding="ascii", newline="\n")
                command([dxc, "-Od", "-T", "cs_6_6", "-E", "main", "-Fo", binary, source_file])
                command([dxc, "-dumpbin", "-extractrootsignature", "-Fo", signature, binary])
                root = signature.read_bytes()
                if root_contents is None:
                    root_contents = root
                else:
                    assert root == root_contents
                dump = command([dxc, "-dumpbin", binary])
                stem.with_suffix(".ll").write_text(dump, encoding="utf-8", newline="\n")
                pair[shape] = inspect(dump) | {"bytes": binary.stat().st_size, "file": binary.name}
            short, long = pair["short"], pair["long"]
            exact_ops = short["opcode_counts"] == long["opcode_counts"]
            assert exact_ops and short["max_live"] < long["max_live"], (width, salt, pair)
            if args.shared_input:
                assert short["memory_order"] == long["memory_order"], (width, salt, pair)
            cases.append(dict(width=width, salt=salt, shared_input=args.shared_input,
                              short=short, long=long, root=f"short-{suffix}.rootsig"))
    (output / "manifest.json").write_text(json.dumps(cases, indent=2)+"\n", encoding="utf-8", newline="\n")
    with (output / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("width","salt","instructions","short DXIL bytes","long DXIL bytes",
                         "short max live","long max live"))
        for case in cases:
            short, long = case["short"], case["long"]
            writer.writerow((case["width"],case["salt"],short["instruction_count"],short["bytes"],long["bytes"],
                             short["max_live"],long["max_live"]))


if __name__ == "__main__":
    main()
