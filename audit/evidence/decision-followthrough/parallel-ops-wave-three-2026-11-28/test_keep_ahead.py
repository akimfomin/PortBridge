"""Byte-range reference check for VIctory-RDNA #4 (CPU model)."""
import random
import unittest


def keeps_interval(start, stop, address, length):
    end = address + length
    return length == 0 or stop <= address or end <= start


class KeepAhead(unittest.TestCase):
    def test_same_page_does_not_mean_same_bytes(self):
        self.assertTrue(keeps_interval(0x10001, 0x10020, 0x10020, 5))
        self.assertTrue(keeps_interval(0x10001, 0x10020, 0x10000, 1))
        self.assertFalse(keeps_interval(0x10001, 0x10020, 0x10000, 2))

    def test_empty_write_keeps_an_existing_range(self):
        self.assertTrue(keeps_interval(0xFFFF, 0x10002, 0x10000, 0))

    def test_matches_byte_sets_across_a_page_boundary(self):
        rng = random.Random(57)
        for _ in range(10000):
            start = 0x10000 + rng.randrange(-32, 32)
            stop = start + rng.randrange(1, 32)
            address = 0x10000 + rng.randrange(-32, 32)
            length = rng.randrange(32)
            expected = set(range(start, stop)).isdisjoint(range(address, address + length))
            self.assertEqual(keeps_interval(start, stop, address, length), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
