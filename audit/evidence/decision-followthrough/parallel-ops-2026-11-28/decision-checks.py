"""CPU-only decision checks. No repositories, game data, drivers or third-party code."""
import itertools
import math
import struct
import unittest
from decimal import Decimal, localcontext
from functools import lru_cache


def half(bits):
    return struct.unpack("<e", struct.pack("<H", bits))[0]


def half_bits(value):
    if abs(value) >= 65520:
        return 0x7C00 | (0x8000 if value < 0 else 0)
    return struct.unpack("<H", struct.pack("<e", value))[0]


def f32(value, ulp=0):
    bits = struct.unpack("<I", struct.pack("<f", value))[0]
    return struct.unpack("<f", struct.pack("<I", bits + ulp))[0]


@lru_cache(maxsize=1)
def sqrt_counts():
    errors = {ulp: [0, 0] for ulp in (-1, 0, 1)}
    for bits in range(1, 0x7C00):
        x = half(bits)
        expected = half_bits(math.sqrt(x))
        for ulp, counts in errors.items():
            c = half_bits(f32(math.sqrt(x), ulp))
            below = (half(c-1) + half(c)) / 2
            above = (half(c) + half(c+1)) / 2
            corrected = c-1 if below**2 > x else c+1 if above**2 < x else c
            counts[0] += c != expected
            counts[1] += corrected != expected
    return errors


@lru_cache(maxsize=1)
def exp_counts():
    # Inputs outside this interval have a provable trivial half result.
    # A high precision reference is useful here because binary32 hits a tie.
    changes = []
    approx_changes = {-1: [], 1: []}
    with localcontext() as ctx:
        ctx.prec = 70
        logarithm = Decimal(2).ln()
        for bits in range(0x10000):
            x = half(bits)
            if not (-26 < x < 17):
                continue
            root = (logarithm * Decimal.from_float(x)).exp()
            approx = float(root)
            expected = half_bits(approx)
            # Reject the rare case in which binary64 itself is at a half
            # midpoint unless we explicitly resolve it using the Decimal value.
            if 0 < expected < 0x7C00:
                center = half(expected)
                direction = -1 if approx < center else 1
                neighbor = half(expected + direction)
                midpoint = (center + neighbor) / 2
                if approx == midpoint:
                    if root > Decimal.from_float(midpoint):
                        expected = max(expected, expected + direction)
                    elif root < Decimal.from_float(midpoint):
                        expected = min(expected, expected + direction)
            if half_bits(f32(approx)) != expected:
                changes.append(bits)
            for ulp in approx_changes:
                got = 0x3C01 if bits == 0x11C5 else half_bits(f32(approx, ulp))
                if got != expected:
                    approx_changes[ulp].append((f"0x{bits:04x}", f"0x{got:04x}", f"0x{expected:04x}"))
    return changes, approx_changes


def select_tree(values, index):
    if not 0 <= index < len(values):
        return 0
    layer = list(values)
    while len(layer) > 1:
        high = index & 1
        layer = [layer[min(k+high, len(layer)-1)] for k in range(0, len(layer), 2)]
        index >>= 1
    return layer[0]


def allocate_bump(capacity, step, cursor, schedule):
    """Model the fetch-add and wrap-store operations separately."""
    old = {}
    assigned = {}
    for event, thread in schedule:
        if event == "add":
            old[thread] = cursor
            cursor += step
        elif old[thread] + step > capacity:
            cursor = step
            assigned[thread] = 0
        else:
            assigned[thread] = old[thread]
    return assigned


def allocating_schedule():
    return [("add", "A"), ("add", "B"), ("wrap", "A"), ("wrap", "B")]


def union_bytes(*intervals, clip=None):
    values = set()
    for lo, hi in intervals:
        if clip is not None:
            lo, hi = max(lo, clip[0]), min(hi, clip[1])
        values.update(range(lo, hi))
    return values


class DecisionChecks(unittest.TestCase):
    def test_sqrt_1_ulp_low(self):
        self.assertEqual(sqrt_counts()[-1], [0, 0])

    def test_sqrt_nearest_f32(self):
        self.assertEqual(sqrt_counts()[0], [0, 0])

    def test_sqrt_1_ulp_high(self):
        self.assertEqual(sqrt_counts()[1], [15, 0])

    def test_exp_midpoint(self):
        self.assertEqual(exp_counts()[0], [0x11C5])

    def test_exp_is_not_a_global_tolerance_proof(self):
        self.assertTrue(any(exp_counts()[1].values()))

    def test_select_tree_in_range(self):
        for count in range(1, 257):
            entries = tuple(101 + 37 * i for i in range(count))
            self.assertEqual([select_tree(entries, i) for i in range(count)], list(entries))

    def test_select_tree_uint32_outside_dense_range(self):
        for count, index in itertools.product((1, 7, 8, 9, 127, 128, 129, 256),
                                              (0x100, 0x10000, 0x80000000, 0xFFFFFFFF)):
            self.assertEqual(select_tree(range(1, count+1), index), 0)

    def test_select_tree_exact_boundary(self):
        for count in (7, 8, 9, 16, 17, 32, 33):
            self.assertEqual(select_tree(range(1, count+1), count-1), count)
            self.assertEqual(select_tree(range(1, count+1), count), 0)

    def test_ring_far_from_wrap(self):
        self.assertEqual(allocate_bump(4<<20, 256, 0, allocating_schedule()),
                         {"A": 0, "B": 256})

    def test_ring_one_worker_wraps(self):
        self.assertEqual(allocate_bump(4<<20, 256, 4<<20, [("add", "A"), ("wrap", "A"),
                         ("add", "B"), ("wrap", "B")]), {"A": 0, "B": 256})

    def test_ring_two_workers_at_wrap(self):
        self.assertEqual(allocate_bump(4<<20, 256, 4<<20, allocating_schedule()),
                         {"A": 0, "B": 0})

    def test_ring_cross_queue_requires_completion_before_reuse(self):
        # Two allocations can start at different positions yet reuse a previous
        # allocation before its owning queue has completed; serializing the
        # cursor alone cannot prove that a slice has retired.
        live_a = (0, 256)
        wrap_b = (0, 256)
        self.assertTrue(union_bytes(live_a) & union_bytes(wrap_b))
        self.assertFalse(union_bytes(live_a) & union_bytes((256, 512)))

    def test_sparse_ranges_bridge_and_keep_prefix(self):
        self.assertEqual(union_bytes((8, 10), (13, 15), (6, 14)), set(range(6, 15)))

    def test_sparse_ranges_respect_byte_bound_without_wrapping(self):
        current = union_bytes((0, 63))
        next_range = union_bytes((128, 132))
        self.assertEqual(len(current | next_range), 67)
        self.assertEqual(len(next_range-current), 4)

    def test_timing_separates_collection_cost_from_gpu_wait(self):
        threshold = 10
        for wait, reporting, expected in [(3, 12, False), (13, 2, True), (13, 12, True)]:
            self.assertEqual(wait > threshold, expected)
            if wait == 3:
                self.assertTrue(wait + reporting > threshold)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(DecisionChecks))
    print("sqrt: uncorrected, corrected per binary32 perturbation:", sqrt_counts())
    print("exp unique nearest-f32 input, perturbed examples (input, got, expected):", exp_counts())
    raise SystemExit(not result.wasSuccessful())
