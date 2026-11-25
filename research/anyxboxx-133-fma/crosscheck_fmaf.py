# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-check AnyXboxX's float32 FMA against the Windows Universal CRT fmaf."""

import argparse
import ctypes
from itertools import product
import json
import math
import os
from pathlib import Path
from random import Random
import struct
import sys


def finite_random_words(seed):
    random = Random(seed)
    unmatched = 100_000
    while unmatched:
        words = tuple(random.getrandbits(32) for _ in range(3))
        if all(word & 0x7F800000 != 0x7F800000 for word in words):
            yield words
            unmatched -= 1


def targeted_words():
    magnitudes = [0, 1, 2, 0x007FFFFF, 0x00800000, 0x00800001, 0x3F000000,
                  0x3F800000, 0x3F800001, 0x3FC00000, 0x7EFFFFFF, 0x7F7FFFFF]
    words = [word | sign for word, sign in product(magnitudes, [0, 0x80000000])]
    yield from product(words, repeat=3)
    for exponent, offset, sign, perturbation in product(
        range(1, 255, 11), range(1, 16, 2), [0, 0x80000000], [0, 0x99800000, 0x19800000],
    ):
        yield (exponent << 23) | 0x00400000 | sign, 0x3F800000 | offset, perturbation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()

    crt = ctypes.CDLL(str(Path(os.environ["SystemRoot"]) / "System32" / "ucrtbase.dll"))
    fmaf = crt.fmaf
    fmaf.argtypes = [ctypes.c_float] * 3
    fmaf.restype = ctypes.c_float
    # The library must distinguish the exact side of the midpoint in the main fixture.
    assert fmaf(1.5, 1 + 2**-23, -2.0**-76) == 1.5 + 2**-23

    sys.path.insert(0, str(args.checkout.resolve() / "PrototypeScarlett"))
    from emu.rdna2_exec_ops import _fma, bits_float, float_bits

    def oracle_bits(value):
        if math.isinf(value):
            return 0x7F800000 if value > 0 else 0xFF800000
        return struct.unpack("<I", struct.pack("<f", value))[0]

    result = {}
    for name, words in [("targeted", targeted_words()), ("random", finite_random_words(0x133))]:
        tested, failures = 0, 0
        for inputs in words:
            values = tuple(bits_float(word) for word in inputs)
            actual = float_bits(_fma(*values))
            expected = oracle_bits(fmaf(*values))
            tested += 1
            failures += actual != expected
        result[name] = {"tested": tested, "mismatches": failures}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
