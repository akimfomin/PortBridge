# SPDX-License-Identifier: GPL-3.0-or-later
"""Byte-level CPU model for consecutive copies in one relay fetch list."""

import random
import unittest
from dataclasses import dataclass


CHUNK = 64 * 1024
LIMIT = 1024 * 1024


@dataclass
class Copy:
    source: int
    start: int
    end: int
    destination: int


def pack(pieces):
    commands = []
    offsets = []
    written = 0
    for source, start, end in pieces:
        active = commands[-1] if commands else None
        if (active is not None and active.source == source and
                active.start <= start <= active.end and end - active.start <= LIMIT):
            offsets.append(active.destination + start - active.start)
            written += max(0, end - active.end)
            active.end = max(active.end, end)
        else:
            commands.append(Copy(source, start, end, written))
            offsets.append(written)
            written += end - start
    return commands, offsets, written


def execute_mapping(buffers, pieces):
    commands, offsets, count = pack(pieces)
    staged = bytearray(count)
    filled = 0
    for copy in commands:
        size = copy.end - copy.start
        assert copy.destination == filled and 0 < size <= LIMIT
        staged[filled:filled + size] = buffers[copy.source][copy.start:copy.end]
        filled += size
    assert filled == count
    rows = [bytes(staged[at:at + end - start]) for (_, start, end), at in zip(pieces, offsets, strict=True)]
    return rows, len(commands), count


class RelayCopy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = random.Random(470)
        cls.buffers = [rng.randbytes(2 * LIMIT) for _ in range(2)]

    def assert_equal_schedule(self, pieces):
        packed, n, size = execute_mapping(self.buffers, pieces)
        self.assertEqual(packed, [self.buffers[owner][a:b] for owner, a, b in pieces])
        self.assertLessEqual(n, len(pieces))
        self.assertLessEqual(size, sum(b - a for _, a, b in pieces))
        return n, size

    def test_adjacent_16_piece_control(self):
        pieces = [(0, a, a + CHUNK) for a in range(0, LIMIT, CHUNK)]
        self.assertEqual(self.assert_equal_schedule(pieces), (1, LIMIT))

    def test_sparse_negative_control(self):
        pieces = [(0, a, a + CHUNK) for a in range(0, 2 * LIMIT, 2 * CHUNK)]
        self.assertEqual(self.assert_equal_schedule(pieces), (16, LIMIT))

    def test_different_clips_overlap_within_one_page(self):
        pieces = [(0, 0, 48 * 1024), (0, 32 * 1024, CHUNK), (0, CHUNK, 96 * 1024)]
        self.assertEqual(sum(b - a for _, a, b in pieces), 112 * 1024)
        self.assertEqual(self.assert_equal_schedule(pieces), (1, 96 * 1024))

    def test_owner_gap_backward_and_one_mib_cut(self):
        pieces = [(0, 0, CHUNK), (1, CHUNK, 2 * CHUNK), (1, 0, CHUNK), (1, 3 * CHUNK, 4 * CHUNK)]
        self.assertEqual(self.assert_equal_schedule(pieces), (4, 4 * CHUNK))
        whole = [(0, a, a + CHUNK) for a in range(0, 2 * LIMIT, CHUNK)]
        self.assertEqual(self.assert_equal_schedule(whole), (2, 2 * LIMIT))

    def test_random_clips_reproduce_every_original_ordered_read(self):
        rng = random.Random(442470)
        for _ in range(250):
            pieces = []
            for _ in range(rng.randrange(5, 70)):
                owner, page = rng.randrange(2), rng.randrange(8)
                begin = CHUNK * page + rng.randrange(CHUNK)
                end = rng.randrange(begin + 1, CHUNK * (page + 1) + 1)
                pieces.append((owner, begin, end))
            pieces.sort(key=lambda p: (p[0], p[1]))
            cut = rng.randrange(len(pieces))
            pieces = pieces[cut:] + pieces[:cut]
            self.assert_equal_schedule(list(dict.fromkeys(pieces)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
