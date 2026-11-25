# SPDX-License-Identifier: GPL-3.0-or-later
"""Reconstruct the exact metadata-side slice from the pinned source allowlist."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
PIN = "1ae8ad326ef6b4fe6e5ac1c5555079fafb78575a"
SLICE = "71967c898ed06baee331c12a3dd55464ce90ac4cfef5a38cf1bb746c11bc6a5d"
FIXTURE = "78221f38535e424ba95a0e06407af18edf06524a125482d95905ef1cc4695c2d"
SHADER = "50c440b71ba35b492017106484f19bfe31ef3d8677cddaef8b80c50e3f49cf66"


def function(source, name):
    start, = re.finditer(rf"^( *)(?:pub\(crate\) )?fn {name}\(", source, re.MULTILINE)
    end = re.search(rf"^{start[1]}}}[ \t]*$", source[start.end():], re.MULTILINE)
    return source[start.start():start.end() + end.end()] + "\n"


def chunk(source, start, end):
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


def files():
    spec = json.loads((ROOT / "source-manifest.json").read_text(encoding="utf-8"))
    if spec["revision"] != PIN or spec["extraction_sha256"] != SLICE:
        raise ValueError("unexpected source manifest revision")
    root = ROOT / "upstream"
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if len(actual) != 13 or actual != set(spec["files"]):
        raise ValueError("the upstream files differ from the source allowlist")
    payload = {}
    for name, expected in spec["files"].items():
        data = (root / name).read_bytes()
        if sha256(data).hexdigest() != expected:
            raise ValueError(f"pinned upstream source changed: {name}")
        payload[name] = data.decode("utf-8").replace("\r\n", "\n")
    for name, expected in (("fixture.rs", FIXTURE), ("read_metadata.hlsl", SHADER)):
        if sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"pinned fixture source changed: {name}")
    return payload


def extract():
    found = files()
    gpu = "crates/victory-gpu/src/"
    emit = "crates/victory-shader/src/emit/"
    guest, table, host, draw = (found[gpu + path] for path in
                               ("descriptor.rs", "descriptor/host.rs", "host.rs", "draw.rs"))
    lower, shader = (found[emit + path] for path in ("lower.rs", "shader.rs"))
    if ("pub const MEMORY_SPACE: u32 = 2;" not in shader or
        "SetComputeRootShaderResourceView(param, gpu)" not in draw or
        "let row = self.s.m.select(c, valid, row, one);" not in lower or
        "let valid = self.s.m.cmp(c, pred::IULT, index, slots);" not in lower):
        raise ValueError("upstream producer/consumer ABI differs from the fixture")
    records = chunk(guest, "#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]\npub(crate) enum View",
                    "/// The title released")
    records += function(guest, "view_at")
    slots = chunk(table, "struct SlotRecords {", "/// Host heaps' GPU ranges")
    methods = "\n".join(function(table, name) for name in ("view_addresses", "note_address", "mirror"))
    methods = slots + "impl HostHeap {\n" + methods + "}\n"
    functions = "\n".join(function(table, name) for name in (
        "srv_desc", "uav_desc", "element_size", "write_address", "view_size_words",
        "buffer_range", "unordered_range", "is_placed_texture",
    ))
    upload = "impl Host {\n" + function(host, "upload_buffer") + "}\n"
    result = (records + "\n" + methods + "\n" + functions + "\n" + upload).encode("utf-8")
    if sha256(result).hexdigest() != SLICE:
        raise ValueError("reconstructed metadata source differs from the tested extraction")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional new file for the verified source slice")
    args = parser.parse_args()
    result = extract()
    if args.output:
        with args.output.open("xb") as output:
            output.write(result)
    print(f"{PIN} / {len(result)} exact source bytes / SHA-256 {SLICE}")
