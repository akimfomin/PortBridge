"""Reproduce checked Vulkan graphics pipelines and verify complete raylib readbacks."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("arms","tools","converter","harness","primary","secondary","native","out"):
        p.add_argument("--"+key,type=Path,required=True)
    p.add_argument("--device", default="NVIDIA GeForce RTX 4070 Ti SUPER")
    p.add_argument("--prepare-only", action="store_true")
    a = p.parse_args()
    for k in ("arms","tools","converter","harness","primary","secondary","native","out"):
        setattr(a,k,getattr(a,k).resolve())
    a.out.mkdir(exist_ok=True,parents=True)
    common=["--vertex",a.harness/"fullscreen.vert.spv","--dis",a.tools/"spirv-dis.exe",
            "--val",a.tools/"spirv-val.exe","--device",a.device]
    def run(command):
        subprocess.run(command,check=True,timeout=100)
    def convert(shader):
        spv=a.out/(shader.stem+".spv")
        cmd=[a.converter,shader]
        for slot in [0,2,3,4,5]:
            cmd+=["--root-descriptor","uav","0",str(slot)]
        run(cmd+["--output",spv])
        run([a.tools/"spirv-val.exe","--target-env","vulkan1.3",spv])
        return spv
    samples=("nerf71","nerf73","raylib")
    modes=("project","inputs","window")
    programs={(name,mode):convert(a.arms/f"{name}-{mode}.dxil") for name in samples for mode in modes}
    if a.prepare_only: return
    # All GPU work is serialized. Each probe or render starts in a fresh worker.
    for name in samples:
        for mode in modes:
            run([sys.executable,a.harness/"run_probe.py",*common,"--profile",
                 "xcl-ray-roots" if name=="raylib" else "xcl-nerf-roots",
                 "--probe",a.harness/"pipeline_stats.exe","--fragment",programs[name,mode],
                 "--out",a.out/f"{name}-{mode}-stats.json"])
    for camera, order in [(a.primary,("project","inputs","window","source")),
                          (a.secondary,("source","window","inputs","project"))]:
        translated_digests = set()
        for i,mode in enumerate(order+tuple(reversed(order))):
            native=mode=="source"
            dst=a.out/f"{camera.name}-{i}-{mode}.json"
            run([sys.executable,a.harness/"run_ray.py",*common,"--camera",camera,
                 "--probe",a.harness/"ray_draw_control.exe",
                 "--fragment",a.native if native else programs["raylib",mode],
                 "--out",dst]+(["--original-source"] if native else []))
            image=dst.with_suffix(".rgba32f")
            captured = json.loads(dst.read_bytes())
            if not captured["draw"]["root_and_readback_guards_intact"]:
                raise ValueError(f"Readback guard failed for {dst.name}")
            if not native:
                translated_digests.add(captured["output_sha256"])
                if len(translated_digests) > 1:
                    raise ValueError(f"Translated GPU images differ for {camera.name}")
            # The probe records the digest and native comparison before releasing this working image.
            image.unlink()
if __name__=="__main__":
    main()
