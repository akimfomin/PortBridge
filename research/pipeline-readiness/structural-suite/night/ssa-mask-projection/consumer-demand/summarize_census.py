# SPDX-License-Identifier: MIT
"""Summarize the matched direct compiler census, preserving failures and code-size regressions."""
from collections import Counter
import argparse, gzip, json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("census",type=Path)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    data=json.loads(a.census.read_bytes())
    complete=[r for r in data["rows"] if "changed" in r]
    cohorts=[]
    for group,wave in sorted({(r["group"],r["wave"]) for r in complete}):
        rows=[r for r in complete if r["group"]==group and r["wave"]==wave]
        size=[r["variants"]["consumer"]["dxil_bytes"]-r["variants"]["strict"]["dxil_bytes"] for r in rows]
        cohorts.append(dict(group=group,wave=wave,valid=len(rows),changed=sum(r["changed"] for r in rows),
                            shrank=sum(d<0 for d in size),grew=sum(d>0 for d in size),
                            total_delta_bytes=sum(size),largest_growth=max(0,max(size)),
                            maximum_reduction=max(0,-min(size))))
    shifts={k:sum(r["variants"]["strict"][k]!=r["variants"]["consumer"][k] for r in complete)
            for k in ("ballots","quad_ops","branches","phis")}
    worst=sorted(complete,key=lambda r:r["variants"]["consumer"]["dxil_bytes"]-r["variants"]["strict"]["dxil_bytes"],reverse=True)[:10]
    first=[dict(source=r["source"],group=r["group"],guest_wave=r["wave"],baseline_bytes=r["variants"]["strict"]["dxil_bytes"],
                candidate_bytes=r["variants"]["consumer"]["dxil_bytes"],guest_sha256=r["guest_sha256"]) for r in worst]
    result=dict(rows=len(data["rows"]),matched=len(complete),changed=sum(r["changed"] for r in complete),changed_counts=shifts,
                cohorts=cohorts,worst_size_changes=first,
                unmatched=[dict(group=r["group"],id=r["id"],source=r["source"],errors=r.get("variants",r.get("excluded"))) for r in data["rows"] if "changed" not in r])
    a.out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(result["rows"],result["matched"],result["changed"],result["changed_counts"])
    for r in cohorts:print(r)
if __name__=="__main__":
    main()
