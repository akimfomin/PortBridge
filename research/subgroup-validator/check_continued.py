# SPDX-License-Identifier: MIT
"""Validate emitted SPIR-V from two public Continued synthetic workloads."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from spirv_transport import inspect


def mutate(assembly, pattern, replacement, expected):
    changed, count = re.subn(pattern, replacement, assembly)
    if count != expected:
        raise ValueError(f"fixture drift: expected {expected} replacements, got {count}")
    return changed


def run(checkout: Path, output: Path, tools: Path):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip()
    source_status = subprocess.check_output(
        ["git", "status", "--porcelain", "--", "tools", "tests/semantic", "runtime/test/shaders"],
        cwd=checkout, text=True,
    )
    if os.environ.get("LEONIDA_TOOLS_DIR"):
        raise ValueError("unset LEONIDA_TOOLS_DIR to replay the translator from this checkout")
    fixture_root = checkout / "tests" / "semantic"
    sys.path.insert(0, str(fixture_root))
    import support
    import spirv_mini_interp as interpreter
    import test_wave64_cross_half as cross
    import test_wave64_subgroup_ops as partial
    sys.path.pop(0)

    native = cross.translate("cs_w64x_bpermute")
    partial_header = partial.compute_header(partial.os.path.join(partial.ASM_DIR, "cs_w64x_partial.asm"))
    small = support.translate_fixture("cs_w64x_partial", fssm=bytes(partial_header))
    bad_base = mutate(native,
                      r"(= OpLoad %uint %sg_lane\n\s*%\w+ = OpBitwiseAnd %uint %\w+ )%c20",
                      r"\g<1>%c0", 3)
    bad_fallback = mutate(small,
                          r"(?P<ballot>(?P<present>%\w+) = OpGroupNonUniformBallotBitExtract[^\n]*\n\s*)"
                          r"(?P<index>%\w+) = OpSelect %uint (?P=present) (?P<source>%\w+) %\w+(?=\n)",
                          r"\g<ballot>\g<index> = OpCopyObject %uint \g<source>", 2)

    observations = {
        str(width): cross.run(native, width)
        for width in (32, 64)
    }
    expected = cross.GPU_EXPECTED["cs_w64x_bpermute"]
    if any(words != expected for words in observations.values()):
        raise ValueError("upstream interpreter changed a bpermute positive control")
    wrong = cross.run(bad_base, 64)
    if wrong == expected:
        raise ValueError("upstream interpreter missed the wrong half-base control")

    def run_partial(assembly):
        return interpreter.run_workgroup(
            assembly, 40, 64,
            inputs_for=lambda i: {"%wg_id": (0, 0, 0), "%local_id": (i, 0, 0), "%sg_lane": i},
            push_constants=partial.VSHARP + [0] * 28, memory=partial.Heap())

    partial_words = partial.words(run_partial(small), len(partial.GPU_DUMPS["cs_w64x_partial"]))
    if partial_words != partial.GPU_DUMPS["cs_w64x_partial"]:
        raise ValueError("upstream interpreter changed the partial-wave positive control")
    try:
        run_partial(bad_fallback)
    except interpreter.UnsupportedConstruct as exc:
        if "undefined value" not in str(exc):
            raise
        missing_fallback = str(exc)
    else:
        raise ValueError("upstream interpreter missed the absent fallback control")

    output.mkdir(parents=True, exist_ok=True)
    cases = {}
    env = ["--target-env", "vulkan1.3"]
    suffix = ".exe" if os.name == "nt" else ""
    assemble = tools / f"spirv-as{suffix}"
    validate = tools / f"spirv-val{suffix}"
    for label, assembly in (
        ("bpermute", native), ("partial", small), ("wrong-half-base", bad_base), ("absent-fallback", bad_fallback),
    ):
        source = output / f"{label}.spvasm"
        binary = output / f"{label}.spv"
        source.write_text(assembly, encoding="utf-8", newline="\n")
        subprocess.run([str(assemble), *env, str(source), "-o", str(binary)], check=True)
        subprocess.run([str(validate), *env, str(binary)], check=True)
        cases[label] = {
            "assembly_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "validated_vulkan_1_3": True,
            **inspect(assembly),
        }
    for label, count in (("bpermute", 3), ("partial", 2), ("wrong-half-base", 3), ("absent-fallback", 0)):
        matches = [row for row in cases[label]["shuffles"] if row["status"] == "recognized"]
        if len(matches) != count:
            raise ValueError(f"expected {count} parsed translations in {label}, got {len(matches)}")
        usable64 = label != "wrong-half-base"
        for row in matches:
            if row["checks"]["64/superset"]["status"] != ("passes modeled domain" if usable64 else "refuted"):
                raise ValueError(f"unexpected modeled result for {label} {row['shuffle']}")
            if row["checks"]["32/superset"]["status"] != "passes modeled domain":
                raise ValueError(f"wrong result on aligned native32 for {label} {row['shuffle']}")

    report = {
        "continued_commit": head,
        "continued_fixture_and_translator_tree_clean": not source_status,
        "spirv_tools": subprocess.check_output([str(validate), "--version"], text=True).splitlines()[0],
        "upstream_interpreter": {
            "bpermute": observations, "partial64": partial_words, "wrong_half_base64": wrong,
            "absent_fallback64": missing_fallback,
        },
        "cases": cases,
    }
    (output / "continued-analysis.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--spirv-tools", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.checkout.resolve(), args.output.resolve(), args.spirv_tools.resolve())
    print(f"Continued {report['continued_commit']}, Vulkan 1.3 validator success across four modules.")
    for label, case in report["cases"].items():
        print(f"{label}: {sum(row['status'] == 'recognized' for row in case['shuffles'])}/{len(case['shuffles'])} shuffles modeled")


if __name__ == "__main__":
    main()
