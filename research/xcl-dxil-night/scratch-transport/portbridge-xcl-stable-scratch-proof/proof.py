# SPDX-License-Identifier: MIT
"""Synthetic scratch transport oracle for an independent XCL #2080 review."""

from collections import Counter
from dataclasses import dataclass
from typing import Callable


DWORD = (1 << 32) - 1
QWORD = (1 << 64) - 1


@dataclass(frozen=True)
class Value:
    name: str
    piece: int
    kind: str = "i32"

    @property
    def words(self):
        return {"i32": 1, "f32": 1, "i64": 2, "handle": 0}[self.kind]


@dataclass(frozen=True)
class Edge:
    tag: int
    origin: int
    target: int
    live: tuple[str, ...]


@dataclass(frozen=True)
class Result:
    next_tag: int
    definitions: dict[str, int]
    observed: tuple[int, ...] = ()


@dataclass(frozen=True)
class Piece:
    original_operands: frozenset[str]
    run: Callable[[dict[str, int], int, int], Result]


@dataclass(frozen=True)
class Program:
    values: tuple[Value, ...]
    edges: tuple[Edge, ...]
    pieces: tuple[Piece, ...]

    def __post_init__(self):
        names = {value.name for value in self.values}
        tags = {edge.tag for edge in self.edges}
        if len(names) != len(self.values) or len(tags) != len(self.edges) or 0 in tags:
            raise ValueError("duplicate value/tag or reserved terminal tag")
        for edge in self.edges:
            if (not 0 <= edge.origin < edge.target < len(self.pieces) or
                    len(set(edge.live)) != len(edge.live) or not names.issuperset(edge.live)):
                raise ValueError("invalid crossing edge")

    @property
    def specs(self):
        return {v.name: v for v in self.values}


def stable_values(program):
    if not program.edges:
        return ()
    common = set(program.edges[0].live)
    for edge in program.edges[1:]:
        common.intersection_update(edge.live)
    return tuple(value.name for value in program.values if value.name in common and value.piece == 0 and value.words)


def layout_fields(program, stable=()):
    specs = program.specs
    placements = {}
    stride = max((1 + sum(specs[name].words for name in edge.live) for edge in program.edges), default=1)
    for edge in program.edges:
        names = (*stable, *(name for name in edge.live if name not in stable))
        word = 1
        offsets = {}
        for name in names:
            width = specs[name].words
            if width:
                offsets[name] = tuple(range(word, word + width))
                word += width
        if word != 1 + sum(specs[name].words for name in edge.live) or word > stride:
            raise ValueError("a placement changed the original edge size")
        placements[edge.tag] = offsets
    return stride, placements


def rebuild_handle(name, lane):
    return (sum(map(ord, name)) << 9) ^ (lane * 23)


def run_unsplit(program, lane):
    full_state = {v.name: rebuild_handle(v.name, lane) for v in program.values if not v.words}
    edges = {edge.tag: edge for edge in program.edges}
    stage = tag = 0
    observed = []
    while True:
        step = program.pieces[stage].run(full_state, lane, tag)
        observed.append((stage, step.observed))
        full_state.update(step.definitions)
        tag = step.next_tag
        if tag == 0:
            return tuple(observed)
        edge = edges[tag]
        if edge.origin != stage:
            raise AssertionError("original step selected a foreign edge")
        stage = edge.target


class AccessWords:
    def __init__(self, size, seed):
        self.words = [((0xC0FFEE00 ^ seed) + i * 109) & DWORD for i in range(size)]
        self.trace = Counter()

    def load(self, stage, name, locations):
        self.trace[stage, "read", name] += len(locations)
        return sum(self.words[location] << (DWORD.bit_length() * word) for word, location in enumerate(locations))

    def store(self, stage, name, locations, value):
        self.trace[stage, "write", name] += len(locations)
        for word, location in enumerate(locations):
            self.words[location] = (value >> (DWORD.bit_length() * word)) & DWORD


def run_split(program, lane, candidate):
    specs = program.specs
    stable = stable_values(program) if candidate else ()
    stride, placements = layout_fields(program, stable)
    crossing = {edge.tag: edge for edge in program.edges}
    scratch = AccessWords(stride, lane)
    observed = []
    for stage, piece in enumerate(program.pieces):
        incoming = scratch.load(stage, "tag", (0,)) if stage else 0
        live = {}
        if stage:
            edge = crossing.get(incoming)
            if edge is None or edge.target != stage:
                continue
            for name in edge.live:
                if not specs[name].words:
                    live[name] = rebuild_handle(name, lane)
                elif name not in stable or name in piece.original_operands:
                    live[name] = scratch.load(stage, name, placements[incoming][name])
        else:
            live.update((v.name, rebuild_handle(v.name, lane)) for v in program.values if not v.words)
        result = piece.run(live, lane, incoming)
        observed.append((stage, result.observed))
        live.update(result.definitions)
        if result.next_tag:
            edge = crossing[result.next_tag]
            if edge.origin != stage:
                raise AssertionError("split step selected a foreign edge")
            for name in edge.live:
                if specs[name].words and (stage == 0 or name not in stable):
                    scratch.store(stage, name, placements[edge.tag][name], live[name])
            scratch.store(stage, "tag", (0,), edge.tag)
        elif stage + 1 < len(program.pieces):
            scratch.store(stage, "tag", (0,), 0)
    return tuple(observed), scratch.trace, stride


def start_values(lane):
    return {"anchor32": (0xFAB0_0001 + lane * 19) & DWORD,
            "anchor64": (0xFFFF_00FD_0102_0304 + lane * 0x10000_0001) & QWORD,
            "seed32": (lane * 83 + 23) & DWORD,
            "seed64": (0x9000_1AB3_AAC2_1234 + lane * 0x20200_0319) & QWORD}


def mixed_program():
    values = (Value("anchor32", 0), Value("anchor64", 0, "i64"), Value("seed32", 0),
              Value("seed64", 0, "i64"), Value("remat", 0, "handle"),
              Value("value1", 1), Value("value2", 2, "i64"), Value("value3", 3))

    def first(_, lane, tag):
        source = start_values(lane)
        if lane % 8 == 0:
            return Result(0, source, (source["seed64"],))
        return Result((1, 2, 3)[lane % 3], source)

    def second(data, lane, tag):
        # No original operation here reads either anchor.
        value = (data["seed32"] ^ (data["seed64"] >> 32) ^ data["remat"]) & DWORD
        return Result(0 if lane % 11 == 1 else (4 if lane % 2 else 5),
                      {"value1": value}, (value & 0xFFFF,))

    def third(data, lane, tag):
        # This phi-like selection deliberately reads anchor32 on just one incoming edge.
        value = data["seed32"] if tag == 2 else data["value1"] ^ data["anchor32"]
        wide = ((value << 32) | ((value ^ 0xABCD_EF01) & DWORD)) & QWORD
        return Result(7 if lane % 5 == 0 else 6, {"value2": wide}, (wide if lane % 7 == 0 else 0,))

    def fourth(data, lane, tag):
        incoming = data["value1"] if tag == 5 else data["value2"]
        value = (incoming ^ data["anchor64"] ^ (data["anchor64"] >> 32)) & DWORD
        return Result(0 if lane % 11 == 4 else 8, {"value3": value}, (value,))

    def last(data, lane, tag):
        variable = data[{3: "seed64", 7: "value2", 8: "value3"}[tag]]
        return Result(0, {}, ((data["anchor64"] ^ variable) & QWORD, data["anchor32"] ^ (variable & DWORD)))

    def piece(operands, logic):
        return Piece(frozenset(operands.split()), logic)

    def edge(tag, source, destination, names):
        return Edge(tag, source, destination, tuple(names.split()))

    pieces = (piece("", first), piece("seed32 seed64 remat", second),
              piece("seed32 value1 anchor32", third), piece("value1 value2 anchor64", fourth),
              piece("seed64 value2 value3 anchor32 anchor64", last))
    edges = (edge(1, 0, 1, "seed64 anchor32 remat seed32 anchor64"),
             edge(2, 0, 2, "anchor64 seed32 anchor32"),
             edge(3, 0, 4, "seed64 anchor64 anchor32"),
             edge(4, 1, 2, "value1 anchor32 anchor64"),
             edge(5, 1, 3, "anchor32 anchor64 value1"),
             edge(6, 2, 3, "value2 anchor64 anchor32"),
             edge(7, 2, 4, "anchor64 value2 anchor32"),
             edge(8, 3, 4, "anchor32 value3 anchor64"))
    return Program(values, edges, pieces)


def linear_program(stages, anchors=True):
    if not 3 <= stages <= 5:
        raise ValueError("three to five pieces expected")
    values = [Value(f"value{i}", i) for i in range(stages - 1)]
    if anchors:
        values += [Value("anchor32", 0), Value("anchor64", 0, "i64")]

    def first(_, lane, tag):
        source = {"value0": lane ^ 0x876546AB}
        if anchors:
            for name in ("anchor32", "anchor64"):
                source[name] = start_values(lane)[name]
        return Result(1, source)

    def middle(index):
        incoming = f"value{index - 1}"
        output = f"value{index}"
        def execute(data, lane, tag):
            return Result(index + 1, {output: (data[incoming] + lane + index * 321) & DWORD})
        return Piece(frozenset((incoming,)), execute)

    def last(data, lane, tag):
        result = data[f"value{stages - 2}"]
        if anchors:
            result ^= data["anchor64"] ^ data["anchor32"]
        return Result(0, {}, (result,))

    original_reads = {f"value{stages - 2}"}
    if anchors:
        original_reads.update(("anchor32", "anchor64"))
    pieces = (Piece(frozenset(), first), *(middle(i) for i in range(1, stages - 1)),
              Piece(frozenset(original_reads), last))
    edges = []
    for i in range(stages - 1):
        live = [f"value{i}"]
        if anchors:
            live.append("anchor64")
            live.insert(i % 2, "anchor32")
        edges.append(Edge(i + 1, i, i + 1, tuple(live)))
    return Program(tuple(values), tuple(edges), pieces)


def incompatible_program():
    """A common rematerialized handle and path-specific scalar definitions."""
    values = (Value("old_bits", 0, "f32"), Value("new_bits", 1, "i64"), Value("remat", 0, "handle"))

    def first(_, lane, tag):
        # Alternate starting quiet-NaN/sign-bit patterns without interpreting them.
        bits = (0x7FC0_0000 if lane % 4 == 0 else 0x8000_0000) | lane
        return Result(1 if lane % 2 == 0 else 2, {"old_bits": bits})

    def second(data, lane, tag):
        bits = (data["old_bits"] << 32) ^ data["remat"]
        return Result(3, {"new_bits": bits})

    def last(data, lane, tag):
        chosen_bits = data["old_bits"] if tag == 2 else data["new_bits"]
        return Result(0, {}, (chosen_bits, data["remat"]))

    pieces = (Piece(frozenset(), first), Piece(frozenset(("old_bits", "remat")), second),
              Piece(frozenset(("old_bits", "new_bits", "remat")), last))
    edges = (Edge(1, 0, 1, ("remat", "old_bits")), Edge(2, 0, 2, ("old_bits", "remat")),
             Edge(3, 1, 2, ("new_bits", "remat")))
    return Program(values, edges, pieces)
