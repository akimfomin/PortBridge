"""Check corpus coverage. Only licensed inputs accepted by the pinned front end are compared."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(a):
    src=json.loads(a.census.read_bytes())
    rows=[]
    env={k:v for k,v in os.environ.items() if not k.startswith("XCL_")}
    env["XCL_DXC_DIR"]=str(a.dxc.resolve())
    roots={"raylib-procedural":a.raylib, "miniengine-display":a.display,
           "khronos-vulkan-samples":a.khronos, "naga":a.mixed, "miniengine":a.mixed}
    with tempfile.TemporaryDirectory() as tmp:
        dst=Path(tmp)/"sample.dxil"
        for spec in src["rows"]:
            r={key:spec[key] for key in ("group","id","source","entry")}
            rows.append(r)
            if "rdna" not in spec:
                r["unavailable"]=spec["excluded_before_xcl"]
                continue
            group,idx,abi=spec["group"],spec["id"],spec["rdna"]
            guest=roots[group]/f"{idx:03}"/"shader.rdna2"
            if sha(guest)!=abi["sha256"]: raise ValueError(f"Guest source mismatch at {group}/{idx}")
            r["guest_sha256"]=abi["sha256"]
            flags=[str(abi[k]) for k in ("wave","spi_ps_input_ena","interpolants","color_mask","depth_mode")]
            for mode in ("project","inputs","window"):
                proc=subprocess.run([a.compiler,guest,dst,*flags,"root-4","generic",mode],env=env,
                                    capture_output=True,text=True,timeout=65)
                if proc.returncode:
                    if not proc.stderr.strip(): raise ValueError("unexpected compiler failure")
                    r[mode]={"error":proc.stderr.strip().splitlines()[-1]}
                else:
                    r[mode]={"dxil_bytes":dst.stat().st_size,"sha256":sha(dst)}
            ok=[("error" not in r[m]) for m in ("project","inputs","window")]
            if len(set(ok))>1: raise ValueError(f"Different supported scope at {group}/{idx}")
    a.output.write_text(json.dumps({"sources":src["input_manifests"],"rows":rows},indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("census","compiler","dxc","raylib","display","khronos","mixed","output"):
        p.add_argument("--"+k,type=Path,required=True)
    run(p.parse_args())
