"""Decode the captured positive-only run without changing its acceptance criterion."""

from pathlib import Path
import re
import struct
import sys


stored = {
    28: ((32, 0, 255, 128), 255),
    11: ((16384, 0, 0, 32768), 65535),
    13: ((-16384, 8192, 32767, 16384), 32767),
    31: ((-64, 32, 127, 64), 127),
}
path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("native-hardware.txt")
text = path.read_text(encoding="utf-8-sig")
strict = True
seen = set()
for line in text.splitlines():
    match = re.fullmatch(r"format=(\d+) support1=([\da-f]+) values=((?:[\da-f]{8} ?){4})", line)
    if match is None:
        continue
    fmt = int(match[1])
    assert fmt not in seen
    codes, scale = stored[fmt]
    bits = [bytes.fromhex(word) for word in match[3].split()]
    ideal = [struct.pack(">f", code / scale) for code in codes]
    read_values = [struct.unpack(">f", word)[0] for word in bits]
    ideal_values = [struct.unpack(">f", word)[0] for word in ideal]
    max_error = max(abs(actual - expected) for actual, expected in zip(read_values, ideal_values))
    strict &= max_error <= 2e-6
    seen.add(fmt)
    print(f"format={fmt} bit_exact={sum(a == b for a, b in zip(bits, ideal))}/4 max_abs_error={max_error:.10g} "
          f"nearest_input_codes={tuple(round(value * scale) for value in read_values)} expected={codes}")

assert seen == set(stored)
print(f"strict_abs_tolerance=2e-6 strict_numeric_pass={strict}")
