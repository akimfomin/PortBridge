import os, subprocess
from pathlib import Path
import json

def git(*args):
    return subprocess.check_output(["git",*args],text=True).strip()

if git("write-tree")!="74a66f97afcff228896e18a8d1511edeb71d484f":
    raise SystemExit("Unexpected staged control tree")
subprocess.run(["git","diff","--quiet"],check=True)
changes={
 Path("crates/victory-gpu/src/replay/play/pixel.rs"): (
    b"    u64::from(f.RowPitch) * u64::from(y) + x as u64 * texel_bytes(f.Format.0) as u64",
    b"    u64::from(f.RowPitch) * u64::from(y) + x as u64 * 8",
 ),
 Path("crates/victory-gpu/src/host.rs"): (
    b"            self.twins_to_depth(true);",
    b"            // Negative control: postpone depth-plane publication until close.",
 ),
}
originals={path:path.read_bytes() for path in changes}
for path,(before,after) in changes.items():
    assert originals[path].count(before)==1, path
tests=[
 ("depth_probe_reads_the_copied_plane_layout","packed width"),
 ("a_depth_planes_twin_is_drawn_into_the_plane","deferred publication"),
]
invocation=[os.environ["PB_CARGO_PATH"],"test","--offline","--locked","-j","2","-p","victory-gpu","--lib","--features","diagnostics"]
reports=[]
try:
    for path,(before,after) in changes.items():
        path.write_bytes(originals[path].replace(before,after))
    for name,mode in tests:
        result=subprocess.run([*invocation,name,"--","--nocapture"],capture_output=True,text=True,errors="replace",timeout=250)
        combined=result.stdout+"\n"+result.stderr
        selected=[line.strip() for line in combined.splitlines() if any(item in line for item in (
            "running 1 test","test result:","FAILED","assertion","left:","right:","error:","NVIDIA required","depth-plane twins"
        ))]
        row={"mode":mode,"test":name,"exit":result.returncode,"result":selected}
        reports.append(row)
        print(json.dumps(row),flush=True)
finally:
    for path, data in originals.items():
        path.write_bytes(data)
subprocess.run(["git","diff","--quiet"],check=True)
Path(os.environ["PB_CONTROL_RECEIPT"]).write_text(json.dumps(reports,indent=2)+"\n",encoding="utf-8")
if any(row["exit"]==0 or not any("test result: FAILED. 0 passed; 1 failed" in line for line in row["result"]) for row in reports):
    raise SystemExit("Negative controls did not both fail inside their selected tests")

