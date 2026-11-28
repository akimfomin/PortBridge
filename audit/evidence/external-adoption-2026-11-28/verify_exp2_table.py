"""Independently check the 70 FP16 exp2 corrections against mathematical rounding."""
from bisect import bisect_left
from decimal import Decimal, localcontext
from math import frexp
import re
from struct import pack, unpack
from urllib.request import urlopen


PIN = "41d79706aa9f024dff5b77d6cbc9d2598fb1434d"
SOURCE = "https://raw.githubusercontent.com/R0Y00/Xbox2Windows/" + PIN + "/src/gfx1013_direct_compute.inl"


def half(bits):
    return unpack("<e", pack("<H", bits))[0]


def main():
    values = [Decimal.from_float(half(word)) for word in range(0x7c00)]
    with urlopen(SOURCE, timeout=10) as response:
        source = response.read().decode("utf-8")
    table = re.search(r"exp_f16_midpoints\[\]\s*\{(.*?)\};", source, re.S)
    assert table
    raw = re.findall(r"\{\s*(0x[0-9a-f]+),\s*(0x[0-9a-f]+)\s*\}", table[1])
    published = {int(key, 16): int(value, 16) for key, value in raw}
    assert len(raw) == len(published)
    reference = {}
    relative = {}
    with localcontext() as ctx:
        ctx.prec = 96
        ln2 = Decimal(2).ln()
        for word in range(0x10000):
            x = half(word)
            if not -25 < x < 16:
                continue
            exact = (Decimal.from_float(x) * ln2).exp()
            upper = bisect_left(values, exact)
            if upper < 2 or upper == len(values):
                continue
            lower = upper - 1
            midpoint = (values[lower] + values[upper]) / 2
            distance = abs(exact - midpoint)
            expected = lower if exact < midpoint else upper
            if distance < Decimal(2) ** (frexp(float(exact))[1] - 21):
                reference[word] = expected
            if distance <= exact * Decimal(2) ** -21:
                relative[word] = expected
    assert published == reference, (published.keys() - reference.keys(), reference.keys() - published.keys())
    assert relative.items() <= published.items()
    print(f"{len(published)}/70 table values match the independent reference; {len(relative)} near the relative-error bound")
    print("Explicit exp2(-25) tie is covered separately by the emitter, outside this interior-table check.")


if __name__ == "__main__":
    main()
