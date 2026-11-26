
"""Measure exact aperture-proof A/B coverage through XCL and standalone DXV."""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from subprocess import SubprocessError
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "xcl-readguard-corpus-artifacts"))
from open_pixel_census import command, error_text, hash_file
from fixture_census import dxil_shape

def replay(index_record):
    index, record=index_record
    row={"id":index,"group":record["group"],"source":record["source"],"entry":record["entry"],
         "source_sha256":record["source_sha256"]}
    meta=record.get("rdna")
    if record.get("error") or not meta:
        return {**row,"input_excluded":record.get("error",{})}
    code=args.input.parent/f"{index:03d}"/"shader.rdna2"
    if hash_file(code)!=meta["sha256"]:
        raise ValueError(f"Input digest mismatch for {code}")
    row["rdna"]=meta
    config=[meta[key] for key in ("wave","spi_ps_input_ena","interpolants","color_mask","depth_mode")]
    case=args.out/f"{index:03d}"
    case.mkdir()
    results={}
    for rule,value in (("off","generic"),("on",str(args.base_hi))):
        dest=case/(rule+".dxil")
        try:
            command([args.xcl,code,dest,*map(str,config),args.layout,value],env=env)
            command([args.dxv,dest])
            asm=dest.with_suffix(".ll").read_text(encoding="utf-8")
            shape=dxil_shape(asm)
            entry=asm.split("define void @main() {",1)[1].split("\n}",1)[0]
            shape["switch_cases"]=len(re.findall(r"^\s+i\d+ (-?\d+), label %\d+",entry,re.M))
            shape["phi_incomings"]=sum(line.count("[") for line in entry.splitlines() if " = phi " in line)
            results[rule]={"bytes":dest.stat().st_size,"sha256":hash_file(dest),**shape}
        except (OSError,SubprocessError,ValueError) as error:
            results[rule]={"error":re.sub(r"(?i) from [a-z]:\\[^\r\n]*", " from <tool>", error_text(error,args.out.parent))}
    row["pair"]=results
    return row

parser=argparse.ArgumentParser(description=__doc__)
for name in ("input","xcl","dxc","dxv","out"):
    parser.add_argument("--"+name,type=lambda v:Path(v).resolve(),required=True)
parser.add_argument("--layout",default="root-4")
parser.add_argument("--base-hi",type=int,default=4)
parser.add_argument("--revision",required=True)
parser.add_argument("--jobs",type=int,choices=(1,2),default=1)
args=parser.parse_args()
args.out.mkdir()
env={k:v for k,v in os.environ.items() if not k.startswith("XCL_")}
env["XCL_DXC_DIR"]=str(args.dxc.parent)
source=json.loads(args.input.read_text())
with ThreadPoolExecutor(max_workers=args.jobs) as jobs:
    rows=list(jobs.map(replay,enumerate(source["observations"])))
counts=Counter()
totals=defaultdict(lambda:Counter())
baselines=defaultdict(lambda:Counter())
for row in rows:
    group=row["group"]
    if not row.get("pair"):
        counts[(group,"input_exclusion")]+=1
        continue
    arm=row["pair"]
    if any("error" in a for a in arm.values()):
        counts[(group,"xcl_or_dxv_reject")]+=1
        continue
    counts[(group,"accepted")]+=1
    if arm["on"]["sha256"]!=arm["off"]["sha256"]:
        counts[(group,"changed")]+=1
    for name,value in arm["off"].items():
        if isinstance(value,int):
            totals[group][name]+=arm["on"][name]-value
            baselines[group][name]+=value
summary={"xcl_revision":args.revision,"layout":args.layout,"proved_uma_base_hi":args.base_hi,
         "scope":"Raw AMD PAL pixel instruction replay through XCL with a synthetic PS signature. Standalone DXV-validated DXIL; Vulkan descriptors, rendering equivalence and D3D12 timings are outside this structural corpus.",
         "source":source.get("source",source.get("sources")),"tools_sha256":{name:hash_file(getattr(args,name)) for name in ("xcl","dxc","dxv")},
         "counts":{group:{k:n for (g,k),n in counts.items() if g==group} for group in {g for g,_ in counts}},
         "deltas":{k:dict(v) for k,v in totals.items()},"baseline_totals":{k:dict(v) for k,v in baselines.items()},"observations":rows}
(args.out/"aperture-results.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
print(json.dumps({k:summary[k] for k in ("counts","deltas")},indent=2,sort_keys=True))
