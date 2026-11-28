"""Independent CPU reference for binary16 exp2 rounding at finite midpoints."""
from bisect import bisect_left
from decimal import Decimal, localcontext
from math import frexp
from struct import pack, unpack


def half(bits):
    return unpack("<e", pack("<H", bits))[0]


def main():
    finite_outputs = [Decimal.from_float(half(bits)) for bits in range(0x7C00)]
    thresholds = {Decimal("0.5"): [], Decimal(2): [], Decimal(4): [], Decimal(8): []}
    checked = 0
    double_rounding = []
    with localcontext() as context:
        context.prec = 80
        log_two = Decimal(2).ln()
        for bits in range(0x10000):
            x = half(bits)
            if not -25 < x < 16:
                continue
            exact = (Decimal.from_float(x) * log_two).exp()
            upper = bisect_left(finite_outputs, exact)
            # Only interior pairs of finite results. Exclude zero and overflow boundaries.
            if upper < 2 or upper >= len(finite_outputs):
                continue
            lower = upper - 1
            midpoint = (finite_outputs[lower] + finite_outputs[upper]) / 2
            ulp = Decimal(2) ** (frexp(float(midpoint))[1] - 24)
            distance = abs(exact - midpoint) / ulp
            expected = lower if exact < midpoint or (exact == midpoint and lower % 2 == 0) else upper
            as_f32 = unpack("<f", pack("<f", float(exact)))[0]
            through_f32 = unpack("<H", pack("<e", as_f32))[0]
            checked += 1
            if through_f32 != expected:
                double_rounding.append((bits, expected, through_f32))
            for bound, inputs in thresholds.items():
                if distance < bound:
                    inputs.append((bits, expected))
    print(f"interior input words checked: {checked}")
    for bound, inputs in thresholds.items():
        print(f"under {bound} f32 ULP: {len(inputs)}")
        if bound == Decimal("0.5"):
            print(" ".join(f"{bits:#06x}->{word:#06x}" for bits, word in inputs))
    print("different via f32: " + ", ".join(
        f"{bits:#06x}: exact {expected:#06x}, via f32 {observed:#06x}"
        for bits, expected, observed in double_rounding))


if __name__ == "__main__":
    main()
