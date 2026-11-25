# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
DXC = ROOT.parent / "portbridge-xcl-925-evidence/dxc-v1.9.2602/bin/x64/dxc.exe"
VALIDATOR = ROOT.parent / "Leonida-portable-vulkan/tools/khronos-shader-tools/install/bin/spirv-val.exe"
WORKER = ROOT / "portbridge-vulkan-cache.exe"
SOURCE = ROOT / "fixture.hlsl"
RECIPES = 6
LAYOUT = b"cs-main/v1 set=0 binding=0 storage-buffer compute\0"
CACHES = ("combined.vkc", *(f"{i}.vkc" for i in range(RECIPES)))
IDENTITY = ("vendor", "device", "driver", "api", "instance_api", "luid_valid", "luid",
            "cache_uuid", "device_uuid", "driver_uuid", "feedback_path")
ORDERS = (
    ("absent", "separate", "combined"),
    ("separate", "combined", "absent"),
    ("combined", "absent", "separate"),
    ("absent", "combined", "separate"),
    ("combined", "separate", "absent"),
    ("separate", "absent", "combined"),
)
GROUP_OFFSETS = (1700, 8300, 22300, 50900, 100900, 142300)
VULKAN_OVERRIDES = (
    "VK_DRIVER_FILES", "VK_ICD_FILENAMES", "VK_ADD_DRIVER_FILES", "VK_LOADER_DRIVERS_SELECT",
    "VK_LOADER_DRIVERS_DISABLE", "VK_INSTANCE_LAYERS", "VK_LAYER_PATH", "VK_ADD_LAYER_PATH",
    "VK_LOADER_LAYERS_ENABLE", "VK_LOADER_LAYERS_DISABLE", "VK_LOADER_LAYERS_ALLOW",
    "VK_LAYER_SETTINGS_PATH",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bundle(directory):
    digest = hashlib.sha256(LAYOUT)
    shaders = []
    for i in range(RECIPES):
        data = (directory / f"{i}.spv").read_bytes()
        if not 20 <= len(data) <= 4096 or len(data) % 4 or data[:4] != b"\x03\x02\x23\x07":
            raise ValueError(f"invalid module {directory.name}/{i}.spv")
        shaders.append(sha(data))
        digest.update(struct.pack("<I", len(data)))
        digest.update(data)
    if len(set(shaders)) != RECIPES:
        raise ValueError(f"duplicated modules in {directory.name}")
    return {"bundle_sha256": digest.hexdigest(), "module_sha256": shaders}


def orders(slot):
    cycle_start = (slot // 3) * 3
    fresh_slot = cycle_start + (slot + 1) % 3
    return {"same": ORDERS[slot], "fresh": ORDERS[fresh_slot]}


def prepare(directory, campaign, start_slot, groups, dxc, validator):
    if start_slot + groups > len(ORDERS):
        raise ValueError("the requested groups extend beyond the six order slots")
    directory.mkdir()
    manifest = {
        "campaign": campaign,
        "start_slot": start_slot,
        "source_sha256": sha(SOURCE.read_bytes()),
        "dxc_sha256": sha(dxc.read_bytes()),
        "spirv_val_sha256": sha(validator.read_bytes()),
        "groups": [],
    }
    known_modules = set()
    for group in range(groups):
        slot = start_slot + group
        cases = {}
        for kind, offset in (("before", 20), ("replay", 0)):
            case = directory / f"{group}-{kind}"
            case.mkdir()
            salts = [campaign * 1_000_000 + GROUP_OFFSETS[slot] + offset + i for i in range(RECIPES)]
            for i, salt in enumerate(salts):
                module = case / f"{i}.spv"
                subprocess.run([dxc, "-spirv", "-fspv-target-env=vulkan1.1", "-O3", "-T", "cs_6_0",
                                "-E", "main", "-D", f"FIXTURE_SALT={salt}u", "-Fo", module, SOURCE],
                               check=True, timeout=15)
                subprocess.run([validator, "--target-env", "vulkan1.1", module], check=True, timeout=15)
            data = bundle(case)
            if known_modules.intersection(data["module_sha256"]):
                raise ValueError("modules are shared by independent cases")
            known_modules.update(data["module_sha256"])
            cases[kind] = {"path": case.name, "salts": salts, **data}
        manifest["groups"].append({"order_slot": slot, "orders": orders(slot), **cases})
    (directory / "prepared.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"validated {len(known_modules)} distinct generated SPIR-V modules in {directory}")


def expect_bundle(directory, metadata):
    actual = bundle(directory)
    if any(actual[key] != metadata[key] for key in actual):
        raise ValueError(f"prepared shader hashes changed in {directory.name}")


def expect_caches(directory, seed):
    for name, metadata in zip(CACHES, seed["cache"], strict=True):
        cache = (directory / name).read_bytes()
        if len(cache) < 32 or len(cache) != metadata["bytes"] or sha(cache) != metadata["sha256"]:
            raise ValueError(f"seeded cache {name} changed")
        expected_header = (32, 1, seed["vendor"], seed["device"], bytes.fromhex(seed["cache_uuid"]))
        if struct.unpack_from("<4I16s", cache) != expected_header:
            raise ValueError(f"seeded cache {name} identity mismatch")


def arm(executable, binary_hash, mode, adapter, case, case_meta, log, label, seed=None):
    expect_bundle(case, case_meta)
    if seed is not None:
        expect_caches(case, seed)
    if sha(executable.read_bytes()) != binary_hash:
        raise ValueError(f"binary bytes changed for {executable.name}")
    start = time.perf_counter()
    try:
        child = subprocess.run([executable, mode, adapter, case], capture_output=True, encoding="utf-8",
                               errors="replace", timeout=8)
    except subprocess.TimeoutExpired:
        log.write(json.dumps({"arm": label, "failure": "parent timeout"}) + "\n")
        raise
    wall_ms = (time.perf_counter() - start) * 1000
    try:
        report = json.loads(child.stdout)
    except json.JSONDecodeError:
        report = None
    log.write(json.dumps({"arm": label, "exe": executable.name, "mode": mode, "case": case.name,
                          "adapter": adapter, "wall_ms": wall_ms, "exit": child.returncode,
                          "report": report, "stderr": child.stderr,
                          "raw_stdout_if_invalid": child.stdout if report is None else None}) + "\n")
    if child.returncode or report is None or report["status"] != "returned" or not report["reaped"]:
        raise RuntimeError(f"{label}: {report['status'] if report else 'missing report'} (see attempts.jsonl)")
    if report["bundle_sha256"] != case_meta["bundle_sha256"]:
        raise ValueError(f"{label}: worker used different shader inputs")
    if seed is not None:
        if any(report[key] != seed[key] for key in IDENTITY):
            raise ValueError(f"{label}: adapter, driver or feedback path changed")
        expect_caches(case, seed)
        for slot in {"absent": (), "combined": (0,), "separate": range(1, RECIPES + 1)}[mode]:
            for key in ("bytes", "sha256"):
                if report["cache"][slot][key] != seed["cache"][slot][key]:
                    raise ValueError(f"{label}: worker loaded a different cache in slot {slot}")
    expect_bundle(case, case_meta)
    pipelines = report["pipeline"]
    if len(pipelines) != RECIPES or any(
        stage["feedback_valid"] != (stage["app_hit"] is not None) for stage in pipelines
    ):
        raise ValueError(f"{label}: inconsistent pipeline feedback")
    if report["feedback_path"] == 0 and any(stage["feedback_valid"] for stage in pipelines):
        raise ValueError(f"{label}: feedback reported without advertised support")
    if mode == "absent" and any(stage["app_hit"] for stage in pipelines):
        raise ValueError(f"{label}: app-cache hit reported for null app cache")
    return report


def summary(report):
    pipelines = report["pipeline"]
    valid = sum(stage["feedback_valid"] for stage in pipelines)
    pipeline_ms = sum(stage["ms"] for stage in pipelines)
    open_ms = sum(cache["open_ms"] for cache in report["cache"])
    return {"pipeline_ms": pipeline_ms, "cache_open_ms": open_ms, "replay_ms": pipeline_ms + open_ms,
            "valid_feedback": valid, "application_hits": sum(stage["app_hit"] is True for stage in pipelines)
                                                          if valid else None}


def execute(directory, adapter):
    overrides = [name for name in VULKAN_OVERRIDES if os.environ.get(name)]
    if overrides:
        raise ValueError(f"nondefault Vulkan loader variables are present: {', '.join(overrides)}")
    manifest = json.loads((directory / "prepared.json").read_text(encoding="utf-8"))
    groups = manifest["groups"]
    campaign = manifest["campaign"]
    start_slot = manifest.get("start_slot", 0)
    if (not 1 <= campaign <= 999 or not 0 <= start_slot < len(ORDERS) or
        not 1 <= len(groups) <= len(ORDERS) - start_slot or
        sha(SOURCE.read_bytes()) != manifest["source_sha256"]):
        raise ValueError("invalid prepared manifest")
    for i, metadata in enumerate(groups):
        slot = start_slot + i
        if "orders" in metadata:
            expected = {cohort: list(order) for cohort, order in orders(slot).items()}
            if metadata["order_slot"] != slot or metadata["orders"] != expected:
                raise ValueError(f"prepared order differs from the expected schedule in group {i}")
        for kind in ("before", "replay"):
            if metadata[kind]["path"] != f"{i}-{kind}":
                raise ValueError("unexpected shader case directory")
            expect_bundle(directory / metadata[kind]["path"], metadata[kind])
    binary = WORKER.read_bytes()
    binary_hash = sha(binary)
    executables = directory / "programs"
    executables.mkdir()
    progress = []
    (directory / "run.json").write_text(json.dumps({"probe_sha256": binary_hash, "adapter": adapter,
                                                   "campaign": campaign, "start_slot": start_slot}, indent=2) + "\n",
                                       encoding="utf-8")
    with (directory / "attempts.jsonl").open("x", encoding="utf-8", buffering=1) as log:
        for i, metadata in enumerate(groups):
            slot = start_slot + i
            prefix = f"c{campaign}-g{slot}"
            same = executables / f"{prefix}-continuous.exe"
            same.write_bytes(binary)
            before = executables / f"{prefix}-preseed-control.exe"
            before.write_bytes(binary)
            control = arm(before, binary_hash, "absent", adapter, directory / metadata["before"]["path"],
                          metadata["before"], log, f"{i}:preseed")
            case = directory / metadata["replay"]["path"]
            seed = arm(same, binary_hash, "seed", adapter, case, metadata["replay"], log, f"{i}:seed")
            expect_caches(case, seed)
            if any(control[key] != seed[key] for key in IDENTITY):
                raise ValueError("preseed adapter or driver differs from seed")
            replay_orders = orders(slot)
            result = {"group": i, "order_slot": slot, "orders": replay_orders, "preseed_reference": summary(control),
                      "archive_bytes": [entry["bytes"] for entry in seed["cache"]],
                      "header_only": [entry["bytes"] == 32 for entry in seed["cache"]],
                      "cohorts": {}}
            cohorts = ("same", "fresh") if slot % 2 == 0 else ("fresh", "same")
            result["cohort_order"] = cohorts
            for cohort in cohorts:
                measured = {}
                for mode in replay_orders[cohort]:
                    executable = same
                    if cohort == "fresh":
                        executable = executables / f"{prefix}-fresh-{mode}.exe"
                        executable.write_bytes(binary)
                    label = f"{i}:{cohort}:{mode}"
                    measured[mode] = summary(arm(executable, binary_hash, mode, adapter, case,
                                                 metadata["replay"], log, label, seed=seed))
                result["cohorts"][cohort] = measured
            progress.append(result)
            temporary = directory / "groups.tmp.json"
            temporary.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
            temporary.replace(directory / "groups.json")
            print(f"group {i}: complete", flush=True)


def main():
    arguments = argparse.ArgumentParser()
    sub = arguments.add_subparsers(dest="action", required=True)
    compiler = sub.add_parser("prepare")
    compiler.add_argument("directory", type=Path)
    compiler.add_argument("--campaign", type=int, required=True, choices=range(1, 1000),
                          metavar="CAMPAIGN")
    compiler.add_argument("--groups", type=int, default=1, choices=range(1, len(ORDERS) + 1))
    compiler.add_argument("--start-slot", type=int, default=0, choices=range(len(ORDERS)))
    compiler.add_argument("--dxc", type=Path, default=DXC)
    compiler.add_argument("--spirv-val", type=Path, default=VALIDATOR)
    launch = sub.add_parser("run")
    launch.add_argument("directory", type=Path)
    launch.add_argument("--adapter", required=True)
    args = arguments.parse_args()
    directory = args.directory.resolve()
    if directory.parent != ROOT:
        arguments.error("choose a case directory directly under the fixture directory")
    if args.action == "prepare":
        prepare(directory, args.campaign, args.start_slot, args.groups, args.dxc.resolve(), args.spirv_val.resolve())
    else:
        execute(directory, args.adapter)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
