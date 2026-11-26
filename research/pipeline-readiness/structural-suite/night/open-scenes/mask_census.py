# SPDX-License-Identifier: MIT
"""Replay complete PAL extraction manifests and record paired XCL mask outputs."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import time


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def execute(args, env):
    return subprocess.run(args, env=env, capture_output=True, check=True,
                          encoding="utf-8", errors="replace", timeout=120)


def shape(text):
    body = re.search(r"^define [^\n]+@main\(\)[^\n]*\{\n(.*?)^\}", text, re.M | re.S)
    if body is None:
        raise ValueError("Missing DXIL entry point")
    contents = body.group(1)
    return {
        "ballots": contents.count("call %dx.types.fouri32 @dx.op.waveActiveBallot("),
        "quad_reads": len(re.findall(r"call [^\n]+?@dx\.op\.quad(?:Op|ReadLaneAt)\.", contents)),
        "wave_reads": len(re.findall(r"call [^\n]+?@dx\.op\.waveReadLane(?:At|First)\.", contents)),
        "blocks": 1 + len(re.findall(r"^(?:; *<label>:\d+|[\w.$-]+:)", contents, re.M)),
        "branches": len(re.findall(r"^\s*br i1\b", contents, re.M)),
        "phis": contents.count(" = phi "),
        "instructions": len(re.findall(r"^  \S", contents, re.M)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--observer", type=Path, required=True)
    parser.add_argument("--dxc", type=Path, required=True, help="DXC executable used by the XCL observer")
    parser.add_argument("--dxv", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-tree", required=True)
    parser.add_argument("--proof-base", choices=("4", "generic"), default="4",
                        help="Select the ABI proof accepted by this XCL observer")
    parser.add_argument("--modes", nargs="+", default=["whole", "local"],
                        help="Mode names supported by the chosen observer")
    args = parser.parse_args()
    if args.modes[0] != "whole" or any(not re.fullmatch("[a-z-]+", m) for m in args.modes):
        parser.error("Use 'whole' first and lowercase mode names")
    if len(args.modes) != len(set(args.modes)):
        parser.error("Modes must be distinct")
    args.out.mkdir(parents=True, exist_ok=False)
    env = {key: value for key, value in os.environ.items() if not key.startswith("XCL_")}
    env.update(XCL_DXC_DIR=str(args.dxc.resolve().parent), XCL_DXIL_SWITCH_READ_FUSION="1")
    rows = []
    result = {"source_tree": args.source_tree, "modes": args.modes, "proof_base": args.proof_base,
              "tool_hashes": {key: digest(getattr(args, key)) for key in ("observer", "dxc", "dxv")},
              "input_manifests": [], "rows": rows}
    for manifest in args.manifest:
        source = json.loads(manifest.read_text(encoding="utf-8"))
        result["input_manifests"].append({"file": manifest.name, "sha256": digest(manifest),
                                        "sources": source.get("source", source.get("sources"))})
        for index, entry in enumerate(source["observations"]):
            row = {key: entry[key] for key in ("group", "source", "entry", "source_sha256")}
            if not re.fullmatch(r"[\w.-]+", row["group"]):
                raise ValueError("Invalid source group")
            rows.append(row)
            row["id"] = index
            meta = entry.get("rdna")
            if entry.get("error") or not meta:
                row["excluded_before_xcl"] = entry.get("error", {"stage": "missing_pal"})
                continue
            row["rdna"] = meta
            case = manifest.parent / f"{index:03d}" / "shader.rdna2"
            if digest(case) != meta["sha256"]:
                raise ValueError(f"Digest mismatch in {manifest.name} entry {index}")
            out = args.out / row["group"] / f"{index:03d}"
            out.mkdir(parents=True)
            variants = row["variants"] = {}
            order = args.modes if index % 2 == 0 else list(reversed(args.modes))
            for mode in order:
                dxil = out / f"{mode}.dxil"
                stage = "observe"
                try:
                    abi = [str(meta[key]) for key in ("wave", "spi_ps_input_ena", "interpolants", "color_mask", "depth_mode")]
                    begin = time.perf_counter()
                    completed = execute([args.observer, case, dxil, *abi, "root-4", args.proof_base, mode], env)
                    wall_ms = (time.perf_counter() - begin) * 1000
                    stage = "dxv"
                    execute([args.dxv, dxil], env)
                    asm = dxil.with_suffix(".ll").read_text(encoding="utf-8")
                    stats = {"dxil_bytes": dxil.stat().st_size, "dxil_sha256": digest(dxil),
                             "observer_wall_ms": round(wall_ms, 4), **shape(asm)}
                    timing = re.search(r"(?m)^translation_ns=(\d+)$", completed.stdout)
                    if timing:
                        stats["translation_ns"] = int(timing.group(1))
                    repeats = re.search(r"(?m)^translation_samples_ns=([0-9,]+)$", completed.stdout)
                    if repeats:
                        stats["translation_samples_ns"] = [int(ns) for ns in repeats.group(1).split(",")]
                    variants[mode] = stats
                except (subprocess.SubprocessError, OSError, ValueError) as error:
                    detail = error.stderr or error.stdout if isinstance(error, subprocess.CalledProcessError) else str(error)
                    variants[mode] = {"error": stage, "detail": detail.strip()[:480]}
            with (args.out / "progress.jsonl").open("a", encoding="utf-8") as progress:
                progress.write(json.dumps(row, separators=(",", ":")) + "\n")
    groups = result["summary"] = {}
    for row in rows:
        group = groups.setdefault(row["group"], Counter())
        group["attempted"] += 1
        if "excluded_before_xcl" in row:
            group["excluded_before_xcl"] += 1
            continue
        if any("error" in variant for variant in row["variants"].values()):
            group["excluded_at_xcl_or_dxv"] += 1
            continue
        group["validated_all"] += 1
        whole = row["variants"]["whole"]
        for mode in args.modes[1:]:
            alternate = row["variants"][mode]
            group[f"{mode}_changed_dxil"] += int(whole["dxil_sha256"] != alternate["dxil_sha256"])
            group[f"{mode}_fewer_ballots"] += int(whole["ballots"] > alternate["ballots"])
            group[f"{mode}_more_ballots"] += int(whole["ballots"] < alternate["ballots"])
    (args.out / "census.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(groups, indent=2))


if __name__ == "__main__":
    main()
