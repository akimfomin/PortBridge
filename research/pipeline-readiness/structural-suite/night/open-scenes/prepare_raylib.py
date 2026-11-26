# SPDX-License-Identifier: MIT
"""Prepare licensed raylib procedural scenes with dynamic application controls."""
import argparse
from pathlib import Path
import re
import json
import sys

PIN = "7aeef5775435ed9f57890bf3c1b53279f6b0866a"
# Distinct real-time applications with bounded loops, no textures and one render target.
# Offsets obey the GLSL push-constant block layout, in bytes.
CASES = {
    "raymarching": [("viewEye", "vec3", 0), ("viewCenter", "vec3", 16),
                    ("runTime", "float", 28), ("resolution", "vec2", 32)],
    "julia_set": [("c", "vec2", 0), ("offset", "vec2", 8), ("zoom", "float", 16)],
    "mandelbrot_set": [("offset", "vec2", 0), ("zoom", "float", 8), ("maxIterations", "int", 12)],
}


def adapt(source, fields):
    # Retain all operations of the source shader. The original application's loose
    # OpenGL uniforms are passed in one explicitly laid out Vulkan push-constant block.
    body = source.replace("#version 330", "#version 450", 1)
    for i, (ty, var) in enumerate((("vec2", "fragTexCoord"), ("vec4", "fragColor"))):
        body, n = re.subn(rf"^in {ty} {var};", f"layout(location={i}) in {ty} {var};", body, flags=re.M)
        if n != 1:
            raise ValueError("Unexpected GLSL varying declaration")
    body, n = re.subn(r"^out vec4 finalColor;", "layout(location=0) out vec4 finalColor;", body, flags=re.M)
    if n != 1:
        raise ValueError("Unexpected GLSL color output")
    block = ["layout(push_constant, std430) uniform Scene {"]
    for var, ty, offset in fields:
        block.append(f"    layout(offset={offset}) {ty} {var};")
        body, n = re.subn(rf"^uniform {ty} {var};", "", body, flags=re.M)
        if n != 1:
            raise ValueError(f"Unexpected GLSL uniform {var}")
    block.append("};")
    body = body.replace("#version 450", "#version 450\n" + "\n".join(block), 1)
    # GL's gl_FragCoord origin is at the bottom; D3D/Vulkan pixel rows start at
    # the top. Express raylib's original camera in the new coordinate system.
    if "gl_FragCoord" in body:
        body = body.replace("gl_FragCoord.xy", "vec2(gl_FragCoord.x, resolution.y-gl_FragCoord.y)")
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("repo", "corpus-tools", "glslang", "val", "llpc", "readobj", "out"):
        parser.add_argument("--" + arg, required=True, type=lambda s: Path(s).resolve())
    parser.add_argument("--wave", type=int, choices=(32, 64), help="Override the PAL compiler's native wave size")
    args = parser.parse_args()
    sys.path.insert(0, str(args.corpus_tools))
    from open_pixel_census import command, hash_file, ps_config, pixel_code, verify_source, LLPC
    verify_source(args.repo, PIN)
    if hash_file(args.llpc) != LLPC:
        raise ValueError("amdllpc must match the RGA 2.12 corpus pipeline")
    args.out.mkdir(parents=True, exist_ok=False)
    rows = []
    for i, (name, fields) in enumerate(CASES.items()):
        path = args.repo / f"examples/shaders/resources/shaders/glsl330/{name}.fs"
        case = args.out / f"{i:03d}"
        case.mkdir()
        source, spv, elf, code = [case / n for n in ("scene.frag", "source.spv", "shader.elf", "shader.rdna2")]
        source.write_text(adapt(path.read_text(encoding="utf-8"), fields), encoding="utf-8")
        command([args.glslang, "-V", "--target-env", "vulkan1.2", "-S", "frag", "-e", "main", "-o", spv, source])
        command([args.val, "--target-env", "vulkan1.2", spv])
        pal_cmd = [args.llpc, "--gfxip=10.3.0", "--filetype=obj", "--shader-cache-mode=0"]
        dump = case / "pipeline"
        capture = ["--enable-pipeline-dump", f"--pipeline-dump-dir={dump}"] if args.wave else []
        command([*pal_cmd, "--auto-layout-desc", *capture, "-o", elf, f"{spv},main"])
        if args.wave:
            # The standalone compiler prefers Wave64 for pixel stages even when the
            # device default is Wave32. Preserve its complete generated PAL layout
            # and alter only the numeric per-stage tuning field in its pipeline file.
            original_pipe, = dump.glob("*.pipe")
            desc = original_pipe.read_text(encoding="utf-8")
            desc, n = re.subn(r"(?m)^options\.waveSize = 0$", f"options.waveSize = {args.wave}", desc)
            if n != 1:
                raise ValueError("Expected exactly one override in the standalone fragment stage")
            requested = dump / "requested.pipe"
            requested.write_text(desc, encoding="utf-8")
            command([*pal_cmd, "-o", elf, requested])
        notes = command([args.readobj, "--notes", elf])
        (case / "pal.txt").write_text(notes, encoding="utf-8")
        code.write_bytes(pixel_code(elf.read_bytes()))
        abi = ps_config(notes)
        if args.wave and abi["wave"] != args.wave:
            raise ValueError(f"PAL wave size differs from request: {abi['wave']}")
        rows.append({"group": "raylib-procedural", "entry": "main", "source": path.relative_to(args.repo).as_posix(),
                     "source_sha256": hash_file(path), "vulkan_glsl_sha256": hash_file(source),
                     "spirv_sha256": hash_file(spv), "elf_sha256": hash_file(elf), "fields": fields,
                     "rdna": {"bytes": code.stat().st_size, "sha256": hash_file(code), **abi}})
    result = {"source": {"repo": "raysan5/raylib", "commit": PIN,
                         "licenses": {"raymarching": "MIT, Inigo Quilez", "repository": "Zlib"}},
              "requested_wave": args.wave,
              "tool_hashes": {s: hash_file(getattr(args, s)) for s in ("glslang", "val", "llpc", "readobj")},
              "observations": rows}
    (args.out / "raylib-pixels.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
