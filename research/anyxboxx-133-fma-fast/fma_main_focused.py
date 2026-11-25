# SPDX-License-Identifier: GPL-3.0-or-later
"""Run pinned directed rounding witnesses against main's actual instructions."""
import json
from pathlib import Path
import sys

source = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(source / "tests"), str(source / "PrototypeScarlett")]

from emu import rdna2_exec
from test_rdna2_exec import LITERAL, V, program, vop1, vop2, vop3

CASES = (
    (0x3FC00000, 0x3F800001, 0x99800000, 0x3FC00001),
    (0x3FC00000, 0x3F800003, 0x19800000, 0x3FC00005),
    (0xBFC00000, 0x3F800001, 0x19800000, 0xBFC00001),
    (0x3FC00000, 0x3F800001, 0x00000000, 0x3FC00002),
    (0x00800000, 0x3F7FFFFF, 0x00000000, 0x00800000),
    (0x5B780000, 0x63842108, 0x8D800000, 0x7F7FFFFF),
)
OPS = ("fmac-e32", "fmac-e64", "fma", "fma-legacy", "fmamk", "fmaak")


def mov(register, word):
    return vop1("v_mov_b32", register, LITERAL), word


def execute(a, b, c):
    return rdna2_exec.run(program(
        *mov(1, a), *mov(2, b), *mov(3, c),
        *mov(4, c), vop2("v_fmac_f32", 4, V + 1, 2),
        *mov(5, c), *vop3("v_fmac_f32", 5, V + 1, V + 2),
        *vop3("v_fma_f32", 6, V + 1, V + 2, V + 3),
        *vop3("v_fma_legacy_f32", 7, V + 1, V + 2, V + 3),
        vop2("v_fmamk_f32", 8, V + 1, 3), b,
        vop2("v_fmaak_f32", 9, V + 1, 2), c,
        *mov(10, c), vop2("v_mac_f32", 10, V + 1, 2),
        *vop3("v_mad_f32", 11, V + 1, V + 2, V + 3),
    ))


def main():
    results = []
    for a, b, c, expected in CASES:
        wave = execute(a, b, c)
        words = tuple(wave.v[register][0] for register in range(4, 12))
        assert all(wave.v[register] == [word] * 32 for register, word in enumerate(words, start=4))
        results.append({
            "inputs": [f"{word:08X}" for word in (a, b, c)],
            "expected": f"{expected:08X}",
            "fused": {op: f"{word:08X}" for op, word in zip(OPS, words)},
            "match": all(word == expected for word in words[:6]),
            "unfused_controls": [f"{word:08X}" for word in words[6:]],
        })
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
