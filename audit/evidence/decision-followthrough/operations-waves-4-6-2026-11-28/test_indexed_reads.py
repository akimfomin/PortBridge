"""Model bounds and known-bit pruning for M0-indexed register reads."""
import unittest


def read_model(values, index, known_zero=0):
    if index & known_zero:
        raise ValueError("unproven bound")
    span = 1 << (len(values) - 1).bit_length()
    if index >= span:
        return 0
    low, high = 0, span
    while high - low > 1:
        half = (low + high) // 2
        if index < half:
            high = half
        else:
            low = half
    return values[low] if low < len(values) else 0


class IndexedRead(unittest.TestCase):
    def test_constrained_and_open_select_tree(self):
        for count in (1, 3, 5, 64, 118, 129):
            values = [10_000 + slot for slot in range(count)]
            for mask in (0, 3):
                with self.subTest(count=count, known_zero=mask):
                    for index in range(2 * count + 17):
                        if index & mask:
                            continue
                        expected = values[index] if index < count else 0
                        self.assertEqual(read_model(values, index, mask), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
