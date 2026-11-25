"""Generate a single RDNA2 byte-pack dispatch, or verify a saved native readback."""

import argparse
from hashlib import sha256
from pathlib import Path
import struct
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "native")
parser.add_argument("--verify", type=Path, help="check existing native output; does not launch D3D12")
args = parser.parse_args()

if args.verify is not None:
    expected = (args.out / "pack.expected.bin").read_bytes()
    actual = args.verify.read_bytes()
    if actual != expected:
        if len(actual) != len(expected):
            raise SystemExit(f"Size mismatch: expected {len(expected)}, got {len(actual)}")
        at = next(index for index, (left, right) in enumerate(zip(expected, actual)) if left != right)
        raise SystemExit(f"Byte mismatch at {at:#x}: expected {expected[at]:#04x}, got {actual[at]:#04x}")
    print(f"native_pack_words=32 whole_buffer_sha256={sha256(actual).hexdigest()}")
    raise SystemExit(0)

sys.path[:0] = [str(args.source.resolve() / "PrototypeScarlett"), str(args.source.resolve() / "tests")]
from emu import rdna2_exec, rdna2_hlsl
from test_rdna2_exec import EXEC_LO, V, VCC_LO, const, program, sop1, vop2, vop3, vopc
from test_rdna2_exec_memory import INPUT, OUTPUT, global_

cases = [
    (0x0000_0000, 0), (0x8000_0000, 0), (0x0000_0001, 0),
    (0x3EFF_FFFF, 0), (0x3F00_0000, 0), (0x3F00_0001, 1),
    (0x3FC0_0000, 2), (0x4020_0000, 2), (0x4060_0000, 4),
    (0x437E_8000, 254), (0x437F_8000, 255), (0x4380_0000, 255),
    (0x7F80_0000, 255), (0xFF80_0000, 0), (0x7FC0_0011, 0), (0x7F80_0001, 0),
] * 2
slots = [0, 1, 2, 3, 4, 5, 6, 0xFFFF_FFFF] * 4
old_word = 0xAABB_CCDD
memory = bytearray(OUTPUT + 32 * 4)
struct.pack_into("<32I", memory, INPUT, *(bits for bits, _ in cases))
struct.pack_into("<32I", memory, INPUT + 128, *slots)
struct.pack_into("<32I", memory, INPUT + 256, *([old_word] * 32))
code = program(
    vop2("v_lshlrev_b32", 31, const(2), 0),
    *global_("global_load_dword", addr=31, vdst=1, saddr=0),
    *global_("global_load_dword", addr=31, vdst=2, saddr=0, offset=128),
    *global_("global_load_dword", addr=31, vdst=3, saddr=0, offset=256),
    vopc("v_cmp_gt_u32", const(24), 0),
    sop1("s_and_saveexec_b32", 5, VCC_LO),
    *vop3("v_cvt_pk_u8_f32", 3, V + 1, V + 2, V + 3),
    sop1("s_mov_b32", EXEC_LO, 5),
    *global_("global_store_dword", addr=31, data=3, saddr=2),
)
sgprs = {0: INPUT, 2: OUTPUT}
hlsl = rdna2_hlsl.translate(code, sgprs)
expected = memory.copy()
for lane, ((_, byte), slot) in enumerate(zip(cases, slots)):
    shift = 8 * (slot % 4)
    value = (old_word & ~(0xFF << shift)) | (byte << shift) if lane < 24 else old_word
    struct.pack_into("<I", expected, OUTPUT + lane * 4, value)

wave = rdna2_exec.Wave()
wave.memory.write(0, memory)
for index, address in sgprs.items():
    wave.s[index] = address
rdna2_exec.run(code, wave)
assert wave.memory.read(0, len(expected)) == expected, "reference interpreter disagrees with measured values"
args.out.mkdir(parents=True, exist_ok=True)
(args.out / "pack.hlsl").write_text(hlsl, encoding="utf-8")
(args.out / "pack.in.bin").write_bytes(memory)
(args.out / "pack.expected.bin").write_bytes(expected)
print("emitted one 32-lane compute group, with 24 active packed words and 8 unchanged words")

