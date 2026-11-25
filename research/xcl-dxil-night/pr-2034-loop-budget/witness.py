# SPDX-License-Identifier: MIT
"""Exercise the two guard predicates in XCL #2034 0e4e10e with finite CFGs."""

from dataclasses import dataclass


WORD_MASK = (1 << 32) - 1


@dataclass(frozen=True)
class Block:
    successors: tuple[int, ...]
    add: int = 0
    mark: bool = False
    branch_until: int = 0


def headers(graph):
    visiting = set()
    done = set()
    result = set()

    def visit(block):
        visiting.add(block)
        for target in graph[block].successors:
            if target in visiting:
                result.add(target)
            elif target not in done:
                visit(target)
        visiting.remove(block)
        done.add(block)

    visit(0)
    return result


def run(graph, budget, guard, max_steps):
    loop_headers = headers(graph) if guard != "packed" else packed_headers(graph)
    current = 0
    value = 0
    marked = False
    for _ in range(max_steps):
        if guard != "compact" and current in loop_headers:
            if budget == 0:
                return value, marked
            budget -= 1
        block = graph[current]
        value += block.add
        marked |= block.mark
        if not block.successors:
            return value, marked
        branch = int(len(block.successors) == 2 and value >= block.branch_until)
        successor = block.successors[branch]
        if guard == "compact" and successor <= current:
            if budget == 0:
                return value, marked
            budget -= 1
        current = successor
    raise AssertionError("fixture exceeded its finite step bound")


def packed_headers(graph):
    actual_headers = headers(graph)
    keys = []
    for i, block in enumerate(graph):
        if block.successors:
            taken, fallthrough = block.successors[0], block.successors[-1]
            offsets = ((taken - i) & WORD_MASK, (fallthrough - i) & WORD_MASK)
        else:
            offsets = (0, 0)
        keys.append((*offsets, i in actual_headers))
    steps = sorted(set(keys))
    step_width = max(1, (len(steps) - 1).bit_length())
    # Some cases intentionally share classes; all quantities cross-check after packing.
    classes = [i % 5 for i in range(len(graph))]
    class_width = max(1, max(classes).bit_length())
    entry_width = class_width + step_width
    words = [0] * ((len(keys) * entry_width + 31) // 32 + 1)
    for block, step in enumerate(keys):
        entry = classes[block] | steps.index(step) << class_width
        index, shift = divmod(block * entry_width, 32)
        words[index] |= (entry << shift) & WORD_MASK
        words[index + 1] |= entry << shift >> 32
    packed_steps = [(((taken << 1) | header) & WORD_MASK, fallthrough)
                    for taken, fallthrough, header in steps]
    assert len(words) + len(packed_steps) * 2 == (len(keys) * entry_width + 31) // 32 + 1 + len(steps) * 2
    decoded_headers = set()
    for block, wanted in enumerate(keys):
        index, shift = divmod(block * entry_width, 32)
        value = words[index] >> shift | ((words[index + 1] << 1) << (31 - shift)) & WORD_MASK
        assert value & ((1 << class_width) - 1) == classes[block]
        pair = (value >> class_width) & ((1 << step_width) - 1)
        guarded_taken, f = packed_steps[pair]
        guarded = bool(guarded_taken & 1)
        taken = guarded_taken >> 1 | (guarded_taken & (1 << 31))
        assert (taken, f, guarded) == wanted
        if graph[block].successors:
            assert (block + taken) & WORD_MASK == graph[block].successors[0]
            assert (block + f) & WORD_MASK == graph[block].successors[-1]
        else:
            assert (taken, f, guarded) == (0, 0, False)
        if guarded:
            decoded_headers.add(block)
    return decoded_headers


def checks():
    stock_budget = 1 << 16
    for terminal in (stock_budget - 1, stock_budget):
        below_limit = (
            Block((1,)),
            Block((1, 2), add=1, branch_until=terminal),
            Block((), mark=True),
        )
        for guard in ("header", "compact", "packed"):
            assert run(below_limit, stock_budget, guard, stock_budget + 4) == (terminal, True)
    finite_loop = (
        Block((1,)),
        Block((1, 2), add=1, branch_until=stock_budget + 1),
        Block((), mark=True),
    )
    assert headers(finite_loop) == {1}
    assert run(finite_loop, stock_budget, "header", stock_budget + 4) == (65536, False)
    assert run(finite_loop, stock_budget, "compact", stock_budget + 4) == (65537, True)
    assert run(finite_loop, stock_budget, "packed", stock_budget + 4) == (65536, False)

    reverse_layout = (
        Block((4,)),
        Block((), mark=True),
        Block((1,), add=1),
        Block((2,), add=1),
        Block((3,), add=1),
    )
    assert not headers(reverse_layout)
    assert run(reverse_layout, 1, "header", 6) == (3, True)
    assert run(reverse_layout, 1, "compact", 6) == (2, False)
    assert run(reverse_layout, 1, "packed", 6) == (3, True)

    # Blocks 1 and 2 lower the same payload with the same +1 successor offset.
    # Only block 2 is a loop header; that bit must be part of the entry identity.
    merged_class = (
        Block((1,)),
        Block((2,), add=1),
        Block((3,), add=1),
        Block((2, 4), branch_until=3),
        Block((), mark=True),
    )
    assert headers(merged_class) == {2}
    assert merged_class[1].add == merged_class[2].add
    assert merged_class[1].successors[0] - 1 == merged_class[2].successors[0] - 2
    assert run(merged_class, 0, "header", 8) == (1, False)
    assert run(merged_class, 0, "compact", 8) == (2, False)
    assert run(merged_class, 0, "packed", 8) == (1, False)

    # Multiple packed words and guarded, unguarded, positive, negative and end steps.
    many_entries = [Block((i + 1,)) for i in range(39)] + [Block((), mark=True)]
    many_entries[38] = Block((8, 39), branch_until=0)
    assert packed_headers(many_entries) == headers(many_entries) == {8}
    assert run(many_entries, 1, "packed", 45) == (0, True)

    print("stock budget, reversed acyclic layout and shared-class header witnesses passed")


if __name__ == "__main__":
    checks()
