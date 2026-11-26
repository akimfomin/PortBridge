"""Count syntactically unused ballot return values in an existing open DXIL corpus."""
import argparse
from collections import Counter
import csv
from pathlib import Path
import re

VAL = re.compile(r"%[-.A-Za-z_0-9]+")
DEF = re.compile(r"\s*(%[-.A-Za-z_0-9]+)\s*=\s*(.*)")
BALLOT = "call %dx.types.fouri32 @dx.op.waveActiveBallot("

def measure(file):
    uses, ballots = Counter(), {}
    inside = False
    for line in file.read_text(encoding="utf-8").splitlines():
        if line.startswith("define "):
            inside = True
            continue
        if not inside:
            continue
        if line == "}":
            inside = False
            continue
        code=line.split(";",1)[0]
        match=DEF.fullmatch(code)
        if match:
            name,code=match.groups()
            if BALLOT in code:
                ballots[name]="i1 true" not in code and "i1 false" not in code
        uses.update(VAL.findall(code))
    dead=[name for name in ballots if not uses[name]]
    return len(ballots),len(dead),sum(ballots[name] for name in dead)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("root",type=Path);p.add_argument("out",type=Path);p.add_argument("--filename",default="project.ll");a=p.parse_args()
    rows=[]
    for file in sorted(a.root.glob("*/*/"+a.filename)):
        rows.append((file.relative_to(a.root).as_posix(),*measure(file)))
    with a.out.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f);w.writerow(["path","ballots","dead_no_direct_ssa_uses","dead_conditional"]);w.writerows(rows)
    positive=[r for r in rows if r[2]];print("entries",len(rows),"with_unused",len(positive),"counts",sum(r[1] for r in rows),sum(r[2] for r in rows),sum(r[3] for r in rows),"top", sorted(positive,key=lambda r:-r[2])[:4])

