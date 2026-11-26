# SPDX-License-Identifier: MIT
"""Wrap a licensed guest pixel program in XCL's synthetic test container.

The guest ISA, signatures and PAL attributes must belong to the same authorized
case. This fixture uses the publicly documented XCL test layout.
"""
import argparse
import hashlib
from pathlib import Path
import struct
import zlib


def u32(*words):
    return struct.pack(f"<{len(words)}I", *words)


def signature_chunks(dxbc):
    if dxbc[:4] != b"DXBC":
        raise ValueError("signature source is not a DXBC container")
    chunks = {}
    (count,) = struct.unpack_from("<I", dxbc, 28)
    for index in range(count):
        (offset,) = struct.unpack_from("<I", dxbc, 32 + 4 * index)
        tag, size = struct.unpack_from("<4sI", dxbc, offset)
        end = offset + 8 + size
        if end > len(dxbc):
            raise ValueError("truncated signature source")
        chunks[tag] = dxbc[offset + 8:end]
    return chunks[b"ISG1"], chunks[b"OSG1"]


def pad_to_word(data):
    data.extend(bytes(-len(data) % 4))


def container(chunks):
    result = bytearray(32 + 4 * len(chunks))
    result[:4] = b"DXBC"
    struct.pack_into("<I", result, 20, 1)
    struct.pack_into("<I", result, 28, len(chunks))
    for index, (tag, data) in enumerate(chunks):
        struct.pack_into("<I", result, 32 + 4 * index, len(result))
        result.extend(tag + u32(len(data)) + data)
        pad_to_word(result)
    struct.pack_into("<I", result, 24, len(result))
    return result


def wrap(isa, reference, wave, input_ena):
    if not isa or len(isa) % 4:
        raise ValueError("guest ISA must be a non-empty sequence of DWORDs")
    code_offset = 0x308
    guest = bytearray(code_offset)
    guest[:4] = b"FSSM"
    struct.pack_into("<I", guest, 4, 0x101)
    struct.pack_into("<QQ", guest, 0xC0, code_offset - 16, len(isa))
    struct.pack_into("<I", guest, 0xD4, 0x20 if wave == 32 else 0)
    struct.pack_into("<Q", guest, 0x100, 0x000000C000020105)  # hardware pixel stage
    struct.pack_into("<I", guest, 0x248, input_ena)
    guest.extend(isa)
    struct.pack_into("<I", guest, 8, len(guest) - 16)

    compressed = zlib.compress(guest, 6)
    xbc = b"XBCH" + u32(3, len(compressed), 0, len(guest), 0) + compressed
    table_offset = 0x18 + 12
    data_offset = table_offset + 2 * 12
    part = bytearray(u32(0x66, 0, int.from_bytes(b"DXIL", "little"), 0x106, 0, 4) + b"XDAT")
    part.extend(u32(2, table_offset, 0x12, data_offset, 16, 0xD, data_offset + 16, len(xbc)))
    part.extend(hashlib.sha256(isa).digest()[:16])
    part.extend(xbc)
    pad_to_word(part)
    no_bitcode_offset = len(part)
    part.extend(b"NOBC")
    struct.pack_into("<I", part, 4, len(part) // 4)
    struct.pack_into("<I", part, 16, no_bitcode_offset - 8)
    inputs, outputs = signature_chunks(reference)
    return container([(b"ISG1", inputs), (b"OSG1", outputs), (b"DXIL", part)])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("isa", type=Path)
    parser.add_argument("signature_source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--wave", type=int, choices=(32, 64), required=True)
    parser.add_argument("--ena", type=int, required=True)
    args = parser.parse_args()
    args.output.write_bytes(wrap(args.isa.read_bytes(), args.signature_source.read_bytes(), args.wave, args.ena))
