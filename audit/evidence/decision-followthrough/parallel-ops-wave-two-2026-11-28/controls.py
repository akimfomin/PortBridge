"""Independent source-derived controls. All inputs are generated constants."""
import itertools
import random
import struct
import unittest


def xcl_groups(x, y, z, cap):
    if max(x, y, z) > 65535:
        return 0
    xy = x * y
    if z and xy > (1 << 22) // z:
        return 0
    return min(xy * z, cap)


def dispatch_slots(live):
    """Continue assigning compact slots to the actual work."""
    emitted = []
    for alive in live:
        if alive:
            emitted.append(len(emitted))
    return emitted


def can_observe_label(own, submitted, overwritten, completion, cpu_write):
    return own and not (submitted or overwritten or completion or cpu_write)


def reuse_candidate(probe_succeeded, stale, published_available):
    if probe_succeeded:
        return "retain-created", 1
    if published_available:
        return "try-published", 2
    return "propagate-failure", 1


def choose_local(shortfall, released_to_driver, retained, cache):
    if shortfall <= 0:
        return ("local", 0, 0)
    first = min(shortfall, retained) if released_to_driver else 0
    second = min(shortfall - first, cache)
    return ("local" if first + second >= shortfall else "host", first, second)


def bits(v):
    return struct.unpack("<H", struct.pack("<e", v))[0]


def overflowing_divided(clamp_first):
    f16_max = 65504.0
    v = 70000.0
    return bits(min(v, f16_max) / 2 if clamp_first else min(v / 2, f16_max))


class NewControls(unittest.TestCase):
    def test_exact_boundary_precedes_record_cap(self):
        self.assertEqual(xcl_groups(128, 256, 128, 1000), 1000)
        self.assertEqual(xcl_groups(128, 256, 129, 1000), 0)
        self.assertEqual(xcl_groups(65536, 1, 1, 1000), 0)

    def test_xcl_integer_group_guard_against_wide_oracle(self):
        rng = random.Random(17)
        for _ in range(25000):
            x, y, z = (rng.choice((0, 1, 2, 63, 64, 65, 1024, 65535, 65536, 0xFFFFFFFF))
                       if rng.randrange(2) else rng.randrange(0, 0x10000) for _ in range(3))
            want = min(x * y * z, 1000) if max(x, y, z) <= 65535 and x * y * z <= 1 << 22 else 0
            self.assertEqual(xcl_groups(x, y, z, 1000), want)

    def test_dropped_indirect_never_spends_a_live_slot(self):
        for live in ((False, True, False, True), (True, False, False, True)):
            self.assertEqual(dispatch_slots(live), [0, 1])
            wrong = [i for i, alive in enumerate(live) if alive]
            self.assertNotEqual(wrong, [0, 1])

    def test_label_observation_rejects_any_missing_condition(self):
        combinations = list(itertools.product((False, True), repeat=5))
        accepted = [f for f in combinations if can_observe_label(*f)]
        self.assertEqual(accepted, [(True, False, False, False, False)])

    def test_partial_label_page_needs_two_sources(self):
        from_gpu = [0x11111111, 0x22222222, 0x33333333]
        staged = [0xAAAAAAAA, None, 0xCCCCCCCC]
        usable = [True, False, False]
        values = [value if known else from_gpu[i] for i, (known, value) in enumerate(zip(usable, staged))]
        self.assertEqual(values, [0xAAAAAAAA, 0x22222222, 0x33333333])

    def test_successful_stale_probe_and_failed_candidate_are_different(self):
        self.assertEqual(reuse_candidate(True, True, True), ("retain-created", 1))
        self.assertEqual(reuse_candidate(False, False, True), ("try-published", 2))
        self.assertEqual(reuse_candidate(False, False, False), ("propagate-failure", 1))

    def test_cached_pool_frees_driver_bytes_before_other_eviction(self):
        self.assertEqual(choose_local(80, True, 100, 200), ("local", 80, 0))
        self.assertEqual(choose_local(80, True, 35, 100), ("local", 35, 45))
        self.assertEqual(choose_local(80, False, 100, 15), ("host", 0, 15))

    def test_fp16_clamp_position(self):
        self.assertEqual(overflowing_divided(True), 0x77FF)
        self.assertNotEqual(overflowing_divided(False), 0x77FF)
        self.assertEqual(bits(min(65504.0, 65000.0 * 2)), 0x7BFF)


if __name__ == "__main__":
    unittest.main(verbosity=2)
