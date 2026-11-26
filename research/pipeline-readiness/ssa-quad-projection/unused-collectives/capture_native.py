"""Validate one input and sample the driver's fragment executable under memory bounds."""
import argparse
import ctypes
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

class Performance(ctypes.Structure):
    _fields_ = [("cb",ctypes.c_uint32)] + [(k,ctypes.c_size_t) for k in
        ("total", "limit", "peak","physical","available","cache","kernel","paged","nonpaged","page")] + [
        (k,ctypes.c_uint32) for k in ("handles","processes","threads")]

def headroom():
    p = Performance()
    p.cb = ctypes.sizeof(p)
    if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(p),p.cb):
        raise OSError("Could not query system memory")
    return (p.limit-p.total)*p.page, p.available*p.page

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ("fragment","harness","tools","out"):
        ap.add_argument("--"+k,type=Path,required=True)
    ap.add_argument("--profile",choices=("xcl-ray-roots","xcl-nerf-roots"),required=True)
    ap.add_argument("--device",default="NVIDIA GeForce RTX 4070 Ti SUPER")
    ap.add_argument("--wait-for-reserve",type=int,default=0,choices=range(11),metavar="SECONDS")
    a=ap.parse_args()
    a.out.parent.mkdir(exist_ok=True,parents=True)
    if a.out.exists():
        raise FileExistsError(a.out)
    probe=a.harness/"pipeline_stats.exe"
    vertex=a.harness/"fullscreen.vert.spv"
    with tempfile.TemporaryDirectory() as tmp:
        preflight=Path(tmp)/"preflight.json"
        subprocess.run([sys.executable,a.harness/"run_probe.py","--validate-only","--probe",probe,
            "--vertex",vertex,"--fragment",a.fragment,"--dis",a.tools/"spirv-dis.exe","--val",a.tools/"spirv-val.exe",
            "--device",a.device,"--profile",a.profile,"--out",preflight],check=True,timeout=30)
        receipt=json.loads(preflight.read_bytes())
    gib=1<<30
    commit,ram=headroom()
    deadline=time.monotonic()+a.wait_for_reserve
    while (commit<6*gib+gib//2 or ram<4*gib+gib//2) and time.monotonic()<deadline:
        time.sleep(.1)
        commit,ram=headroom()
    if commit<6*gib+gib//2 or ram<4*gib+gib//2:
        raise SystemExit(f"Prelaunch headroom insufficient: available commit={commit}, RAM={ram}")
    # The native executable creates its own bounded process-memory Job object.
    # Read the direct child only after it exits; its JSON is written to a file.
    with tempfile.TemporaryFile() as capture:
        with subprocess.Popen([probe,vertex,a.fragment,a.device,a.profile],stdout=capture,stderr=subprocess.STDOUT) as proc:
            end=time.monotonic()+35
            minimum=[commit,ram]
            while proc.poll() is None:
                c,r=headroom()
                minimum=[min(minimum[0],c),min(minimum[1],r)]
                if c<6*gib or r<4*gib or time.monotonic()>end:
                    proc.kill()
                    proc.wait(timeout=4)
                    raise SystemExit("Stopped by system reserve or time")
                time.sleep(.025)
            capture.seek(0)
            raw=capture.read()
        if proc.returncode:
            raise RuntimeError(raw.decode(errors="replace"))
    receipt["physical_pipeline"]=json.loads(raw)
    receipt["memory_guard"]={"system_commit_reserve":6*gib,"physical_reserve":4*gib,
                              "lowest_system_commit_available":minimum[0],"lowest_system_physical_available":minimum[1]}
    with a.out.open("x",encoding="utf-8") as out:
        json.dump(receipt,out,indent=2)
        out.write("\n")

if __name__=="__main__":
    main()

