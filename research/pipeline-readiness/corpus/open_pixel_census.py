# SPDX-License-Identifier: MIT
"""Source-licensed external Vulkan fragment shader shape probe for XCL."""
import argparse
from collections import Counter
from pathlib import Path
import json
import os
import re
import struct
import subprocess
from xml.etree import ElementTree

from fixture_census import command, describe, hash_file

MINI = "68a2b1e97f71642924e74c7757ca21756ad221b5"
NAGA = "c76dea031c688ecef0050dbf60506fff128fb23f"
XCL = "8e4c4a63143702d5e5da79484273143e0b76eb92"
LLPC = "928501ebdafcb4c1e20af5c39fed45cd69a402aaa73be453d2d6de50eae9215a"
ELF_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
SECTION = struct.Struct("<IIQQQQIIQQ")
SYMBOL = struct.Struct("<IBBHQQ")
ATTR = ("persp_sample", "persp_center", "persp_centroid", "persp_pull_model",
        "linear_sample", "linear_center", "linear_centroid", "line_stipple_tex",
        "pos_x_float", "pos_y_float", "pos_z_float", "pos_w_float",
        "front_face", "ancillary", "sample_coverage", "pos_fixed_pt")


def verify_source(root, head):
    if command(["git", "rev-parse", "HEAD"], cwd=root).strip() != head:
        raise ValueError(f"{root}: wrong checkout")
    if command(["git", "status", "--porcelain"], cwd=root).strip():
        raise ValueError(f"{root}: checkout must be clean")


def sources(mini, naga):
    xml = mini / "MiniEngine/Core/Core.vcxproj"
    m = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
    for row in ElementTree.parse(xml).findall(".//m:FxCompile[@Include]", m):
        if row.findtext("m:ShaderType", "", m) == "Pixel":
            yield "miniengine", mini, xml.parent / row.get("Include").replace("\\", "/"), "main", None
    for path in sorted((naga / "naga/tests/out/spv").glob("*.spvasm")):
        source = path.read_text(encoding="utf-8")
        entries = re.findall(r'^ *OpEntryPoint Fragment %\S+ "([^"]+)"', source, re.M)
        if entries:
            version = re.search(r"^; Version: (\d+\.\d+)", source, re.M).group(1)
            for entry in entries:
                yield "naga", naga, path, entry, version


def slice_elf(data, off, size):
    if off < 0 or not size >= 0 or off + size > len(data):
        raise ValueError("ELF slice outside file")
    return data[off:off + size]


def pixel_code(data):
    h = ELF_HEADER.unpack_from(data)
    if (h[0][:8] != b"\x7fELF\x02\x01\x01\x41" or h[1:3] != (1, 224)
            or h[7] & 0xFF != 0x36 or h[-3] != SECTION.size or not 1 <= h[-2] <= 128):
        raise ValueError("Expected relocatable little-endian AMD PAL gfx1030 ELF")
    sections = list(SECTION.iter_unpack(slice_elf(data, h[6], h[-2] * SECTION.size)))

    def contents(section):
        return slice_elf(data, section[4], section[5])

    def name(table, start):
        return table[start:table.index(b"\0", start)].decode("ascii")

    section_names = contents(sections[h[-1]])
    text_index, = [i for i, s in enumerate(sections) if name(section_names, s[0]) == ".text"]
    text = contents(sections[text_index])
    symbols, = [s for s in sections if s[1] == 2]
    if symbols[9] != SYMBOL.size or not sections[text_index][2] & 4:
        raise ValueError("Expected executable .text and an ordinary ELF symbol table")
    strings = contents(sections[symbols[6]])
    entries = [symbol for symbol in SYMBOL.iter_unpack(contents(symbols))
               if name(strings, symbol[0]) == "_amdgpu_ps_main"]
    if len(entries) != 1:
        raise ValueError("Expected exactly one _amdgpu_ps_main")
    _, info, _, section, start, size = entries[0]
    if info & 15 != 2 or section != text_index or not size or (start | size) & 3:
        raise ValueError("Malformed pixel entry symbol")
    # Only fully linked instructions. PAL runtime user data are a separate ABI issue.
    for s in sections:
        if s[1] in (4, 9, 20) and s[7] == text_index and s[5] > 0:
            fmt = {4: "<QQq", 9: "<QQ"}.get(s[1])
            if fmt is None or s[9] != struct.calcsize(fmt):
                raise ValueError("Unrecognized .text relocation format")
            if any(start <= record[0] < start + size for record in struct.iter_unpack(fmt, contents(s))):
                raise ValueError("Pixel entry requires .text relocation")
    return slice_elf(text, start, size)


def ps_config(notes):
    def read(name, values, text=notes):
        field = re.search(rf"^\s*\.{name}:\s*({values})\s*$", text, re.M)
        if field is None:
            raise ValueError(f"Missing PAL metadata field {name}")
        return field.group(1)

    ena = re.search(r"(?ms)^      \.spi_ps_input_ena:\n((?:        [^\n]+\n)+)", notes)
    if ena is None:
        raise ValueError("Missing SPI_PS_INPUT_ENA in PAL metadata")
    input_ena = sum(1 << bit for bit, key in enumerate(ATTR)
                    if read(key + "_ena", "true|false", ena.group(1)) == "true")
    color = sum(1 << int(index) for index, fmt in re.findall(
        r"^\s*\.col_([0-7])_export_format:\s*(\d+)\s*$", notes, re.M
    ) if int(fmt))
    z_enabled = read("z_export_enable", "[01]|true|false") in {"1", "true"}
    depth = int(read("conservative_z_export", "[012]")) if z_enabled else -1
    return {
        "wave": int(read("wavefront_size", "32|64")), "spi_ps_input_ena": input_ena,
        "interpolants": int(read("num_interps", r"\d+")), "color_mask": color, "depth_mode": depth,
    }


def error_text(error, workspace):
    if isinstance(error, subprocess.CalledProcessError):
        return f"exit {error.returncode}: {(error.stderr or error.stdout).strip()}".replace(str(workspace), "<work>")[:1200]
    return str(error).replace(str(workspace), "<work>")[:1200]


def run_shader(args, case, directory):
    group, root, path, entry, version = case
    row = {"group": group, "source": path.relative_to(root).as_posix(), "entry": entry,
           "source_sha256": hash_file(path)}
    spv = directory / "source.spv"
    elf = directory / "shader.elf"
    rdna = directory / "shader.rdna2"
    stage = "spirv"
    try:
        if group == "miniengine":
            command([args.dxc, "-spirv", "-fspv-target-env=vulkan1.2", "-fvk-auto-shift-bindings",
                     "-T", "ps_6_2", "-E", entry, "-O3", "-HV", "2021", "-D_GAMING_DESKTOP=1",
                     "-Fo", spv, path.name], cwd=path.parent)
        else:
            command([args.asm, "--target-env", f"spv{version}", path, "-o", spv])
        command([args.val, "--target-env", "vulkan1.2", spv])
        row["spirv"] = {"bytes": spv.stat().st_size, "sha256": hash_file(spv)}
        stage = "amdllpc"
        command([args.llpc, "--gfxip=10.3.0", "--auto-layout-desc", "--filetype=obj",
                 "--shader-cache-mode=0", "-o", elf, f"{spv},{entry}"])
        stage = "extract"
        elf_bytes = elf.read_bytes()
        notes = command([args.readobj, "--notes", elf])
        config = ps_config(notes)
        (directory / "pal.txt").write_text(notes, encoding="utf-8")
        rdna.write_bytes(pixel_code(elf_bytes))
        row["rdna"] = {"bytes": rdna.stat().st_size, "sha256": hash_file(rdna), **config}
        row["pairs"] = {}
        for windows in (1, 4):
            pair = {}
            row["pairs"][str(windows)] = pair
            for arm in ("off", "on"):
                env = {k: v for k, v in os.environ.items() if not k.startswith("XCL_")}
                env["XCL_DXC_DIR"] = str(args.dxc.parent)
                if arm == "off":
                    env["XCL_DXIL_NO_OPT"] = "read-guards"
                target = directory / f"{windows}w-{arm}.dxil"
                try:
                    command([args.xcl, rdna, target, *map(str, config.values()), f"heap-{windows}"], env=env)
                    pair[arm] = describe(target, args.dxc, args.dxv)
                except (OSError, subprocess.SubprocessError, ValueError) as error:
                    pair[arm] = {"error": error_text(error, directory.parent.parent)}
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        row["error"] = {"stage": stage, "message": error_text(error, directory.parent.parent)}
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("mini", "naga", "dxc", "dxv", "asm", "val", "llpc", "readobj", "xcl", "out"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.resolve())
    args.out.mkdir()
    if hash_file(args.llpc) != LLPC:
        raise ValueError("Expected the amdllpc build bundled with RGA 2.12")
    verify_source(args.mini, MINI)
    verify_source(args.naga, NAGA)
    inputs = list(sources(args.mini, args.naga))
    rows = []
    for index, case in enumerate(inputs[:args.limit]):
        case_directory = args.out / f"{index:03d}"
        case_directory.mkdir()
        rows.append(run_shader(args, case, case_directory))
    manifest = {
        "sources": {
            "miniengine": {"repo": "microsoft/DirectX-Graphics-Samples", "commit": MINI, "license": "MIT"},
            "naga": {"repo": "gfx-rs/wgpu", "commit": NAGA, "license": "MIT OR Apache-2.0"},
        },
        "tools_sha256": {name: hash_file(getattr(args, name))
                         for name in ("dxc", "dxv", "asm", "val", "llpc", "readobj", "xcl")},
        "xcl": XCL,
        "scope": "CPU-only XCL DXIL structural comparison. AMD PAL shaders have a synthetic XCL graphics signature; Vulkan resource bindings and output equivalence are outside this probe.",
        "observations": rows,
    }
    (args.out / "open-pixel.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(Counter((row["group"], row.get("error", {}).get("stage", "rdna")) for row in rows))
    for windows in ("1", "4"):
        counts = Counter()
        for row in rows:
            pair = row.get("pairs", {}).get(windows)
            if pair:
                desc = "failed" if any("error" in arm for arm in pair.values()) else (
                    "different" if pair["on"]["sha256"] != pair["off"]["sha256"] else "identical")
                counts[(row["group"], desc)] += 1
        print(f"{windows} windows: {counts}")


if __name__ == "__main__":
    main()
