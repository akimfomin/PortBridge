"""Run the upstream SPIRV-Tools optimizer on the same XCL SPIR-V modules."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ("inputs","optimizer","tools","out"):
        ap.add_argument("--"+k,required=True,type=Path)
    a=ap.parse_args()
    version=subprocess.check_output([a.optimizer,"--version"],stderr=subprocess.STDOUT,text=True).strip()
    with tempfile.TemporaryDirectory() as tmp:
        results=[]
        for shader in ("nerf71","nerf73","raylib"):
            for mode in ("project","project-ballot-quad"):
                src=a.inputs/f"{shader}-{mode}.spv"
                for passes in (["--eliminate-dead-code-aggressive"],["-O"]):
                    dst=Path(tmp)/"candidate.spv"
                    opts=[*passes,"--strip-debug","--compact-ids"]
                    subprocess.run([a.optimizer,"--target-env=vulkan1.3",*opts,src,"-o",dst],timeout=35,check=True)
                    subprocess.run([a.tools/"spirv-val.exe","--target-env","vulkan1.3",dst],timeout=20,check=True)
                    dis=subprocess.check_output([a.tools/"spirv-dis.exe","--raw-id",dst],timeout=20).decode()
                    results.append(dict(shader=shader,mode=mode,passes=opts,input_sha256=digest(src),
                        bytes=dst.stat().st_size,sha256=digest(dst),ballots=dis.count("OpGroupNonUniformBallot "),
                        quads=dis.count("OpGroupNonUniformQuadBroadcast ")+dis.count("OpGroupNonUniformQuadSwap ")))
    libraries={f.name:digest(f) for f in sorted(a.optimizer.parent.glob("libSPIRV-Tools*.dll"))}
    a.out.write_text(json.dumps(dict(optimizer=version,optimizer_sha256=digest(a.optimizer),libraries=libraries,runs=results),
        indent=2)+"\n",encoding="utf8")

if __name__=="__main__":
    main()
