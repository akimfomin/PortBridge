# SPDX-License-Identifier: MIT
"""Compare XCL's direct pixel outputs on the public in-tree RDNA fixtures."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

# All of these tests end on the CPU. The first is the authors' positive control.
TESTS = (
    "graphics_read_guards_merge_only_equal_window_conditions",
    "branchy_graphics_stages_validate",
    "long_pixel_shader_translates_fast",
    "ps_get_lod_with_a_static_sampler",
    "raw_loads_in_root_windows_are_branchless",
    "pixel_unfused_mad_sets_disable_math_refactoring",
    "fmad_suppresses_disable_math_refactoring_in_compute_and_pixel",
    "dead_fmad_eliminated_by_dce_still_allows_disable_math_refactoring",
    "direct_ps_ballot_uses_quad_ops_and_keeps_entry_exec_live_only",
    "direct_ps_constant_false_ballot_skips_quad_ops",
    "direct_ps_non_vopc_carry_ballot_uses_quad_op",
    "pops_pixel_shader_marks_uavs_as_rov_and_validates",
    "pops_pixel_shader_without_uavs_on_heap_windows_validates_cleanly",
    "non_pops_pixel_shader_does_not_mark_rovs",
    "ps_implicit_lod_sample_and_get_lod_validate",
    "ps_exp_vm_hlsl_and_direct_dxil_codegen",
    "heap_windows_graphics_stages_validate",
)
OPT = "XCL_DXIL_NO_OPT"


def hash_file(path):
    return sha256(path.read_bytes()).hexdigest()


def command(args, env=None, cwd=None):
    return subprocess.run(args, env=env, cwd=cwd, check=True, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=90).stdout


def dxil_shape(text):
    match = re.search(r"^define\s+.*?@main\(\).*?\{\r?\n(.*?)^\}", text, re.S | re.M)
    if not match:
        raise ValueError("Missing DXIL main body")
    body = match.group(1)
    return {
        "blocks": 1 + len(re.findall(r"^(?:;\s*<label>:\d+|[\w.$-]+:)", body, re.M)),
        "conditional_branches": len(re.findall(r"^\s*br i1\b", body, re.M)),
        "switches": len(re.findall(r"^\s*switch\b", body, re.M)),
        "phis": len(re.findall(r"= phi\b", body)),
        "raw_loads": len(re.findall(r"call [^\r\n]*?@dx\.op\.rawBufferLoad\.", body)),
    }


def describe(binary, dxc, dxv):
    with TemporaryDirectory() as directory:
        probe = Path(directory) / "probe.dxil"
        probe.write_bytes(binary.read_bytes())
        command([dxv, probe])
        asm = command([dxc, "-dumpbin", probe])
    binary.with_suffix(".ll").write_text(asm, encoding="utf-8")
    return {"bytes": binary.stat().st_size, "sha256": hash_file(binary), **dxil_shape(asm)}


def collect_tests(exe, dxc, out):
    rows = command([exe, "--list"])
    names = [row.removesuffix(": test") for row in rows.splitlines() if row.endswith(": test")]
    expected = [name for name in names if name.rsplit("::", 1)[-1] in TESTS]
    if Counter(name.rsplit("::", 1)[-1] for name in expected) != Counter(TESTS):
        raise ValueError("Test selection differs from pinned XCL")
    arms = {}
    for arm in ("off", "on"):
        directory = out / ("fixture-" + arm)
        directory.mkdir(exist_ok=False)
        env = {k: v for k, v in os.environ.items() if not k.startswith("XCL_")}
        env["XCL_DXC_DIR"] = str(dxc.parent)
        env["XCL_OPEN_PS_DUMP"] = str(directory.resolve())
        if arm == "off":
            env[OPT] = "read-guards"
        log = command([exe, "--test-threads=1", "--nocapture", "--exact", *expected], env)
        (out / f"fixture-{arm}.log").write_text(log, encoding="utf-8")
        if f"{len(TESTS)} passed; 0 failed" not in log or "SKIPPED" in log:
            raise ValueError(f"Unexpected test run, see fixture-{arm}.log")
        arms[arm] = {path.stem: path for path in directory.glob("*.dxil")}
    if set(arms["off"]) != set(arms["on"]) or not arms["on"]:
        raise ValueError("Test arms produced different or empty fixture sets")
    return arms


def compare(arms, dxc, dxv):
    rows = []
    for name in sorted(arms["on"]):
        off, on = (arms[arm][name] for arm in ("off", "on"))
        rdna = off.with_suffix(".rdna2")
        abi = off.with_suffix(".abi").read_text(encoding="utf-8")
        if (rdna.read_bytes() != on.with_suffix(".rdna2").read_bytes()
                or abi != on.with_suffix(".abi").read_text(encoding="utf-8")):
            raise ValueError(f"{name}: compiler inputs differ")
        before = describe(off, dxc, dxv)
        after = describe(on, dxc, dxv)
        rows.append({"fixture": name.rsplit("--", 1)[0].replace("--", "::"),
                     "control": name.split("--")[-2] == TESTS[0],
                     "rdna_bytes": rdna.stat().st_size, "rdna_sha256": hash_file(rdna),
                     "abi": abi.strip(), "off": before, "on": after,
                     "changed": before["sha256"] != after["sha256"]})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xcl-tests", type=Path, required=True)
    parser.add_argument("--dxc", type=Path, required=True)
    parser.add_argument("--dxv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir()
    arms = collect_tests(args.xcl_tests.resolve(), args.dxc.resolve(), args.output)
    rows = compare(arms, args.dxc.resolve(), args.dxv.resolve())
    manifest = {"xcl_commit": "8e4c4a63143702d5e5da79484273143e0b76eb92",
                "fixture_origin": "XCL public, source-authored tests, GPL-2.0-only",
                "xcl_executable_sha256": hash_file(args.xcl_tests),
                "dxc_sha256": hash_file(args.dxc), "dxv_sha256": hash_file(args.dxv),
                "observations": rows}
    (args.output / "fixtures.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(Counter(("control" if row["control"] else "in-tree", row["changed"]) for row in rows))


if __name__ == "__main__":
    main()
