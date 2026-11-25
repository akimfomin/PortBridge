
from __future__ import annotations

import argparse
import ast
import json
import math
from pathlib import Path
from random import Random
import statistics
import sys
from time import perf_counter_ns


def load_previous(path: Path):
    program = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    fn, = (node for node in program.body if isinstance(node, ast.FunctionDef) and node.name == "_fma")
    namespace = {"math": math}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_fma"]


def bits(low, high, random):
    return (random.randrange(2) << 31) | (random.randrange(low, high) << 23) | random.getrandbits(23)


def inputs(convert):
    random = Random(0x133)
    ordinary = [tuple(convert(bits(118, 135, random)) for _ in range(3)) for _ in range(1018)]
    separated = [(convert(bits(110, 111, random)), convert(bits(120, 121, random)),
                  convert(bits(exp, exp+1, random))) for exp in [75, 175] * 509]
    halfway = []
    for exponent in range(100, 135):
        for low in range(1, 16, 2):
            for perturbation in (0x99800000, 0x19800000, 0):
                halfway.append(tuple(map(convert, ((exponent << 23) | 0x00400000, 0x3F800000 | low, perturbation))))
    return {"ordinary": ordinary, "separated-exponents": separated, "midpoints": halfway}


def measure(variants, trial, runs):
    samples = {name: [] for name in variants}
    items = list(variants.items())
    for name, fn in items:
        trial(fn)
    for rotation in range(runs):
        offset = rotation % len(items)
        order = items[offset:] + items[:offset]
        if rotation % 2:
            order.reverse()
        for name, fn in order:
            elapsed, fingerprint = trial(fn)
            samples[name].append([round(elapsed / 1e6, 6), fingerprint])
    assert all(len({entry[1] for entry in group}) == 1 for group in samples.values())
    return {name: {"median-ms": statistics.median(entry[0] for entry in group), "samples-ms-and-checksum": group}
            for name, group in samples.items()}


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--candidate", type=Path, required=True, help="AnyXboxX checkout with the faster FMA patch")
    args.add_argument("--previous", type=Path, required=True, help="AnyXboxX checkout with the published FMA patch")
    args.add_argument("--output", type=Path, required=True)
    args = args.parse_args()
    sys.path[0:0] = [str((args.candidate / directory).resolve()) for directory in ("PrototypeScarlett","tests")]
    from emu import rdna2_exec, rdna2_exec_ops as ops
    from test_rdna2_exec import V, program, vop2
    from test_rdna2_exec_vop12 import mov

    previous = load_previous(args.previous / "PrototypeScarlett/emu/rdna2_exec_ops.py")
    variants = {"baseline": ops._mul_add, "published": previous, "fast": ops._fma}
    corpora = inputs(ops.bits_float)
    repeat = 150
    result = {"python": sys.version.split()[0], "micro": {}}
    for case, triplets in corpora.items():
        def helper(function):
            start = perf_counter_ns()
            checksum = 0
            for _ in range(repeat):
                for a, b, c in triplets:
                    checksum = (checksum + ops.float_bits(function(a, b, c))) & 0xFFFFFFFF
            return perf_counter_ns() - start, checksum
        row = measure(variants, helper, 9)
        assert row["published"]["samples-ms-and-checksum"][0][1] == row["fast"]["samples-ms-and-checksum"][0][1]
        result["micro"][case] = {"calls": len(triplets) * repeat, "results": row}

    programs = [program(*mov(1, ops.float_bits(a)), *mov(2, ops.float_bits(b)), *mov(3, ops.float_bits(c)),
                        *[vop2("v_fmac_f32", 3, V + 1, 2)] * 96)
                for a, b, c in corpora["ordinary"][:10]]
    repeat = 5

    def interpreter(function):
        previous = ops._fma
        ops._fma = function
        try:
            start = perf_counter_ns()
            checksum = 0
            for _ in range(repeat):
                for code in programs:
                    wave = rdna2_exec.run(code)
                    checksum = (checksum + sum(wave.v[3])) & 0xFFFFFFFF
            return perf_counter_ns() - start, checksum
        finally:
            ops._fma = previous

    row = measure(variants, interpreter, 9)
    assert row["published"]["samples-ms-and-checksum"][0][1] == row["fast"]["samples-ms-and-checksum"][0][1]
    result["interpreter"] = {"lane-operations": 32 * 96 * len(programs) * repeat, "results": row}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for name, case in {**result["micro"],"interpreter":result["interpreter"]}.items():
        print(name, {label: round(values["median-ms"], 2) for label,values in case["results"].items()})

if __name__ == "__main__":
    main()
