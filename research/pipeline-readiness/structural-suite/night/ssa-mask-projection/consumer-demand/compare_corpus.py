# SPDX-License-Identifier: MIT
"""Replay two XCL strict mask observers on identical licensed AMD shader streams."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("baseline","candidate","dxc-dir","dxv","out"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("manifests", nargs="+",type=Path)
    args=parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    env={k:v for k,v in os.environ.items() if not k.startswith("XCL_")}
    env["XCL_DXC_DIR"]=str(args.dxc_dir.resolve())
    rows=[]
    tools={"baseline":digest(args.baseline),"candidate":digest(args.candidate),"dxv":digest(args.dxv)}
    result={"tools":tools, "manifests":[], "rows":rows}
    for manifest in args.manifests:
        document=json.loads(manifest.read_bytes())
        observations=document.get("observations")
        if observations is None:
            # The published Wave32 PAL recompile receipt retains the same source
            # row index and spelling, plus the ABI read from its own Wave32 ELF.
            observations=[]
            for item in document["rows"]:
                case=dict(item)
                if "abi" in case and "guest_sha256" in case:
                    case["rdna"]={**case["abi"],"sha256":case["guest_sha256"]}
                else:
                    case["error"]=case.get("exclusion","missing Wave32 extraction")
                observations.append(case)
        result["manifests"].append({"name":manifest.name,"sha256":digest(manifest),
                                   "sources":document.get("sources",document.get("source"))})
        for position,case in enumerate(observations):
            index=case.get("index",position)
            row={"group":case["group"],"id":index,"source":case["source"],"source_sha256":case["source_sha256"]}
            rows.append(row)
            meta=case.get("rdna")
            if not meta or case.get("error"):
                row["excluded"]=case.get("error",{"stage":"missing RDNA extraction"})
                continue
            assert re.fullmatch(r"[\w.-]+",row["group"])
            rdna=manifest.parent/f"{index:03}"/"shader.rdna2"
            if digest(rdna)!=meta["sha256"]:raise ValueError("Guest digest differs")
            row["guest_sha256"]=meta["sha256"]
            row["wave"]=meta["wave"]
            variants=row["variants"]={}
            entry=args.out/f"wave{meta['wave']}"/row["group"]/f"{index:03}"
            entry.mkdir(parents=True)
            for mode,observer in (("strict",args.baseline),("consumer",args.candidate)):
                dxil=entry/(mode+".dxil")
                command=[observer.resolve(),rdna.resolve(),dxil.resolve(),*[str(meta[k]) for k in ("wave","spi_ps_input_ena","interpolants","color_mask","depth_mode")],"root-4","generic","project"]
                try:
                    subprocess.run(command,env=env,capture_output=True,check=True,timeout=45)
                    subprocess.run([args.dxv.resolve(),dxil.resolve()],env=env,capture_output=True,check=True,timeout=20)
                    text=dxil.with_suffix(".ll").read_text(encoding="utf-8")
                    body=re.search(r"^define [^\n]+@main\(\)[^\n]*\{\n(.*?)^\}",text,re.M|re.S)
                    if not body:raise ValueError("Missing shader entry")
                    definitions=re.findall(r"^  %\d+ = (\w+)",body[1],re.M)
                    variants[mode]={"sha256":digest(dxil),"dxil_bytes":dxil.stat().st_size,"ssa_definitions":len(definitions),
                                    "ballots":body[1].count("call %dx.types.fouri32 @dx.op.waveActiveBallot("),
                                    "quad_ops":len(re.findall(r"call [^\n]*? @dx\.op\.quad",body[1])),
                                    "branches":len(re.findall(r"^  br ",body[1],re.M)), "phis":definitions.count("phi")}
                except subprocess.CalledProcessError as e:
                    msg=(e.stderr or e.stdout).decode(errors="replace").splitlines()
                    variants[mode]={"exit":e.returncode, "reason":next((x for x in reversed(msg) if x.strip()),"")[:240]}
            if len(variants)==2 and "sha256" in variants["strict"] and "sha256" in variants["consumer"]:
                row["changed"]=variants["strict"]["sha256"]!=variants["consumer"]["sha256"]
        (args.out/"census.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    completed=[r for r in rows if "changed" in r]
    print(f"{len(completed)}/{len(rows)} valid, {sum(r['changed'] for r in completed)} changed")


if __name__=="__main__":
    main()
