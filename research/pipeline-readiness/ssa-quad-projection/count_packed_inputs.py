"""Count complete pack/unpack cycles on inputs to actual emitted pixel wave ballots."""
import argparse
import collections
import json
import re
from pathlib import Path

VALUE = r"(%[-.a-zA-Z0-9_]+)"
ASSIGN = re.compile(r"^\s*"+VALUE+r" = (.*?)(?:\s+;.*)?$")
BALLOT = re.compile(r"call %dx.types.fouri32 @dx.op.waveActiveBallot\(i32 116, i1 "+VALUE+r"\)")

def inspect(path):
    defs = {}
    groups = collections.defaultdict(set)
    ballots = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ASSIGN.match(line)
        if not match:
            continue
        result, op = match.groups()
        defs[result] = op.strip()
        if "@dx.op.waveActiveBallot(" not in op:
            continue
        ballots += 1
        call = BALLOT.fullmatch(op)
        if not call:
            continue
        pred = defs.get(call[1], "")
        cmp = re.fullmatch(r"icmp ne i32 "+VALUE+r", 0", pred)
        if not cmp:
            continue
        mask = re.fullmatch(r"and i32 "+VALUE+r", 1", defs.get(cmp[1], ""))
        if not mask:
            continue
        root, bit = mask[1], 0
        shift = re.fullmatch(r"lshr i32 "+VALUE+r", ([123])", defs.get(root, ""))
        if shift:
            root, bit = shift[1], int(shift[2])
        def fields(value, depth=0):
            if depth > 4:
                return None
            op = defs.get(value, "")
            join = re.fullmatch(r"or i32 "+VALUE+r", "+VALUE, op)
            if join:
                left, right = fields(join[1], depth+1), fields(join[2], depth+1)
                return None if left is None or right is None else left + right
            move = re.fullmatch(r"shl i32 "+VALUE+r", ([123])", op)
            position = int(move[2]) if move else 0
            leaf = defs.get(move[1], "") if move else op
            return [position] if re.fullmatch(r"zext i1 "+VALUE+r" to i32", leaf) else None
        known = fields(root)
        if known is not None and sorted(known) == [0, 1, 2, 3]:
            groups[root].add(bit)
    return {"input":path.name,"wave_ballots":ballots,
            "complete_quads":sum(bits == {0,1,2,3} for bits in groups.values()),
            "provable_predicate_operands":sum(len(bits) for bits in groups.values())}

if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("ir",type=Path,nargs="+")
    args=cli.parse_args()
    print(json.dumps([inspect(f) for f in args.ir], indent=2))
