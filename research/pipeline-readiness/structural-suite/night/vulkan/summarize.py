# SPDX-License-Identifier: MIT
"""Join per-stage driver reports with reference images and Vulkan timestamps."""
import argparse
import json
import statistics
from pathlib import Path


def report(path):
    return json.loads(path.read_text(encoding="utf-8"))


def stage_stats(result, stage):
    rows = [x for x in result["executables"] if x["stage_flags"] == stage]
    if len(rows) != 1:
        raise ValueError("Expected one executable per reviewed stage")
    executable = rows[0]
    values = {s["name"]: s["value"] for s in executable["statistics"]}
    return {"binary_bytes": values["Binary Size"], "registers": values["Register Count"],
            "representations": len(executable["internal_representations"])}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("experiment", type=Path)
    p.add_argument("reference_corpus", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    stage = {}
    for path in sorted((args.experiment / "physical").glob("*.json")):
        raw = report(path)
        result = raw["physical_pipeline"]
        vs = stage_stats(result, 1)
        if vs["binary_bytes"] != 768:
            raise ValueError("Vertex control differed from this pinned driver / experiment")
        fs = stage_stats(result, 16)
        stage[path.stem] = {"fragment_sha256": raw["fragment_sha256"],
                            "spirv_bytes": result["fragment_spirv_bytes"], **fs}
    scenes = {}
    for camera in ("primary", "secondary"):
        reference = report(args.reference_corpus / f"ray800-{camera}" / "scene.json")
        dx_hashes = {r["image"]["sha256"] for pair in reference["pairs"] for r in pair["variants"].values()}
        rows = []
        for path in sorted((args.experiment / "draws").glob(f"{camera}-*.json")):
            raw = report(path)
            source = raw["fragment"] == "source.spv"
            mode = "source" if source else raw["fragment"].removeprefix("ray-").removesuffix("-roots.spv")
            draw = raw["draw"]
            ms = [t * draw["timestamp_period_ns"] / (draw["draws_per_interval"] * 1e6) for t in draw["gpu_ticks"]]
            if not draw["root_and_readback_guards_intact"] or len(ms) != 5 or not all(t > 0 for t in ms):
                raise ValueError("Invalid timing, roots or readback")
            if not source and (raw["output_sha256"] not in dx_hashes or len(dx_hashes) != 1):
                raise ValueError(f"{camera} {mode} does not agree across D3D12 and Vulkan")
            stage_key = "source-000" if source else f"ray-{mode}"
            if raw["fragment_sha256"] != stage[stage_key]["fragment_sha256"]:
                raise ValueError("Draw and stage statistics used different SPIR-V")
            captured = stage_stats(draw, 16) if "executables" in draw else None
            if captured and captured["binary_bytes"] != stage[stage_key]["binary_bytes"]:
                raise ValueError("Timed pipeline disagreed with stand-alone capture")
            rows.append({"input": path.name, "mode": mode, "capture": bool(captured),
                         "gpu_median_ms": statistics.median(ms), "gpu_range_ms": [min(ms), max(ms)],
                         "captured_stage": captured, "output_sha256": raw["output_sha256"], "vs_native_gl": raw["vs_native_gl"]})
        scenes[camera] = {"native_gl_median_ms": statistics.median(reference["gl"]["gpu_ms_per_draw"]),
                          "native_gl_sha256": reference["gl_image"]["sha256"], "d3d12_sha256": next(iter(dx_hashes)),
                          "rows": rows}
    args.output.write_text(json.dumps({"fragment_stages": stage, "scenes": scenes}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
