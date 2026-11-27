"""Model the sparse buffer selection and rejection boundary in Continued #2405."""

from dataclasses import dataclass


@dataclass
class Heap:
    arena_backed: bool = False
    memory_type: int | None = None


def contains_type(mask, index):
    return bool(mask & (1 << index))


def bind(heap, probe_mask, mask, *, arena=0, patched=True, reuse_first=False):
    if not mask & probe_mask:
        return "resource_creation_rejected"
    if reuse_first and heap.memory_type is not None:
        return "eligible" if contains_type(mask, heap.memory_type) else "heap_rejected"
    use_arena = contains_type(probe_mask, arena) and (
        not patched or contains_type(mask, arena)
    )
    if use_arena:
        if heap.memory_type is not None:
            return "heap_rejected"
        heap.arena_backed = True
        backing = arena
    else:
        if heap.arena_backed:
            return "heap_rejected"
        if heap.memory_type is None:
            candidates = mask & probe_mask if patched else probe_mask
            heap.memory_type = (candidates & -candidates).bit_length() - 1
        backing = heap.memory_type
    return "eligible" if contains_type(mask, backing) else "queue_validation_rejected"


def main():
    probe, first, second = 0b111, 0b010, 0b100
    shared = Heap()
    cases = {
        "first_old": bind(Heap(), probe, first, patched=False),
        "first_patched": bind(shared, probe, first),
        "existing_backing_type": shared.memory_type,
        "second_same_heap": bind(shared, probe, second),
        "second_with_overlap": bind(shared, probe, first | second),
        "second_separate_heap": bind(Heap(), probe, second),
        "resource_disjoint_from_probe": bind(Heap(), probe, 0b1000),
    }
    assert cases == {
        "first_old": "queue_validation_rejected",
        "first_patched": "eligible",
        "existing_backing_type": 1,
        "second_same_heap": "queue_validation_rejected",
        "second_with_overlap": "eligible",
        "second_separate_heap": "eligible",
        "resource_disjoint_from_probe": "resource_creation_rejected",
    }
    assert shared.memory_type == 1
    overlap_heap = Heap()
    assert bind(overlap_heap, 0x12, 0x02, arena=4) == "eligible"
    assert bind(overlap_heap, 0x12, 0x12, arena=4) == "heap_rejected"
    assert bind(overlap_heap, 0x12, 0x12, arena=4, reuse_first=True) == "eligible"
    assert bind(shared, probe, second, reuse_first=True) == "heap_rejected"
    assert bind(shared, probe, first, reuse_first=True) == "eligible"
    cases["compatible_reuse_after_guard"] = "eligible"
    cases["incompatible_reuse_after_guard"] = "heap_rejected"
    for mask in range(1, 16):
        heap = Heap()
        verdict = bind(heap, probe, mask)
        assert (verdict == "eligible") == bool(mask & probe)
        if verdict == "eligible":
            backing = 0 if heap.arena_backed else heap.memory_type
            assert contains_type(mask, backing)
    print(cases)


if __name__ == "__main__":
    main()
