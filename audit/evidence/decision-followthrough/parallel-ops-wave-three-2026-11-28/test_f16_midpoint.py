# Reproduce a documented binary16 midpoint on CPU without a shader toolchain.
from decimal import Decimal, localcontext
import struct
import unittest


def half(bits):
    return struct.unpack("<e", struct.pack("<H", bits))[0]


def bits(value):
    return struct.unpack("<H", struct.pack("<e", value))[0]


class ExpMidpoint(unittest.TestCase):
    def test_rounding_twice_changes_the_midpoint_result(self):
        x = Decimal.from_float(half(0x11C5))
        low, high = (Decimal.from_float(half(h)) for h in (0x3C00, 0x3C01))
        with localcontext() as ctx:
            ctx.prec = 60
            y = (Decimal(2).ln() * x).exp()
            middle = (low + high) / 2
            self.assertGreater(y, middle)
            self.assertLess(y, high)
            self.assertEqual(bits(float(y)), 0x3C01)
            widened = struct.unpack("<f", struct.pack("<f", float(y)))[0]
            self.assertEqual(Decimal.from_float(widened), middle)
            self.assertEqual(bits(widened), 0x3C00)

    def test_exact_controls(self):
        for code, expected in [(0x0000, 0x3C00), (0xBC00, 0x3800)]:
            self.assertEqual(bits(2 ** half(code)), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
