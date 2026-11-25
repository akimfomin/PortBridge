"""Write a C++ array for the source-built DXIL used by the guarded fixture."""
import argparse
from pathlib import Path


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("dxil", type=Path)
parser.add_argument("header", type=Path)
args = parser.parse_args()
blob = args.dxil.read_bytes()
lines = [
    "inline constexpr unsigned char native_cast_dxil[] = {",
    *["    " + ", ".join(f"0x{byte:02x}" for byte in blob[i:i + 16]) + "," for i in range(0, len(blob), 16)],
    "};",
    "",
]
args.header.write_text("\n".join(lines), encoding="ascii")
