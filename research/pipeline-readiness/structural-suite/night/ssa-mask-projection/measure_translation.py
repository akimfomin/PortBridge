# SPDX-License-Identifier: MIT
"""Counterbalanced measurement of the full in-process guest-to-DXIL translation."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(args):
    args.output.mkdir(parents=True, exist_ok=False)
    rows = json.loads(args.census.read_bytes())["rows"]
    cases = [("khronos-vulkan-samples", 71, args.khronos), ("raylib-procedural", 0, args.raylib),
             ("khronos-vulkan-samples", 73, args.khronos), ("raylib-procedural", 1, args.raylib)]
    if args.miniengine_display:
        cases.append(("miniengine-display", 0, args.miniengine_display))
    env = {k: v for k, v in os.environ.items() if not k.startswith("XCL_")}
    env["XCL_DXC_DIR"] = str(args.dxc.resolve())
    report = {"compiler": args.compiler,
              "observer_sha256": digest(args.observer), "blocks": [], "summaries": []}
    for block in range(args.blocks):
        sequence = cases if block % 2 == 0 else reversed(cases)
        for group, idx, source_dir in sequence:
            spec = next(r for r in rows if r["group"] == group and r["id"] == idx)
            rdna = spec["rdna"]
            source = source_dir / f"{idx:03}" / "shader.rdna2"
            if digest(source) != rdna["sha256"]:
                raise ValueError("guest digest")
            abi = [str(rdna[k]) for k in ("wave", "spi_ps_input_ena", "interpolants", "color_mask", "depth_mode")]
            key = group + f"-{idx:03}"
            row = {"name": key, "block": block, "arms": {}}
            for arm in (("whole", "project") if (block + idx) % 2 == 0 else ("project", "whole")):
                out = args.output / (key + "-" + arm + ".dxil")
                proc = subprocess.run([args.observer.resolve(), source, out, *abi, "root-4", "generic", arm],
                                      capture_output=True, check=True, env=env, timeout=40)
                values = ast.literal_eval(re.search(rb"(?m)^samples_ns=(\[[0-9, ]+\])", proc.stdout)[1].decode())
                if len(values) != 7 or digest(out) != spec["variants"][arm]["dxil_sha256"]:
                    raise AssertionError("unexpected count or different compiled program")
                row["arms"][arm] = {"ns": values, "median_ns": statistics.median(values), "dxil_sha256": digest(out)}
            report["blocks"].append(row)
            print(block, key, *(round(row["arms"][a]["median_ns"] / 1e6, 2) for a in ("whole","project")), flush=True)
    for key in sorted({r["name"] for r in report["blocks"]}):
        matched = [r["arms"] for r in report["blocks"] if r["name"] == key]
        summary = {"name": key, "blocks": len(matched)}
        for arm in ("whole", "project"):
            vals = [m[arm]["median_ns"] / 1e6 for m in matched]
            summary[arm] = {"median_of_block_medians_ms": statistics.median(vals), "min_ms": min(vals), "max_ms": max(vals)}
        report["summaries"].append(summary)
    (args.output / "translation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("observer", "dxc", "census", "khronos", "raylib", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--compiler", default="ed8baf5de7bfe73208974d08a570acc95f978437")
    parser.add_argument("--miniengine-display", type=Path)
    parser.add_argument("--blocks", type=int, choices=(2, 4, 6), default=4)
    check(parser.parse_args())
