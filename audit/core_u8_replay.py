"""Compare a CPU model with the pinned AnyPS5 pack test's recorded outputs."""

import argparse
from math import floor, isnan
from pathlib import Path
import re
import struct


def table(source, name, width):
    match = re.search(rf"{name}\[32\]\[{width}\]\s*=\s*\{{(.*?)\}};", source, re.S)
    if not match:
        raise ValueError(f"Missing reference table: {name}")
    rows = [[int(value, 16) for value in re.findall(r"0x([0-9a-f]+)u", row, re.I)]
            for row in re.findall(r"\{([^}]+)\}", match[1])]
    if len(rows) != 32 or any(len(row) != width for row in rows):
        raise ValueError(f"Unexpected reference table: {name}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    source = args.fixture.read_text(encoding="utf-8")
    inputs, expected = table(source, "Rows", 4), table(source, "Expected", 10)
    rounding = {"nearest_even": round, "truncate": int, "half_up": lambda value: floor(value + 0.5)}
    misses = {name: [] for name in rounding}
    slots = set()
    for index, ((bits, _, packed, selector), reference) in enumerate(zip(inputs, expected)):
        number = struct.unpack("<f", struct.pack("<I", bits))[0]
        limited = 0 if isnan(number) or number <= 0 else min(number, 255)
        slot = selector & 3
        slots.add(slot)
        shift = slot * 8
        retained = packed & ~(255 << shift)
        for name, rounding_fn in rounding.items():
            actual = retained | (rounding_fn(limited) << shift)
            if actual != reference[6]:
                misses[name].append(index)
    for name, failures in misses.items():
        print(f"{name}: {len(inputs) - len(failures)}/{len(inputs)}, differing rows {failures}")
    print("byte positions:", sorted(slots))
    if misses != {"nearest_even": [], "truncate": [0, 3], "half_up": [5]} or len(slots) != 4:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
