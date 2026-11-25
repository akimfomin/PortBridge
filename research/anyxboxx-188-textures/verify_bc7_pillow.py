# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare actual AnyXboxX surfaces with Pillow 13's independent BC7 decoder."""
import argparse
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import random
import struct
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image, __version__ as pillow_version

ROOT = Path(__file__).resolve().parent


def dds(width, height, blocks):
    # DDS_HEADER, DXGI_FORMAT_BC7_UNORM and DDS_DIMENSION_TEXTURE2D.
    header = struct.pack("<7I", 124, 0x81007, height, width, len(blocks), 0, 1)
    pixel_format = struct.pack("<II4s5I", 32, 4, b"DX10", 0, 0, 0, 0, 0)
    caps = struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    dx10 = struct.pack("<5I", 98, 3, 0, 1, 0)
    return b"DDS " + header + bytes(44) + pixel_format + caps + dx10 + blocks


def random_block(generator, mode):
    block = bytearray(generator.randbytes(16))
    mode_bit = 1 << mode
    block[0] = block[0] & ~(mode_bit - 1) | mode_bit
    return bytes(block)


def make_cases():
    generator = random.Random(20261125)
    for mode in range(8):
        for _ in range(256):
            yield f"mode-{mode}", 4, 4, random_block(generator, mode)
    for width in range(1, 20):
        for height in range(1, 20):
            count = ((width + 3) // 4) * ((height + 3) // 4)
            blocks = b"".join(random_block(generator, index % 8) for index in range(count))
            yield "mixed-crop", width, height, blocks


def rust_output(folder, label, corpus, compiler, linker):
    library = corpus.parent / f"lib{label}-anyxboxx-texture.rlib"
    extension = ".exe" if os.name == "nt" else ""
    executable = corpus.parent / f"{label}-bc7-surface-oracle{extension}"
    common = [compiler, "--edition=2021", "-O"]
    if linker:
        common += ["-C", f"linker={linker}"]
    subprocess.run([*common, "--crate-name=anyxboxx_texture", "--crate-type=lib",
                    str(folder / "rust" / "anyxboxx-texture" / "src" / "lib.rs"), "-o", str(library)],
                   check=True, timeout=60)
    subprocess.run([*common, str(ROOT / "bc7_surface_oracle.rs"), "--extern",
                    f"anyxboxx_texture={library}", "-o", str(executable)],
                   check=True, timeout=60)
    return subprocess.run([str(executable), str(corpus)], check=True, capture_output=True, timeout=45).stdout


def verify(args, scratch):
    cases = list(make_cases())
    corpus = scratch / "bc7-synthetic-corpus.bin"
    corpus.write_bytes(b"".join(struct.pack("<III", w, h, len(data)) + data for _, w, h, data in cases))
    expected = bytearray()
    groups = {}
    for label, width, height, blocks in cases:
        with Image.open(io.BytesIO(dds(width, height, blocks))) as image:
            assert image.mode == "RGBA" and image.size == (width, height)
            expected.extend(image.tobytes())
        groups[label] = groups.get(label, 0) + 1
    result = {"pillow": pillow_version, "cases": groups, "texels": len(expected) // 4,
              "corpus_sha256": sha256(corpus.read_bytes()).hexdigest(), "oracle_sha256": sha256(expected).hexdigest(),
              "arms": {}}
    for label, folder in (("upstream", args.upstream), ("candidate", args.candidate)):
        actual = rust_output(folder, label, corpus, args.rustc, args.linker)
        result["arms"][label] = {"sha256": sha256(actual).hexdigest(), "bytes": len(actual),
                                 "matches_oracle": actual == expected,
                                 "sha": subprocess.check_output(["git", "-C", str(folder), "rev-parse", "HEAD"],
                                                                encoding="utf-8").strip()}
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8",
                                                     newline="\n")
    print(json.dumps(result, indent=2))
    return 0 if all(arm["matches_oracle"] for arm in result["arms"].values()) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--rustc", default="rustc")
    parser.add_argument("--linker")
    parser.add_argument("--report", type=Path, default=Path("bc7-pillow-verification.json"))
    args = parser.parse_args()
    with TemporaryDirectory() as scratch:
        return verify(args, Path(scratch))


if __name__ == "__main__":
    raise SystemExit(main())
