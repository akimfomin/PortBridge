"""Validate retained corpus comparisons, five ablations and separate SPIR-V module sizes."""
import csv
import gzip
import json
from pathlib import Path
from reuse_raylib import binary

ROOT=Path(__file__).resolve().parent
def main():
    corpus=json.loads(gzip.decompress((ROOT/"corpus.json.gz").read_bytes()))
    rows=corpus["rows"]
    assert len(rows)==corpus["accepted"]==202 and corpus["prior_inputs"]==222
    assert len({(r["group"],r["id"]) for r in rows})==len(rows)
    assert len({r["input_sha256"] for r in rows})==151
    assert all(r["pinned_archive_match"] for r in rows)
    for mode,expected in [("project-ballot",(94,1220,0,37604)),("project-ballot-quad",(94,1220,816,55636))]:
        sums=[0,0,0,0]
        for r in rows:
            old,new=r["project"],r[mode]
            assert [new[k] for k in ("feature_flags","branches","phis")]==[old[k] for k in ("feature_flags","branches","phis")]
            assert new["checked_observable_graph"]["blocks"] and new["checked_observable_graph"]["roots"]
            for i,v in enumerate((new["sha256"]!=old["sha256"],old["ballots"]-new["ballots"],
                                  old["quads"]-new["quads"],old["dxil_bytes"]-new["dxil_bytes"])):
                sums[i]+=v
        assert tuple(sums)==expected,(mode,sums)
        print(mode,"changed entries, removed ballots, removed quad reads, total byte delta:",*sums)
    small=sorted((r["project"]["dxil_bytes"]-r["project-ballot-quad"]["dxil_bytes"] for r in rows),reverse=True)
    assert small[:3]==[26656,26312,404]
    ablation=json.loads((ROOT/"structure.json").read_bytes())
    assert len({(r["case"],r["mode"]) for r in ablation})==30
    converted=json.loads((ROOT/"validated-spirv.json").read_bytes())
    assert len(converted)==18
    shapes={(r["case"],r["mode"]):r for r in ablation}
    for v in converted:
        r=shapes[v["case"],v["mode"]]
        assert v["dxil_sha256"]==r["sha256"]
        assert (v["ballots"],v["quad_reads"])==(r["ballots"],r["quad_ops"])
    with (ROOT/"census-existing.csv").open() as f:
        existing=list(csv.DictReader(f))
    assert len(existing)==202 and sum(int(r["dead_no_direct_ssa_uses"]) for r in existing)==1228
    native={k:v["receipt"] for k,v in json.loads(gzip.decompress((ROOT/"native-evidence.json.gz").read_bytes())).items()}
    spv={(r["case"],r["mode"]):r["spirv_sha256"] for r in converted}
    nerf=[native["nerf71-prior"],native["nerf71-pruned"]]
    assert all(nerf[0][s]==nerf[1][s] for s in ("vertex_sha256","probe_sha256"))
    before_layout,after_layout=({k:v for k,v in d["layout"].items() if k!="structure"} for d in nerf)
    assert before_layout==after_layout
    for item,mode,size in zip(nerf,("project","project-ballot-quad"),(411392,411136)):
        assert item["fragment_sha256"]==spv["nerf71",mode]
        assert binary(item["physical_pipeline"])==size
    cameras=json.loads((ROOT/"matched-raylib.json").read_bytes())
    assert {r["camera"] for r in cameras}=={"primary","secondary"}
    for row in cameras:
        prefix="raylib-"+row["camera"]
        before,after=native[prefix+"-prior"],native[prefix+"-matched"]
        assert before["fragment_sha256"]==spv["raylib","project"] and after["fragment_sha256"]==spv["raylib","project-ballot-quad"]
        assert all(before[k]==after[k]==row[k] for k in ("vertex_sha256","worker_sha256","references","scene_controls","output_sha256"))
        assert binary(native["raylib-prior-stat"]["physical_pipeline"])==binary(after["draw"])==197888
    print("NVIDIA fragment executable bytes: NeRF 071 411392 -> 411136; raylib 197888 -> 197888; both full readbacks match")
    comparator=json.loads((ROOT/"spirvtools.json").read_bytes())
    assert comparator["optimizer"].startswith("SPIRV-Tools v2026.4")
    assert len({(v["shader"],v["mode"],v["passes"][0]) for v in comparator["runs"]})==12
    for v in comparator["runs"]:
        key=v["shader"],v["mode"]
        assert v["input_sha256"]==spv[key]
        assert (v["ballots"],v["quads"])==(shapes[key]["ballots"],shapes[key]["quad_ops"])
    print("SPIRV-Tools v2026.4 retained the subgroup counts in every input under both optimizer pipelines")
    draws=json.loads(gzip.decompress((ROOT/"nerf-draws.json.gz").read_bytes()))
    prep=draws["preparation"]
    assert prep["source_sha"]==spv["nerf71","project-ballot-quad"] and prep["diagnostics"]
    assert prep["counts"]==dict(bounded_load_ptr=554,window_offsets=552,lookup_accesses=4,image_accesses=12,fault_outputs=1)
    for case,pixels in (("smoke",256),("frame",57600)):
        old,new=draws["strict-"+case],draws["swept-"+case]
        assert all(old[k]==new[k] for k in ("worker_sha256","vertex_sha256","inputs","output_sha256","cpu_sha256","native_sha256"))
        assert prep["output_sha"]==new["fragment_sha256"]
        assert new["gpu"]["root_and_readback_guards_intact"] and new["width"]*new["height"]==pixels
        m=new["metrics"]
        assert m["diagnostic_alpha"]==m["alpha_mismatches"]==0
        assert all(m[k]["pixels"]==pixels and m[k]["exact_alpha"]==pixels and m[k]["max_abs"]<1e-4 for k in ("native","cpu"))
    assert draws["swept-frame"]["metrics"]["native"]["exact_clear_rgba"]==5095
    print("Both bounded physical NeRF frames matched strict SSA, the CPU oracle and the source Vulkan fragment")
    return rows

if __name__=="__main__":
    main()

