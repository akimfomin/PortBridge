"""Prepare deterministic, duplicate-ID and variable density point fixtures."""
import argparse
from pathlib import Path
import random

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("destination", type=Path)
root = parser.parse_args().destination
root.mkdir(parents=True, exist_ok=True)
cases = [("sparse", 1025, 0.21), ("dense", 4096, 1), ("empty", 257, 0),
         ("boundary", 33, 0.75), ("single", 1, 1)]
for name, size, chance in cases:
    prng = random.Random(36 + size)
    rows = [f"{prng.randrange(100)} {prng.randrange(1 << 32)} {int(prng.random() < chance)}"
            for _ in range(size)]
    (root / f"{name}.txt").write_text("\n".join([str(size), *rows, ""]),
                                      encoding="ascii", newline="\n")
