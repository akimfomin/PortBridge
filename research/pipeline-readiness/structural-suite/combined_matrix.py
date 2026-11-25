# SPDX-License-Identifier: MIT
"""Measure the individual and joint effects of XCL's three pixel passes."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
from subprocess import SubprocessError
import sys

# Supports a separate local study folder and the checked-in corpus package.
sys.path.append(str(Path(__file__).resolve().parent.parent / "xcl-readguard-corpus-artifacts"))
from fixture_census import command, dxil_shape, hash_file
from open_pixel_census import error_text

ARMS = ("off", "a", "g", "s", "ag", "as", "gs", "ags")
APERTURE_GUARD_ARMS = ("off", "a", "g", "ag")
COMPARISONS = (
    ("off", "a"), ("off", "g"), ("off", "s"),
    ("a", "ag"), ("a", "as"), ("a", "ags"),
    ("g", "ag"), ("g", "gs"), ("s", "as"), ("s", "gs"),
    ("ag", "ags"), ("as", "ags"), ("gs", "ags"), ("off", "ags"),
)
CONFIG = ("wave", "spi_ps_input_ena", "interpolants", "color_mask", "depth_mode")


def arm_environment(base, arm):
    disabled = [name for bit, name in (("g", "read-guards"), ("s", "read-switches")) if bit not in arm]
    return {
        **base,
        "XCL_DXIL_NO_OPT": ",".join(disabled),
        "XCL_DXIL_SWITCH_READ_FUSION": "1" if "s" in arm else "0",
    }


def measure(record, args, environment):
    index, entry = record
    row = {key: entry[key] for key in ("group", "source", "entry", "source_sha256")}
    row["id"] = index
    meta = entry.get("rdna")
    if entry.get("error") or not meta:
        row["input_excluded"] = entry.get("error", {})
        return row
    code = args.input.parent / f"{index:03d}" / "shader.rdna2"
    if hash_file(code) != meta["sha256"]:
        raise ValueError(f"Input digest mismatch for entry {index}")
    row["rdna"] = meta
    interface = [str(meta[key]) for key in CONFIG]
    target = args.out / f"{index:03d}"
    target.mkdir()
    arms = {}
    for arm in args.arms:
        dxil = target / f"{arm}.dxil"
        assembly = dxil.with_suffix(".ll")
        try:
            proof = str(args.base_hi) if "a" in arm else "generic"
            command([args.xcl, code, dxil, *interface, args.layout, proof],
                    env=arm_environment(environment, arm))
            command([args.dxv, dxil])
            asm = assembly.read_text(encoding="utf-8")
            shape = dxil_shape(asm)
            body = asm.split("define void @main() {", 1)[1].split("\n}", 1)[0]
            shape["switch_cases"] = sum(line.strip().startswith("i32 ") and
                                        ", label %" in line for line in body.splitlines())
            shape["phi_incomings"] = sum(line.count("[") for line in body.splitlines() if " = phi " in line)
            arms[arm] = {"bytes": dxil.stat().st_size, "sha256": hash_file(dxil), **shape}
        except (OSError, SubprocessError, ValueError) as error:
            reason = error_text(error, args.out.parent)
            arms[arm] = {"error": re.sub(r"(?i) from [a-z]:\\[^\r\n]*", " from <tool>", reason)}
        finally:
            if index not in args.keep:
                dxil.unlink(missing_ok=True)
                assembly.unlink(missing_ok=True)
    row["arms"] = arms
    return row


def summarize(rows, selected_arms):
    counts = Counter()
    totals = {arm: Counter() for arm in selected_arms}
    for row in rows:
        trials = row.get("arms")
        if not trials:
            counts["source_excluded"] += 1
        elif any("error" in arm for arm in trials.values()):
            counts["adapter_or_validator_excluded"] += 1
        else:
            counts["accepted_in_all_arms"] += 1
            for arm, counters in trials.items():
                totals[arm].update({name: value for name, value in counters.items() if isinstance(value, int)})
    contrasts = {}
    for baseline, candidate in COMPARISONS:
        if baseline not in totals or candidate not in totals:
            continue
        eligible = [row for row in rows if row.get("arms") and
                    not any("error" in arm for arm in row["arms"].values())]
        pairs = [(row["arms"][baseline], row["arms"][candidate]) for row in eligible]
        contrasts[f"{baseline}_to_{candidate}"] = {
            "changed_entries": sum(a["sha256"] != b["sha256"] for a, b in pairs),
            "fewer_switches": sum(b["switches"] < a["switches"] for a, b in pairs),
            "fewer_conditional_branches": sum(b["conditional_branches"] < a["conditional_branches"] for a, b in pairs),
            "fewer_blocks": sum(b["blocks"] < a["blocks"] for a, b in pairs),
            "delta": {key: totals[candidate][key] - value for key, value in totals[baseline].items()},
        }
    return {"counts": counts, "totals": totals, "contrasts": contrasts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("input", "xcl", "dxc", "dxv", "out"):
        parser.add_argument("--" + name, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--layout", choices=("root-4", "heap-4"), default="root-4")
    parser.add_argument("--aperture-guard-only", action="store_true",
                        help="Test the four A/G configurations and disable root read-switch fusion in every arm.")
    parser.add_argument("--base-hi", type=int, default=4)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=1)
    parser.add_argument("--keep", type=int, action="append", default=[])
    parser.add_argument("--only", type=int, action="append", default=[])
    args = parser.parse_args()
    args.arms = APERTURE_GUARD_ARMS if args.aperture_guard_only else ARMS
    args.out.mkdir()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    env = {key: value for key, value in os.environ.items() if not key.startswith("XCL_")}
    env["XCL_DXC_DIR"] = str(args.dxc.parent)
    inputs = [pair for pair in enumerate(source["observations"]) if not args.only or pair[0] in args.only]
    with ThreadPoolExecutor(max_workers=args.jobs) as workers:
        rows = list(workers.map(lambda pair: measure(pair, args, env), inputs))
    result = {
        "xcl_revision": args.revision, "layout": args.layout, "proved_uma_base_hi": args.base_hi,
        "source": source.get("source", source.get("sources")),
        "selected_inputs": args.only, "tested_arms": args.arms,
        "input_manifest_sha256": hash_file(args.input),
        "scope": "Raw AMD PAL pixel replay with synthetic XCL interface, separately validated by DXV. Vulkan bindings and physical execution are unavailable here.",
        "arm_bits": {"a": "aperture specialization", "g": "read guard fusion", "s": "root read switch fusion"},
        "tools_sha256": {name: hash_file(getattr(args, name)) for name in ("xcl", "dxc", "dxv")},
        **summarize(rows, args.arms),
        "observations": rows,
    }
    (args.out / "combined-results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("counts", "contrasts")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
