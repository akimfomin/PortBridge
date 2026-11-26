"""Translate pinned public shaders with a single XCL binary and validate each DXIL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

CASES = [
    ("nerf71", "khronos-vulkan-samples", 71, "khronos"),
    ("nerf73", "khronos-vulkan-samples", 73, "khronos"),
    ("raylib", "raylib-procedural", 0, "raylib"),
    ("mini", "miniengine-display", 0, "mini"),
    ("julia", "raylib-procedural", 1, "raylib"),
]
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def generate(args):
    specs = json.loads(args.census.read_bytes())["rows"]
    args.out.mkdir(exist_ok=True, parents=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("XCL_")}
    env["XCL_DXC_DIR"] = str(args.dxc.resolve())
    results = []
    for arm in args.modes:
        for name, group, index, source_arg in CASES:
            spec = next(row for row in specs if row["group"] == group and row["id"] == index)
            guest = getattr(args, source_arg) / f"{index:03}" / "shader.rdna2"
            abi = spec["rdna"]
            if digest(guest) != abi["sha256"]:
                raise ValueError(f"Unexpected guest bytes for {name}")
            keys = ("wave", "spi_ps_input_ena", "interpolants", "color_mask", "depth_mode")
            flags = [str(abi[key]) for key in keys]
            dxil = args.out / f"{name}-{arm}.dxil"
            subprocess.run([args.compiler, guest, dxil, *flags, "root-4", "generic", arm],
                           env=env, check=True, timeout=90)
            ir = dxil.with_suffix(".ll").read_text(encoding="utf-8")
            ops = re.findall(r"(?m)^\s*%[-\w.]+ = (\w+)", ir)
            results.append(dict(case=name, mode=arm, source=spec["source"], rdna_sha256=abi["sha256"],
                                sha256=digest(dxil), dxil_bytes=dxil.stat().st_size, ssa_definitions=len(ops),
                                ballots=ir.count("call %dx.types.fouri32 @dx.op.waveActiveBallot("),
                                quad_ops=len(re.findall(r"call .*? @dx.op.quad", ir)),
                                branches=len(re.findall(r"(?m)^\s*br ", ir)), phis=ops.count("phi")))
        (args.out / "structure.json").write_text(json.dumps(results, indent=2)+"\n", encoding="utf-8")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("compiler", "census", "khronos", "raylib", "mini", "out", "dxc"):
        p.add_argument("--"+key, type=Path, required=True)
    p.add_argument("--modes", nargs="+", default=["project","whole","inputs","window"])
    generate(p.parse_args())
