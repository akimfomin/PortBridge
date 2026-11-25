"""Test group-wide tile spacing and its divergent edge collision control."""

from itertools import product
from random import Random


def tile_offsets(threads, maximum, lane, requested, wrong_spacing=False):
    for first in range(0, requested, 4):
        stored = min(4, requested - first)
        width = stored if wrong_spacing else min(4, maximum - first)
        yield from ((1 + first) * threads + lane * width + i for i in range(stored))


def verify(threads, maximum, counts):
    scratch = [-1] * (threads * (1 + maximum))
    values = [[(lane << 10) + n for n in range(count)] for lane, count in enumerate(counts)]
    for lane, (count, words) in enumerate(zip(counts, values)):
        scratch[lane] = count
        offsets = list(tile_offsets(threads, maximum, lane, count))
        assert len(offsets) == len(words)
        for offset, word in zip(offsets, words):
            assert threads <= offset < len(scratch)
            assert scratch[offset] == -1, (threads, maximum, counts, offset)
            scratch[offset] = word
    for lane, count in enumerate(counts):
        assert scratch[lane] == count
        assert [scratch[offset] for offset in tile_offsets(threads, maximum, lane, count)] == values[lane]
    assert scratch.count(-1) == threads * maximum - sum(counts)


def main():
    count = 0
    for maximum in range(7):
        for widths in product(range(maximum + 1), repeat=4):
            verify(4, maximum, widths)
            count += 1
    seed = Random(2080)
    for threads in (32, 64):
        for maximum in (0, 1, 2, 3, 4, 5, 15, 16, 17, 35, 92, 127):
            for _ in range(32):
                verify(threads, maximum, [seed.randrange(maximum + 1) for _ in range(threads)])
                count += 1
    bad = set(tile_offsets(4, 4, 0, 4, True)) & set(tile_offsets(4, 4, 1, 3, True))
    assert bad == {7}
    print(f"{count} mixed-edge layouts preserve every word and never overlap")
    print("Negative control: using the edge's short width instead of capacity aliases lane 0 and 1 at word 7")
    count = sum(1 for _ in tile_offsets(32, 35, 17, 35))
    assert count == 35
    print("35 payload words use nine vector transactions plus the separate tag, versus 35 scalar payload operations")


if __name__ == "__main__":
    main()
