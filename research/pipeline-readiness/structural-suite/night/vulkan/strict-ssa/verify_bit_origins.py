# SPDX-License-Identifier: MIT
"""Check the exact source bits of the full mask and a single-bit projection.

All data operations inside a fixed-lane branch are OR, fixed shifts and constant
masks. A set of input indices represents the disjunction at one output bit,
making equality of the sets an equality for every assignment to the input bits.
"""
from collections.abc import Iterable

Word = tuple[frozenset[int], ...]
ZERO = frozenset()


def combine(words: Iterable[Word]) -> Word:
    return tuple(frozenset.union(*bits) for bits in zip(*words, strict=True))


def shift_right(word: Word, amount: int) -> Word:
    return word[amount:] + (ZERO,) * amount


def spread(word: Word, member: int) -> Word:
    first = combine((word, shift_right(word, 1)))
    second = combine((first, shift_right(first, 2)))
    kept = tuple(bits if (0x11111111 >> index) & 1 else ZERO for index, bits in enumerate(second))
    return ((ZERO,) * member + kept)[:32]


def main():
    # Four original ballot results. The two low 32-bit words of each result
    # are independent variables, including for every possible helper value.
    ballots = [[tuple(frozenset([64 * member + 32 * half + bit]) for bit in range(32))
                for half in range(2)] for member in range(4)]
    full = [combine(spread(vote[half], member) for member, vote in enumerate(ballots)) for half in range(2)]
    checks = 0
    for guest_wave64 in (False, True):
        for physical_width in (4, 8, 16, 32, 64, 128):
            for host_lane in range(physical_width):
                # Mirror setup_lanes_gfx and the baseline's choice of word.
                relative = host_lane & 31
                guest_lane = host_lane if guest_wave64 else relative
                wide_guest = guest_lane >= 32
                gfx_half = physical_width > 32 and (host_lane >> 5) != 0
                original_word = int(wide_guest) if guest_wave64 else int(gfx_half)
                original = full[original_word][relative]
                # Evaluate the four selects and nibble test of project_quad_ballots.
                half = int(wide_guest if guest_wave64 else gfx_half)
                first = ballots[1 if relative & 1 else 0][half]
                second = ballots[3 if relative & 1 else 2][half]
                selected = second if relative & 2 else first
                offset = relative & 28
                projected = frozenset.union(*selected[offset:offset + 4])
                if projected != original or len(original) != 4:
                    raise AssertionError((guest_wave64, physical_width, host_lane, projected, original))
                checks += 1
    print(f"Matched exact OR dependencies for {checks} receiver/width cases and all 256 symbolic ballot bits.")


if __name__ == "__main__":
    main()
