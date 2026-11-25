# SPDX-License-Identifier: MIT
"""Prototype scalar scratch reuse from read/write phases of the split CFG."""

from dataclasses import dataclass
import json
from pathlib import Path

from proof import (AccessWords, Edge, Piece, Program, Result, Value, incompatible_program,
                   layout_fields, linear_program, mixed_program, rebuild_handle, run_split, run_unsplit)


@dataclass(frozen=True)
class Interval:
    value: str
    first: int
    last: int
    words: int


def choose_intervals(program):
    """Use only values actually leaving their defining piece and forwarded later."""
    intervals = []
    for v in program.values:
        crossing = [e for e in program.edges if v.name in e.live]
        if (v.words and any(e.origin == v.piece for e in crossing)
                and any(e.origin > v.piece for e in crossing)
                and all(e.origin >= v.piece for e in crossing)):
            # A piece loads its inputs at entry and writes successors at exit.
            intervals.append(Interval(v.name, 2 * v.piece + 1,
                                      2 * max(e.target for e in crossing), v.words))
    return sorted(intervals, key=lambda i: (i.first, i.value))


def place(intervals):
    """First-fit one/two-word contiguous intervals. Reserve word zero for tags."""
    slots = {}
    active = []
    high = 1
    for interval in intervals:
        active = [entry for entry in active if entry[0] >= interval.first]
        occupied = 1
        for _, mask in active:
            occupied |= mask
        at = 1
        pattern = (1 << interval.words) - 1
        while occupied & (pattern << at):
            at += 1
        slots[interval.value] = tuple(range(at, at + interval.words))
        high = max(high, at + interval.words)
        active.append((interval.last, pattern << at))
    return slots, high


def make_layout(program):
    baseline, original = layout_fields(program)
    candidates = choose_intervals(program)
    stable, dynamic_start = place(candidates)
    specs = program.specs
    widest = max((dynamic_start + sum(specs[n].words for n in e.live if n not in stable)
                  for e in program.edges), default=1)
    naive_fixed = 1 + sum(i.words for i in candidates)
    naive_stride = max((naive_fixed + sum(specs[n].words for n in e.live if n not in stable)
                        for e in program.edges), default=1)
    if widest > baseline:
        return {}, baseline, original, widest, naive_stride
    edges = {}
    for edge in program.edges:
        tail = dynamic_start
        addresses = {}
        for name in edge.live:
            size = specs[name].words
            if not size:
                continue
            if name in stable:
                addresses[name] = stable[name]
            else:
                addresses[name] = tuple(range(tail, tail + size))
                tail += size
        occupied = [slot for slots in addresses.values() for slot in slots]
        assert len(set(occupied)) == len(occupied)
        assert all(0 < slot < baseline for slot in occupied)
        edges[edge.tag] = addresses
    return stable, baseline, edges, widest, naive_stride


def run_interval(program, lane, layout):
    stable, stride, offsets, _, _ = layout
    specs = program.specs
    edges = {edge.tag: edge for edge in program.edges}
    scratch = AccessWords(stride, lane)
    trace = []
    for stage, piece in enumerate(program.pieces):
        tag = scratch.load(stage, "tag", (0,)) if stage else 0
        incoming = edges.get(tag)
        state = {}
        if stage:
            if incoming is None or incoming.target != stage:
                continue
            for name in incoming.live:
                if not specs[name].words:
                    state[name] = rebuild_handle(name, lane)
                elif name not in stable or name in piece.original_operands:
                    state[name] = scratch.load(stage, name, offsets[tag][name])
        else:
            state.update((v.name, rebuild_handle(v.name, lane)) for v in program.values if not v.words)
        step = piece.run(state, lane, tag)
        state.update(step.definitions)
        trace.append((stage, step.observed))
        if step.next_tag:
            outgoing = edges[step.next_tag]
            assert outgoing.origin == stage
            for name in outgoing.live:
                if specs[name].words and (name not in stable or specs[name].piece == stage):
                    scratch.store(stage, name, offsets[step.next_tag][name], state[name])
            scratch.store(stage, "tag", (0,), step.next_tag)
        elif stage + 1 < len(program.pieces):
            scratch.store(stage, "tag", (0,), 0)
    return tuple(trace), scratch.trace


def phased():
    # Sample a closing i64 at stage 2 entry and initialize another at stage 2 exit.
    # Intervals are disjoint despite sharing a dispatch index.
    names = (Value("a", 0, "i64"), Value("b", 2, "i64"))
    pieces = (
        Piece(frozenset(), lambda d, lane, tag: Result(1, {"a": (lane << 33) ^ 0x1234567876543210})),
        Piece(frozenset(), lambda d, lane, tag: Result(2, {})),
        Piece(frozenset({"a"}), lambda d, lane, tag: Result(3, {"b": d["a"] ^ 0x35F7E001AB321095},
                                                          (d["a"],))),
        Piece(frozenset(), lambda d, lane, tag: Result(4, {})),
        Piece(frozenset({"b"}), lambda d, lane, tag: Result(0, {}, (d["b"],))),
    )
    edges = (Edge(1, 0, 1, ("a",)), Edge(2, 1, 2, ("a",)),
             Edge(3, 2, 3, ("b",)), Edge(4, 3, 4, ("b",)))
    return Program(names, edges, pieces)


def branch_budget():
    # The lanes choose mutually exclusive payloads, but the static intervals
    # overlap in stage time. A fixed layout must stay within the compact cap.
    values = (Value("a", 0, "i64"), Value("b", 0, "i64"))
    pieces = (
        Piece(frozenset(), lambda d, lane, tag: Result(1 if lane & 1 else 2,
              {"a": (lane << 32) ^ 0x8123456789ABCDEF, "b": (lane << 34) ^ 0x13579ACE13})),
        Piece(frozenset(), lambda d, lane, tag: Result(3, {})),
        Piece(frozenset(), lambda d, lane, tag: Result(4, {})),
        Piece(frozenset({"a", "b"}), lambda d, lane, tag: Result(0, {}, (d["a" if tag == 3 else "b"],))),
    )
    edges = (Edge(1, 0, 1, ("a",)), Edge(2, 0, 2, ("b",)),
             Edge(3, 1, 3, ("a",)), Edge(4, 2, 3, ("b",)))
    return Program(values, edges, pieces)


def crossed_lifetimes():
    earlier = phased()
    pieces = list(earlier.pieces)
    pieces[-1] = Piece(frozenset({"a", "b"}), lambda d, lane, tag: Result(0, {}, (d["a"] + d["b"],)))
    edges = (*earlier.edges[:2], Edge(3, 2, 3, ("a", "b")), Edge(4, 3, 4, ("a", "b")))
    return Program(earlier.values, edges, tuple(pieces))


def bench_cases():
    result = {}
    for name, program in (
        ("phased_i64", phased()), ("mixed_skipping", mixed_program()),
        ("linear_common", linear_program(5)), ("linear_transient", linear_program(5, anchors=False)),
        ("distinct_edges", incompatible_program()), ("branch_budget", branch_budget()),
        ("crossed_lifetimes", crossed_lifetimes()),
    ):
        layout = make_layout(program)
        slots, stride, _, planned, naive = layout
        logical = [0, 0]
        for lane in range(96):
            original, before, _ = run_split(program, lane, False)
            candidate, after = run_interval(program, lane, layout)
            assert candidate == original == run_unsplit(program, lane), (name, lane)
            logical[0] += 4 * sum(before.values())
            logical[1] += 4 * sum(after.values())
        result[name] = {"lanes": 96, "stable_slots": slots, "baseline_dwords_per_lane": stride,
                        "uncapped_reused_dwords": planned, "uncapped_naive_dwords": naive,
                        "bytes": logical, "budget_fallback": planned > stride}
    phase = result["phased_i64"]
    assert phase["stable_slots"] == {"a": (1, 2), "b": (1, 2)}
    assert phase["baseline_dwords_per_lane"] == phase["uncapped_reused_dwords"] == 3
    assert phase["uncapped_naive_dwords"] == 5
    assert phase["bytes"][0] > phase["bytes"][1]
    rejected = result["branch_budget"]
    assert rejected["budget_fallback"]
    assert rejected["baseline_dwords_per_lane"] == 3
    assert rejected["uncapped_reused_dwords"] == rejected["uncapped_naive_dwords"] == 5
    assert rejected["bytes"][0] == rejected["bytes"][1]
    crossing = result["crossed_lifetimes"]
    assert crossing["stable_slots"] == {"a": (1, 2), "b": (3, 4)}
    assert crossing["baseline_dwords_per_lane"] == crossing["uncapped_reused_dwords"] == 5
    return result


if __name__ == "__main__":
    report = json.dumps(bench_cases(), indent=2) + "\n"
    Path(__file__).with_name("interval-results.json").write_text(report, encoding="utf-8")
    print(report, end="")
