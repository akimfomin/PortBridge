# SPDX-License-Identifier: GPL-3.0-or-later
"""Run exact synthetic Wave32 arithmetic checks against a public AnyXboxX checkout."""

import argparse
from collections import Counter
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
from random import Random
import struct
import subprocess
import sys

MASK32 = 0xFFFFFFFF
V = 256
VCC_LO, EXEC_LO, LITERAL = 106, 126, 255
A, B, DEST = 1, 2, 3
SGPR_IN, SGPR_OUT = 40, 42


def directed_samples():
    random = Random(0x133)
    yield MASK32, 0, 1
    yield 0, MASK32, 1
    yield MASK32, MASK32, 0
    yield 0, 0, MASK32
    edges = [0, 1, 2, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFE, MASK32]
    for a, b in product(edges, repeat=2):
        yield a, b, random.getrandbits(32)
    for _ in range(80):
        yield random.getrandbits(32), random.getrandbits(32), random.getrandbits(32)


def compare_carry(wave, check, outcomes, errors):
    branches = {
        "v_add_co_ci_u32": lambda a, b, k: a + b + k,
        "v_sub_co_ci_u32": lambda a, b, k: a - b - k,
        "v_subrev_co_ci_u32": lambda a, b, k: b - a - k,
    }
    masks = [0, 1, 1 << 31, 0x55555555, 0xAAAAAAAA, 0x00FFFF00, MASK32]
    for (a, b, salt), mask, incoming, (op, formula), form in product(
        directed_samples(), masks, [0, MASK32, 0xAAAAAAAA, 0x55555555], branches.items(),
        [("VOP2", VCC_LO, VCC_LO), ("VOP3", SGPR_IN, SGPR_OUT), ("VOP3", SGPR_IN, SGPR_IN)],
    ):
        family, source, target = form
        exec_wave = wave()
        exec_wave.v[A][:] = [a ^ (lane & salt) for lane in range(32)]
        exec_wave.v[B][:] = [b ^ ((31 - lane) & (salt >> 5)) for lane in range(32)]
        unchanged = [0xBAD00000 | lane for lane in range(32)]
        exec_wave.v[DEST][:] = unchanged
        exec_wave.s[EXEC_LO] = mask
        exec_wave.s[source] = incoming
        if target != source:
            exec_wave.s[target] = MASK32
        expected, expected_mask = unchanged.copy(), 0
        for lane in range(32):
            if not (mask >> lane & 1):
                continue
            value = formula(exec_wave.v[A][lane], exec_wave.v[B][lane], incoming >> lane & 1)
            expected[lane] = value & MASK32
            if value < 0 or value > MASK32:
                expected_mask |= 1 << lane
        check(exec_wave, family, op, source=source, target=target)
        key = (family, op, "in-place" if source == target else "separate")
        outcomes[key] += 1
        if exec_wave.v[DEST] != expected or exec_wave.s[target] != expected_mask:
            errors[key] += 1
        if target != source and exec_wave.s[source] != incoming:
            errors[key] += 1


def f32(word):
    return struct.unpack("<f", struct.pack("<I", word))[0]


def f32bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def round_normal(value):
    """Round an exact normal finite result by comparing nearby float32 values."""
    sign = 0x80000000 if value < 0 else 0
    absolute = abs(value)
    assert 1 <= absolute < 2
    centre = f32bits(float(absolute))
    candidates = range(centre - 1, centre + 2)
    closest = min(candidates, key=lambda word: (abs(Fraction(f32(word)) - absolute), word & 1))
    return sign | closest


def compare_fma(wave, check, outcomes, errors, controls, examples):
    variants = [
        ("VOP2", "v_fmac_f32", "accumulator"), ("VOP3", "v_fmac_f32", "accumulator"),
        ("VOP2", "v_fmac_legacy_f32", "accumulator"), ("VOP3", "v_fmac_legacy_f32", "accumulator"),
        ("VOP3", "v_fma_f32", "third_source"),
        ("VOP3", "v_fma_legacy_f32", "third_source"),
        ("VOP2", "v_fmamk_f32", "literal_multiplier"),
        ("VOP2", "v_fmaak_f32", "literal_addend"),
    ]
    for sign, offset, perturbation, (family, op, mode) in product(
        [0, 0x80000000], range(1, 128, 2), [0, 0x99800000, 0x19800000], variants,
    ):
        # 1.5 * (1 + odd * 2^-23) is exactly halfway between two binary32 words.
        # A normal +/- 2^-76 is lost when the sum first rounds to binary64.
        a, b, c = 0x3FC00000 | sign, 0x3F800000 | offset, perturbation
        expected = round_normal(Fraction(f32(a)) * Fraction(f32(b)) + Fraction(f32(c)))
        exec_wave = wave()
        exec_wave.v[A][:] = [a] * 32
        exec_wave.v[B][:] = [b] * 32
        exec_wave.v[4][:] = [c] * 32
        exec_wave.v[DEST][:] = [c] * 32
        if mode == "literal_multiplier":
            exec_wave.v[B][:] = [c] * 32
        check(
            exec_wave, family, op, third=V + 4 if mode == "third_source" else 128,
            literal=b if mode == "literal_multiplier" else c if mode == "literal_addend" else None,
        )
        actual = exec_wave.v[DEST][0]
        assert exec_wave.v[DEST] == [actual] * 32
        key = (family, op)
        outcomes[key] += 1
        if not perturbation:
            controls[key] += actual == expected
        if actual != expected:
            errors[key] += 1
            if "/".join(key) not in examples:
                examples["/".join(key)] = dict(zip(
                    ("a", "b", "c", "interpreter", "exact"),
                    [f"0x{word:08X}" for word in (a, b, c, actual, expected)],
                ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    revision = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    changes = subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"], text=True)
    sys.path.insert(0, str(checkout / "PrototypeScarlett"))
    from emu.rdna2_exec import Wave, run
    from emu.rdna2_ops import MNEMONICS

    opcodes = {(family, name): opcode for (family, opcode), name in MNEMONICS.items()}

    def check(wave, family, op, source=None, target=None, third=128, literal=None):
        opcode = opcodes[family, op]
        if family == "VOP2":
            words = [(opcode << 25) | (DEST << 17) | (B << 9) | (V + A)]
        else:
            words = [
                (0x35 << 26) | (opcode << 16) | ((target or 0) << 8) | DEST,
                ((source if source is not None else third) << 18) | ((V + B) << 9) | (V + A),
            ]
        if literal is not None:
            words.append(literal)
        words.append((0x17F << 23) | (opcodes["SOPP", "s_endpgm"] << 16))
        run(struct.pack(f"<{len(words)}I", *words), wave=wave)

    carries, carry_errors = Counter(), Counter()
    compare_carry(Wave, check, carries, carry_errors)
    fma, fma_errors, fma_controls = Counter(), Counter(), Counter()
    examples = {}
    compare_fma(Wave, check, fma, fma_errors, fma_controls, examples)
    evidence = {
        "revision": revision,
        "checkout_has_local_changes": bool(changes),
        "carry_wave_programs": sum(carries.values()),
        "carry_lane_checks": 32 * sum(carries.values()),
        "carry_samples_by_form": {"/".join(key): count for key, count in carries.items()},
        "carry_failing_checks": {"/".join(key): count for key, count in carry_errors.items()},
        "fma_samples_by_form": {"/".join(key): count for key, count in fma.items()},
        "fma_mismatches_by_form": {"/".join(key): count for key, count in fma_errors.items()},
        "fma_unperturbed_ties_passed": {"/".join(key): count for key, count in fma_controls.items()},
        "fma_first_mismatch_by_form": examples,
    }
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
