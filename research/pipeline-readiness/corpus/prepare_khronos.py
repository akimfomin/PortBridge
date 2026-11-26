
"""Prepare a second licensed pixel corpus using Khronos GLSL examples."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from subprocess import SubprocessError
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "xcl-readguard-corpus-artifacts"))
from open_pixel_census import command, error_text, hash_file, pixel_code, ps_config, verify_source

PIN="979aefaa5f2f4bd30efe035ca5a39444cc24ab9f"
parser=argparse.ArgumentParser(description=__doc__)
for name in ("repo", "glslang", "val", "llpc", "readobj", "out"):
    parser.add_argument("--"+name, type=lambda v: Path(v).resolve(), required=True)
args=parser.parse_args()
verify_source(args.repo, PIN)
args.out.mkdir()
rows=[]
for i, source in enumerate(sorted((args.repo / "shaders").rglob("*.frag"))):
    case=args.out / f"{i:03d}"
    case.mkdir()
    spv, elf, rdna=(case / name for name in ("source.spv","shader.elf","shader.rdna2"))
    row={"group":"khronos-vulkan-samples","source":source.relative_to(args.repo).as_posix(),"source_sha256":hash_file(source),"entry":"main"}
    stage="glslang"
    try:
        command([args.glslang,"-V","--target-env","vulkan1.2","-S","frag","-e","main","-o",spv,source],cwd=source.parent)
        stage="spirv-val"
        command([args.val,"--target-env","vulkan1.2",spv])
        row["spirv"]={"sha256":hash_file(spv),"bytes":spv.stat().st_size}
        stage="amdllpc"
        command([args.llpc,"--gfxip=10.3.0","--auto-layout-desc","--filetype=obj","--shader-cache-mode=0","-o",elf,f"{spv},main"])
        stage="elf-extract"
        notes=command([args.readobj,"--notes",elf])
        (case/"pal.txt").write_text(notes,encoding="utf-8")
        config=ps_config(notes)
        rdna.write_bytes(pixel_code(elf.read_bytes()))
        row["rdna"]={"sha256":hash_file(rdna),"bytes":rdna.stat().st_size,**config}
    except (OSError,SubprocessError,ValueError) as error:
        row["error"]={"stage":stage,"message":error_text(error,args.out.parent)}
    rows.append(row)
summary={"source":{"repo":"KhronosGroup/Vulkan-Samples","commit":PIN,"license":"Apache-2.0"},
         "scope":"All shader-tree .frag entries at the pin. SPIR-V 1.5 target Vulkan 1.2 validation and AMD PAL gfx1030 standalone fragment compilation. Outputs used for XCL structural measurements only.",
         "tools_sha256":{name:hash_file(getattr(args,name)) for name in ("glslang","val","llpc","readobj")},
         "observations":rows}
(args.out/"khronos-fragment-prep.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
print(Counter(row.get("error",{}).get("stage","rdna") for row in rows))
