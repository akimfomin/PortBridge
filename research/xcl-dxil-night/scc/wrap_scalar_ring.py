# SPDX-License-Identifier: GPL-2.0-only
"""Build synthetic console-format compute records for XCL's CPU-only CLI.

The container layout comes from XCL's existing synthetic `console_cs` fixture
at 20cf130, crates/xcl/tests/gpu_compute_e2e.rs. No assets are inputs.
"""

from pathlib import Path
import struct
import sys
import zlib


def words(*values):
    return struct.pack(f"<{len(values)}I", *values)


def compute_record(code):
    code_at = 0x308
    fssm = bytearray(code_at)
    fssm[:4] = b"FSSM"
    fssm[4:12] = words(0x101, code_at + len(code) - 0x10)
    struct.pack_into("<QQ", fssm, 0xC0, code_at - 0x10, len(code))
    struct.pack_into("<Q", fssm, 0x100, 0x0000_00C0_0002_0106)
    fssm[0x138:0x148] = words(0, 1, 1, 1)
    fssm.extend(code)
    zipped = zlib.compress(fssm)
    xbch = b"XBCH" + words(3, len(zipped), 0, len(fssm), 0) + zipped
    d = bytearray(words(5 << 16 | 0x66, 0, int.from_bytes(b"DXIL", "little"), 0x106, 0, 4))
    table = 0x18 + 12
    data_at = table + 2 * 12
    d.extend(b"XDAT" + words(2, table, 0x12, data_at, 16, 0x0D, data_at + 16, len(xbch)))
    d.extend(bytes([0x5A]) * 16 + xbch)
    d.extend(bytes(-len(d) % 4))
    d[16:20] = words(len(d) - 8)
    d.extend(b"NOBC")
    d[4:8] = words(len(d) // 4)
    return b"DXBC" + bytes(16) + words(1, 36 + 8 + len(d), 1, 36) + b"DXIL" + words(len(d)) + d


if __name__ == "__main__":
    source, destination = map(Path, sys.argv[1:])
    destination.mkdir(exist_ok=True)
    for raw in sorted(source.glob("*.rdna2")):
        record = compute_record(raw.read_bytes())
        (destination / f"{raw.stem}.bin").write_bytes(record)
