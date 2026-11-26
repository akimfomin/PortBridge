# SPDX-License-Identifier: MIT
"""Identify residual full pixel-ballot reconstruction in validated XCL LLVM disassembly."""

import argparse
import collections
import json
import re
from pathlib import Path

LOCAL = r"%\d+"
ARG = rf"(?:{LOCAL}|-?\d+|true|false)"


def parse(path):
    definitions = {}
    users = collections.defaultdict(list)
    function = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if line.startswith("define ") and "@main(" in line:
            function = True
            continue
        if line.strip() == "}" and function:
            break
        if not function or not line.startswith("  "):
            continue
        body = line.strip().split(";", 1)[0].rstrip()
        if not body:
            continue
        match = re.match(r"^(%\d+) = (.*)$", body)
        if match:
            dest, body = match.groups()
        else:
            dest = f"!statement-{number}"
        definitions[dest] = body
        for v in set(re.findall(LOCAL, body)):
            users[v].append(dest)
    return definitions, users


def binop(defs, val, op):
    match = re.fullmatch(rf"{op} i32 ({ARG}), ({ARG})", defs.get(val, ""))
    return match.groups() if match else None


def member(defs, value, offset):
    if offset:
        shift = binop(defs, value, "shl")
        if not shift or shift[1] != str(offset):
            return None
        value = shift[0]
    mask = binop(defs, value, "and")
    if not mask or mask[1] != "286331153":
        return None
    comb2 = binop(defs, mask[0], "or")
    if not comb2 or binop(defs, comb2[1], "lshr") != (comb2[0], "2"):
        return None
    comb1 = binop(defs, comb2[0], "or")
    if not comb1 or binop(defs, comb1[1], "lshr") != (comb1[0], "1"):
        return None
    extr = re.fullmatch(
        r"extractvalue %dx.types.fouri32 (%\d+), ([01])", defs.get(comb1[0], "")
    )
    if not extr or "@dx.op.waveActiveBallot(" not in defs.get(extr[1], ""):
        return None
    return extr.groups()


def inspect(path):
    defs, users = parse(path)
    words = {}
    for val in defs:
        tree = val
        members = []
        for index in (3, 2, 1):
            item = binop(defs, tree, "or")
            if not item:
                break
            reg = member(defs, item[1], index)
            if not reg:
                break
            tree = item[0]
            members.append(reg)
        if len(members) == 3 and (first := member(defs, tree, 0)):
            members.append(first)
            if len({x[1] for x in members}) == 1:
                words[val] = (tuple(x[0] for x in reversed(members)), first[1])
    positions = {v: i for i, v in enumerate(defs)}
    groups = {g for g, _ in words.values()}
    ordered_groups = sorted(groups, key=lambda g: positions[g[0]])
    direct = collections.Counter()
    lane_conditions = collections.Counter()
    examples = []
    observed = collections.Counter()
    select_ids = set()
    all_direct_reads = collections.Counter()
    terminal_selections = set()
    for val, expr in defs.items():
        select = re.fullmatch(r"select i1 (%\d+), i32 (%\d+), i32 (%\d+)", expr)
        if not select:
            continue
        _, hi, lo = select.groups()
        pair = words.get(lo)
        if pair is None or words.get(hi) != (pair[0], "1") or pair[1] != "0":
            continue
        known = True
        for con in users[val]:
            if not re.fullmatch(r"lshr i32 %\d+, %\d+", defs[con]):
                known = False
                continue
            bit_only = bool(users[con]) and all(
                defs[u] == f"and i32 {con}, 1" or defs[u] == f"trunc i32 {con} to i1"
                for u in users[con]
            )
            if not bit_only:
                known = False
                continue
            terminal_selections.add(con)
            all_direct_reads[pair[0]] += 1
            condition = defs.get(select[1], "")
            index = defs[con].rsplit(" ", 1)[1]
            lane_conditions[
                (condition.split(" ")[0], defs.get(index, "").split(" ")[0])
            ] += 1
            source = binop(defs, index, "and")
            if source:
                source_op = defs.get(source[0], "")
                observed[
                    "own hardware lane"
                    if "waveGetLaneIndex" in source_op
                    else source_op.split(" ")[0]
                ] += 1
            if len(examples) < 8:
                examples.append([expr, condition, defs[con], defs.get(index, "")])
            last = next(
                (
                    g
                    for g in reversed(ordered_groups)
                    if positions[g[-1]] < positions[con]
                ),
                None,
            )
            direct["any exact pair"] += 1
            direct[
                "latest remaining reconstructed group"
                if last == pair[0]
                else "earlier reconstructed group"
            ] += 1
        if users[val] and known:
            select_ids.add(val)
    purely_extractable = {g for g, _ in words.values()}
    for v, (g, pos) in words.items():
        if any(x not in select_ids for x in users[v]):
            purely_extractable.discard(g)
    pure_histogram = collections.Counter(
        all_direct_reads[g] for g in purely_extractable
    )
    immediate = collections.Counter()
    terminals = collections.Counter()
    for root in words:
        immediate.update(defs[x].split()[0] for x in users[root])
        visited = set()
        pending = [(root, 0)]
        while pending:
            value, depth = pending.pop()
            if value in visited:
                continue
            visited.add(value)
            for v in users[value]:
                text = defs[v]
                op = text.split()[0]
                if op in ("and", "or", "xor", "select", "phi") and depth < 6:
                    pending.append((v, depth + 1))
                elif op == "lshr" and re.fullmatch(r"lshr i32 %\d+, %\d+", text):
                    terminals["variable bit extraction"] += 1
                elif op == "icmp" and re.search(r", 0$", text):
                    terminals["zero test"] += 1
                else:
                    terminals[op] += 1
    return {
        "program": str(path),
        "instructions": len(defs),
        "ballots": sum("@dx.op.waveActiveBallot(" in t for t in defs.values()),
        "full_reconstructed_words": len(words),
        "ballot_groups": len({pair for pair, _ in words.values()}),
        "direct_selected_pair_reads": dict(direct),
        "index_examples": examples,
        "index_source": dict(observed),
        "all_observed_uses_are_indexed": dict(pure_histogram),
        "index_operators": {str(k): v for k, v in lane_conditions.items()},
        "immediate": dict(immediate),
        "terminal_paths_through_bitwise": dict(terminals),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    a = parser.parse_args()
    results = [inspect(p) for p in a.files]
    a.out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    for x in results:
        print(
            x["program"],
            x["full_reconstructed_words"],
            x["direct_selected_pair_reads"],
            x["immediate"],
        )
