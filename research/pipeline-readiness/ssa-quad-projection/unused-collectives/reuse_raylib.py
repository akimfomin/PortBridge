"""Join historical physical raylib receipts by exact module, camera, worker and frame identity."""
import argparse
import json
from pathlib import Path

def read(p):
    return json.loads(p.read_bytes())

def binary(physical):
    fs=next(stage for stage in physical["executables"] if stage["name"]=="FS")
    return next(stat["value"] for stat in fs["statistics"] if stat["name"]=="Binary Size" and stat["format"]==2)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ("inputs","current","historical","out"):
        ap.add_argument("--"+k,required=True,type=Path)
    a=ap.parse_args()
    modules={(r["case"],r["mode"]):r for r in read(a.inputs)}
    rows=[]
    for camera,current_file in [("primary","ray800-primary-0-project.json"),("secondary","ray800-secondary-3-project.json")]:
        old=read(a.current/current_file)
        matched=read(a.historical/(camera+"-project.json"))
        exact={}
        for key in ("vertex_sha256","worker_sha256","scene_controls","references","output_sha256"):
            assert old[key]==matched[key],key
            exact[key]=old[key]
        for key in ("adapter","driver_version_raw","api_version_raw","timestamp_period_ns","width","height","subgroup_size","root_and_readback_guards_intact"):
            assert old["draw"][key]==matched["draw"][key],key
            exact[key]=old["draw"][key]
        assert exact["root_and_readback_guards_intact"]
        for mode,record in [("project",old),("project-ballot-quad",matched)]:
            assert record["fragment_sha256"]==modules["raylib",mode]["spirv_sha256"]
        ref=read(a.current/"raylib-project-stats.json")
        assert ref["fragment_sha256"]==old["fragment_sha256"]
        rows.append(dict(camera=camera,before_spirv=old["fragment_sha256"],after_spirv=matched["fragment_sha256"],
            reference_executable=binary(ref["physical_pipeline"]),matched_executable=binary(matched["draw"]),**exact))
    a.out.write_text(json.dumps(rows,indent=2)+"\n",encoding="utf8")

if __name__=="__main__":
    main()

