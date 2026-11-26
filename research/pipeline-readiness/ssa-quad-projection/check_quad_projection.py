"""Exhaustively compare the observable bits of a quad for defined guest register values."""
from itertools import product

def check():
    cases = 0
    for width in (32, 64):
        for lane, active_nibble, compare_nibble, background in product(
                range(width), range(16), range(16), (0, 0xaaaaaaaa, 0x55555555, 0xffffffff)):
            base = lane & ~3
            shift = base & 31
            word = (background & ~(15 << shift)) | (active_nibble << shift)
            lo, hi = (word, ~word & 0xffffffff) if base < 32 else (~word & 0xffffffff, word)
            packed = 0
            for index in range(4):
                old_lane = base | index
                old_word = hi if width == 64 and old_lane >= 32 else lo
                old_active = (old_word >> (old_lane & 31)) & 1
                packed |= (old_active & ((compare_nibble >> index) & 1)) << index
            selected = hi if width == 64 and base >= 32 else lo
            window = selected >> shift
            for index in range(4):
                projected = bool(window & (1 << index)) and bool(compare_nibble & (1 << index))
                assert bool(packed & (1 << index)) == projected
                cases += 1
    return cases

if __name__ == "__main__":
    print(f"{check()} matched ballot operands")
