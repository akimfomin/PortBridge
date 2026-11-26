# SPDX-License-Identifier: MIT
"""Build published MiniEngine display filters with separate Vulkan descriptor bindings."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PIN = "68a2b1e97f71642924e74c7757ca21756ad221b5"
# Preselected before timing: largest ballot reduction in MiniEngine plus its
# linear-space sibling and another display filter that changes fewer ballots.
STAGES = (
    "BicubicUpsampleGammaPS",
    "BicubicUpsamplePS",
    "SharpeningUpsampleGammaPS",
    "PresentSDRPS",
    "BilinearUpsamplePS",
)


def build_shader(args, src, case, build_display):
    from open_pixel_census import command, hash_file, pixel_code, ps_config

    spv, elf, code = [case / n for n in ("source.spv", "shader.elf", "shader.rdna2")]
    compile_args = [
        args.dxc,
        "-spirv",
        "-fspv-target-env=vulkan1.2",
        "-fvk-b-shift",
        "16",
        "0",
        "-fvk-s-shift",
        "32",
        "0",
        "-fvk-u-shift",
        "48",
        "0",
        "-T",
        "ps_6_2",
        "-E",
        "main",
        "-O3",
        "-HV",
        "2021",
        "-D_GAMING_DESKTOP=1",
        "-Fo",
        spv,
        src.name,
    ]
    command(compile_args, cwd=src.parent)
    command([args.val, "--target-env", "vulkan1.2", spv])
    assembly = command([args.dis, spv])
    bindings = {
        n: int(b) for n, b in re.findall(r"OpDecorate %(\w+) Binding (\d+)", assembly)
    }
    sets = {
        n: int(s)
        for n, s in re.findall(r"OpDecorate %(\w+) DescriptorSet (\d+)", assembly)
    }
    slots = [(sets[n], b) for n, b in bindings.items()]
    if len(slots) != len(set(slots)):
        raise ValueError(f"Descriptor collision in {src.name}: {bindings}")
    (case / "source.spvasm").write_text(assembly, encoding="utf-8")
    dump = case / "pipeline"
    command(
        [
            args.llpc,
            "--gfxip=10.3.0",
            "--auto-layout-desc",
            "--enable-pipeline-dump",
            f"--pipeline-dump-dir={dump}",
            "--filetype=obj",
            "--shader-cache-mode=0",
            "-o",
            elf,
            f"{spv},main",
        ]
    )
    notes = command([args.readobj, "--notes", elf])
    (case / "pal.txt").write_text(notes, encoding="utf-8")
    code.write_bytes(pixel_code(elf.read_bytes()))
    native_data = {}
    if build_display:
        native, rootsig = case / "native.dxil", case / "present.rootsig"
        command(
            [
                args.dxc,
                "-T",
                "ps_6_6",
                "-E",
                "main",
                "-HV",
                "2021",
                "-O3",
                "-D_GAMING_DESKTOP=1",
                "-Fo",
                native,
                src.name,
            ],
            cwd=src.parent,
        )
        command([args.dxc, "-dumpbin", "-extractrootsignature", "-Fo", rootsig, native])

        native_data = {
            "native_dxil_sha256": hash_file(native),
            "rootsig_sha256": hash_file(rootsig),
        }
    return {
        "group": "miniengine-display" if build_display else "miniengine-corrected",
        "entry": "main",
        "source": src.relative_to(args.repo).as_posix(),
        "source_sha256": hash_file(src),
        "spirv_sha256": hash_file(spv),
        "bindings": bindings,
        **native_data,
        "rdna": {
            "bytes": code.stat().st_size,
            "sha256": hash_file(code),
            **ps_config(notes),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for a in ("repo", "corpus-tools", "dxc", "dis", "val", "llpc", "readobj", "out"):
        parser.add_argument("--" + a, type=lambda v: Path(v).resolve(), required=True)
    parser.add_argument(
        "--all-project-pixels",
        action="store_true",
        help="Extract all declared project pixel stages in their original order, without display-only native fixtures",
    )
    args = parser.parse_args()
    sys.path.insert(0, str(args.corpus_tools))
    from open_pixel_census import (
        LLPC,
        hash_file,
        sources,
        verify_source,
    )

    verify_source(args.repo, PIN)
    if hash_file(args.llpc) != LLPC:
        raise ValueError("Expected pinned AMD PAL compiler")
    args.out.mkdir(parents=True, exist_ok=False)

    if args.all_project_pixels:
        inputs = [
            path
            for group, _, path, _, _ in sources(args.repo, args.out)
            if group == "miniengine"
        ]
    else:
        inputs = [
            args.repo / "MiniEngine/Core/Shaders" / (name + ".hlsl") for name in STAGES
        ]
    rows = []
    for index, src in enumerate(inputs):
        case = args.out / f"{index:03d}"
        case.mkdir()
        try:
            rows.append(build_shader(args, src, case, not args.all_project_pixels))
        except (subprocess.SubprocessError, ValueError) as error:
            if not args.all_project_pixels:
                raise
            from open_pixel_census import error_text

            rows.append(
                {
                    "group": "miniengine-corrected",
                    "entry": "main",
                    "source": src.relative_to(args.repo).as_posix(),
                    "source_sha256": hash_file(src),
                    "error": {
                        "stage": "prepare",
                        "message": error_text(error, args.out.parent),
                    },
                }
            )
    manifest = {
        "source": {
            "repo": "microsoft/DirectX-Graphics-Samples",
            "commit": PIN,
            "license": "MIT",
        },
        "tool_hashes": {
            name: hash_file(getattr(args, name))
            for name in ("dxc", "dis", "val", "llpc", "readobj")
        },
        "observations": rows,
    }
    (args.out / "miniengine-display.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
