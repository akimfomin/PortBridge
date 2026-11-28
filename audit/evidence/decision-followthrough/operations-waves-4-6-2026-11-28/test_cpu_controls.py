"""Small CPU controls for three independently reviewed contracts.

This module never loads a graphics runtime, third-party workspace or title file.
"""
from collections import deque
from dataclasses import dataclass
import itertools
import unittest


@dataclass
class Readback:
    eager: bool

    def __post_init__(self):
        self.device = {}
        self.host = {}
        self.pending = set()
        self.transfers = 0

    def gpu_write(self, page, data):
        self.device[page] = data
        self.pending.add(page)
        if self.eager:
            self.flush(page)

    def flush(self, page):
        if page in self.pending:
            self.host[page] = self.device[page]
            self.pending.remove(page)
            self.transfers += 1

    def read(self, page):
        self.flush(page)
        return self.host.get(page, b"0000")

    def write_slice(self, page, offset, data):
        current = self.read(page)
        self.host[page] = current[:offset] + data + current[offset + len(data):]


class ReadbackControls(unittest.TestCase):
    def test_observations_match_eager_reference(self):
        # Each case has distinct ordering of CPU observation and replacement.
        scenarios = {
            "no_observation": (("gpu_write", 0, b"1234"),),
            "one_page": (("gpu_write", 0, b"1234"), ("read", 0)),
            "reread": (("gpu_write", 0, b"1234"), ("read", 0), ("read", 0)),
            "unobserved_neighbor": (("gpu_write", 0, b"1234"), ("gpu_write", 1, b"ABCD"), ("read", 0)),
            "observed_neighbor": (("gpu_write", 0, b"1234"), ("gpu_write", 1, b"ABCD"), ("read", 1), ("read", 0)),
            "superseded_before_cpu": (("gpu_write", 0, b"1234"), ("gpu_write", 0, b"ABCD"), ("read", 0)),
            "superseded_after_cpu": (("gpu_write", 0, b"1234"), ("read", 0), ("gpu_write", 0, b"ABCD"), ("read", 0)),
            "read_before_gpu_write": (("read", 0), ("gpu_write", 0, b"ABCD"), ("read", 0)),
            "partial_cpu_write": (("gpu_write", 0, b"1234"), ("write_slice", 0, 1, b"A"), ("read", 0)),
            "second_partial_write": (("gpu_write", 0, b"1234"), ("write_slice", 0, 0, b"A"), ("write_slice", 0, 2, b"B"), ("read", 0)),
            "partial_write_on_cpu_owned_page": (("write_slice", 0, 1, b"A"), ("read", 0)),
            "device_replaces_partial_write": (("gpu_write", 0, b"1234"), ("write_slice", 0, 1, b"A"), ("gpu_write", 0, b"ABCD"), ("read", 0)),
            "interleaved_pages": (("gpu_write", 0, b"1234"), ("gpu_write", 1, b"ABCD"), ("write_slice", 0, 1, b"A"), ("read", 1), ("read", 0)),
            "different_view_same_backing": (("gpu_write", 1, b"ABCD"), ("read", 1), ("write_slice", 1, 1, b"Z"), ("read", 1)),
        }
        expected_counts = [0, 1, 1, 1, 2, 1, 2, 1, 1, 1, 0, 2, 2, 1]
        for (name, commands), count in zip(scenarios.items(), expected_counts, strict=True):
            with self.subTest(case=name):
                eager, lazy = Readback(True), Readback(False)
                for method, *args in commands:
                    self.assertEqual(getattr(eager, method)(*args), getattr(lazy, method)(*args))
                self.assertEqual(lazy.transfers, count)
                self.assertLessEqual(lazy.transfers, eager.transfers)


class DirtyQueueControls(unittest.TestCase):
    def test_no_dirty_event_is_lost(self):
        # The reader clears the queued bit before taking committed ranges.
        # The writer records its range before setting/enqueuing the bit.
        schedules = [
            actions for actions in set(itertools.permutations("CSTWQ"))
            if actions.index("C") < actions.index("S") < actions.index("T")
            and actions.index("W") < actions.index("Q")
        ]
        for actions in sorted(schedules):
            with self.subTest(schedule="".join(actions)):
                queued = True
                waiting = deque([1])
                dirty = [100]
                received = []
                for action in actions:
                    if action == "C":
                        self.assertEqual(waiting.popleft(), 1)
                    elif action == "S":
                        queued = False
                    elif action == "T":
                        received.extend(dirty)
                        dirty.clear()
                    elif action == "W":
                        dirty.append(200)
                    else:
                        if not queued:
                            queued = True
                            waiting.append(1)
                for _ in waiting:
                    received.extend(dirty)
                    dirty.clear()
                self.assertEqual(received, [100, 200])


    def test_wrong_order_can_lose_a_later_event(self):
        # C,T,W,Q,S: a reader taking before it clears its queued bit
        # allows a writer's notification to be suppressed after the take.
        dirty = [100]
        queued = True
        observed = dirty.pop()
        dirty.append(200)
        notified = not queued
        queued = False
        self.assertEqual(observed, 100)
        self.assertFalse(notified)
        self.assertFalse(queued)
        self.assertEqual(dirty, [200])


def valid_present_deltas(samples):
    last = None
    deltas = []
    for value in samples:
        if value is None:
            continue
        if last is not None:
            deltas.append((value - last) & 0xffffffff)
        last = value
    return deltas


class PresentCountControls(unittest.TestCase):
    def test_missing_as_zero_counterexample(self):
        self.assertEqual((0 - 100) & 0xffffffff, 4294967196)
        self.assertEqual(valid_present_deltas([100, None, 104]), [4])

    def test_missing_is_neither_zero_nor_wrap(self):
        samples = [
            ([100, None, 104], [4]),
            ([None, 100, 102], [2]),
            ([0xffffffff, None, 0], [1]),
            ([0xffffffff, 0, 1], [1, 1]),
            ([0, None, 0], [0]),
            ([None, None], []),
            ([10, 10, 10], [0, 0]),
            ([None, 3, None, None, 7, 9], [4, 2]),
            ([10, None, 12, None, 15], [2, 3]),
            ([0xfffffffd, None, 2], [5]),
            ([0, None, 1], [1]),
            ([1, 2, None], [1]),
            ([0xfffffffe, 0xffffffff, None, 0], [1, 1]),
            ([8, 9, 10, None, 10], [1, 1, 0]),
            ([None, 0, 1, None, 2, 3], [1, 1, 1]),
            ([14], []),
        ]
        for index, (received, expected) in enumerate(samples):
            with self.subTest(case=index):
                self.assertEqual(valid_present_deltas(received), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
