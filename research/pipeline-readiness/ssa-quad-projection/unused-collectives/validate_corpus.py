"""Translate each accepted public pixel shader with all three modes and compare it with itself."""
import argparse
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from prepare_spirv import feature_flags
from check_observables import compare

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("manifest","accepted","compiler","dxc","khronos","raylib","mixed","display","out"):
        p.add_argument("--"+k,type=Path,required=True)
    a=p.parse_args()
    env={k:v for k,v in os.environ.items() if not k.startswith("XCL_")}
    env["XCL_DXC_DIR"]=str(a.dxc.resolve())
    def load(path):
        data=path.read_bytes()
        return json.loads(gzip.decompress(data) if data[:2]==b"\x1f\x8b" else data)
    specs=load(a.manifest)["rows"]
    previous=load(a.accepted)
    previous=previous.get("corpus",previous)
    prior={(v["group"],v["id"]):v for v in previous["rows"]}
    roots={"khronos-vulkan-samples":a.khronos,"raylib-procedural":a.raylib,
            "miniengine-display":a.display,"miniengine":a.mixed,"naga":a.mixed}
    rows=[]
    with tempfile.TemporaryDirectory() as tmp:
        dst=Path(tmp)/"candidate.dxil"
        for spec in specs:
            group,i=spec["group"],spec["id"]
            accepted=prior[group,i]
            if "sha256" not in accepted.get("project",{}):
                continue
            abi=spec["rdna"]
            inp=roots[group]/f"{i:03}"/"shader.rdna2"
            if sha256(inp.read_bytes()).hexdigest()!=abi["sha256"]:
                raise ValueError(f"Input identity mismatch {group}/{i}")
            row=dict(group=group,id=i,source=spec["source"],entry=spec["entry"],input_sha256=abi["sha256"])
            baseline_ir=None
            flags=[str(abi[k]) for k in ("wave","spi_ps_input_ena","interpolants","color_mask","depth_mode")]
            for mode in ("project","project-ballot","project-ballot-quad"):
                proc=subprocess.run([a.compiler,inp,dst,*flags,"root-4","generic",mode],env=env,
                                    capture_output=True,timeout=65)
                if proc.returncode:
                    raise RuntimeError(f"{group}/{i} {mode}: {proc.stderr.decode(errors='replace')}")
                ir=dst.with_suffix(".ll").read_text(encoding="utf8")
                code=dst.read_bytes()
                row[mode]=dict(sha256=sha256(code).hexdigest(),dxil_bytes=len(code),feature_flags=hex(feature_flags(dst)),
                    ballots=ir.count("call %dx.types.fouri32 @dx.op.waveActiveBallot("),
                    quads=len(re.findall(r"call .*? @dx.op.quad",ir)),
                    branches=len(re.findall(r"(?m)^\s*br ",ir)),phis=len(re.findall(r"(?m)^\s*%[-\w.]+ = phi ",ir)))
                if baseline_ir is None:
                    baseline_ir=ir
                else:
                    row[mode]["checked_observable_graph"]=compare(baseline_ir,ir)
            controls=("feature_flags","branches","phis")
            if any(len({row[m][key] for m in ("project","project-ballot","project-ballot-quad")})!=1 for key in controls):
                raise RuntimeError(f"Control mismatch {group}/{i}")
            row["pinned_archive_match"]=row["project"]["sha256"]==accepted["project"]["sha256"]
            rows.append(row)
    a.out.write_text(json.dumps(dict(accepted=len(rows),modes=["project","project-ballot","project-ballot-quad"],
        prior_inputs=len(prior),rows=rows),indent=2)+"\n",encoding="utf8")

if __name__=="__main__":
    main()

