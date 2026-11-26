# SPDX-License-Identifier: MIT
"""Run bounded XCL draws and compare every color and discard decision with the MLP oracle."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np


def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def compare(a, b):
    left=a.reshape(-1,4)
    right=b.reshape(-1,4)
    killed_a=(left == -3).all(axis=1)
    killed_b=(right == -3).all(axis=1)
    live=~(killed_a | killed_b)
    d=np.abs(left[live,:3].astype("f8")-right[live,:3].astype("f8"))
    finite=np.isfinite(d).all(axis=1)
    adj=d[finite]
    finite_max=adj.max(axis=1) if adj.size else np.array([])
    return {
        "pixels": len(left), "bit_equal_pixels": int(np.all(left.view("u4")==right.view("u4"),axis=1).sum()),
        "discarded_left":int(killed_a.sum()),"discarded_right":int(killed_b.sum()),
        "discard_mismatches":int((killed_a!=killed_b).sum()),"shared_live_pixels":int(live.sum()),
        "alpha_mismatches":int(np.sum(left[:,3]!=right[:,3])),
        "nonfinite_pixels":int((~np.isfinite(left).all(axis=1) | ~np.isfinite(right).all(axis=1)).sum()),
        "live_rgb_max_abs":float(adj.max()) if adj.size else None,
        "live_rgb_mean_abs":float(adj.mean()) if adj.size else None,
        "live_rgb_p99_max_abs":float(np.quantile(finite_max,.99)) if finite_max.size else None,
        "distinct_live_rgb8_left":int(len(np.unique(np.rint(left[~killed_a,:3]*255),axis=0))),
        "shared_live_rgb_over_1e-4":int((finite_max>1e-4).sum()),
    }


def agrees(stats):
    return (stats["discard_mismatches"] == 0 and stats["alpha_mismatches"] == 0
            and stats["nonfinite_pixels"] == 0 and stats["shared_live_rgb_over_1e-4"] == 0
            and stats["shared_live_pixels"] > 0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("inputs","strict","consumer","dxc","dxv","vertex","guard","tests","out"):
        p.add_argument("--"+arg,type=Path,required=True)
    p.add_argument("--shader",choices=("mlp_combo","mlp_morpheus_combo"),required=True)
    p.add_argument("--draws",type=int,choices=range(0,17),default=0)
    p.add_argument("--rounds",type=int,choices=range(1,7),default=1)
    p.add_argument("--native",type=Path,help="raw output of the unmodified upstream Vulkan fragment")
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    info=json.loads((a.inputs/"manifest.json").read_bytes())
    for name, sha in info["sha256"].items():
        if digest(a.inputs/name)!=sha: raise ValueError("Changed fixture: "+name)
    gold=np.fromfile(a.inputs/(a.shader+".cpu.rgba32f"),dtype="<f4")
    native=np.fromfile(a.native,dtype="<f4") if a.native else None
    shaders={"strict":a.strict,"consumer":a.consumer}
    for module in (a.vertex, a.strict, a.consumer):
        subprocess.run([a.dxv.resolve(), module.resolve()], check=True, capture_output=True, timeout=20)
    r={"shader":a.shader,"width":info["width"],"height":info["height"],"inputs_manifest_sha256":digest(a.inputs/"manifest.json"),
       "dxil_sha256":{s:digest(f) for s,f in shaders.items()},"tests_sha256":digest(a.tests),"guard_sha256":digest(a.guard),
       "vertex_sha256":digest(a.vertex),"validator_sha256":digest(a.dxv),
       "warmup":1,"timed_draws":a.draws,"rounds":[]}
    if native is not None:
        if native.size!=gold.size:raise ValueError("Vulkan result extent differs")
        r["source_vulkan_sha256"]=digest(a.native)
        r["source_vulkan_vs_cpu"]=compare(native,gold)
    out=a.out/"results.json"
    def save():
        out.write_text(json.dumps(r,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    if native is not None and not agrees(r["source_vulkan_vs_cpu"]):
        save()
        raise SystemExit("Vulkan reference differs from the CPU oracle")
    for i in range(a.rounds):
        order=list(shaders) if i%2==0 else list(reversed(shaders))
        trial={"order":order,"arms":{}}
        r["rounds"].append(trial)
        rendered={}
        for arm in order:
            work=a.out/f"{i:02d}-{arm}"
            work.mkdir()
            raw=work/"image.rgba32f"
            log=work/"draw.log"
            env={k:v for k,v in os.environ.items() if not k.startswith(("PB_","XCL_"))}
            env.update(XCL_DXC_DIR=str(a.dxc.resolve()),XCL_READ_GUARD_TEST_ROOT_WINDOWS="1",
                       XCL_READ_GUARD_TEST_PSO_BLOB="1", PB_SCENE_PS=str(shaders[arm].resolve()),
                       PB_NERF_VS=str(a.vertex.resolve()),
                       PB_NERF_INPUT=str(a.inputs.resolve()),PB_SCENE_IMAGE=str(raw.resolve()),
                       PB_SCENE_SIZE=str(info["width"]),PB_SCENE_HEIGHT=str(info["height"]))
            if a.draws: env["XCL_READ_GUARD_TEST_GPU_DRAWS"]=str(a.draws)
            cmd=[a.guard.resolve(),a.tests.resolve(),log.resolve(),"gpu::dxil::aperture_tests::open_mobilenerf_mlp_draw","--512-mib"]
            run=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=45)
            guard=run.stdout+run.stderr
            (work/"guard.txt").write_text(guard,encoding="utf-8")
            stdout=log.read_text(encoding="utf-8") if log.exists() else ""
            if run.returncode or not raw.exists() or "1 passed; 0 failed" not in stdout or "SKIPPED" in stdout:
                trial["stopped"]={"arm":arm,"guard_exit":run.returncode,"error":guard.strip()};save()
                raise SystemExit(f"Stopped at {arm}, see {work}")
            arr=np.fromfile(raw,dtype="<f4")
            if arr.size!=gold.size:raise ValueError("Truncated XCL frame")
            rendered[arm]=arr
            stats={"output_sha256":digest(raw),"vs_cpu":compare(arr,gold)}
            if native is not None:stats["vs_source_vulkan"]=compare(arr,native)
            for fld in ("native_create_ms","pso_cache_blob_bytes","scene_native_setup_submit_readback_ms","gpu_ms_per_draw","ticks","frequency_hz","peak_process_bytes"):
                value=re.search(rf"\b{fld}=([\d.]+)",stdout+" "+guard)
                if value: stats[fld]=float(value[1]) if "." in value[1] else int(value[1])
            trial["arms"][arm]=stats;save()
        trial["paired"]=compare(rendered["strict"],rendered["consumer"]);save()
        print(i,trial["arms"]["strict"]["vs_cpu"],trial["paired"]["bit_equal_pixels"],flush=True)
        if trial["paired"]["bit_equal_pixels"]!=info["width"]*info["height"]:
            raise SystemExit("Mask projection changed the frame")
        for arm, stats in trial["arms"].items():
            if not agrees(stats["vs_cpu"]) or native is not None and not agrees(stats["vs_source_vulkan"]):
                raise SystemExit(f"{arm} differs from a source oracle; exclude from speed claims")


if __name__=="__main__":
    main()
