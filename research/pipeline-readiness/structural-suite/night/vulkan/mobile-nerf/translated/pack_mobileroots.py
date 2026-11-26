# SPDX-License-Identifier: MIT
"""Pack the same small XCL guest memory used by the D3D12 fixture for a BDA receiver."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import struct

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture",type=Path)
    args=parser.parse_args()
    folder=args.fixture
    receipt=json.loads((folder/"manifest.json").read_bytes())
    width,height=receipt["width"],receipt["height"]
    if not 8<=width<=640 or not 8<=height<=360:raise ValueError("Unexpected extent")
    weights=(folder/"weights.bin").read_bytes()
    if len(weights)!=4*532*4 or sha256(weights).hexdigest()!=receipt["sha256"]["weights.bin"]:
        raise ValueError("Weight file differs from the fixture")
    # u0 is the 128-DWORD guest SGPR buffer. Each of u2/u3/u4/u5 points
    # at one 16 KiB slice, and the test accesses only the first.
    scalars=[0]*128
    scalars[1]=64*4
    scalars[112]=4
    mem=bytearray(4*4096*4)
    for i,format_code in enumerate((77,77,77,20)):
        w=width-1;h=height-1
        words=(i*2,(format_code<<20) | ((w & 3)<<30),(w>>2) | (h<<14),
               0xFAC | (9<<28),0,0,0,0)
        struct.pack_into("<8I",mem,(64+64+i*8)*4,*words)
    for i in range(4):
        pos=512+i*532
        start=i*532*4
        mem[pos*4:(pos+532)*4]=weights[start:start+532*4]
        struct.pack_into("<4I",mem,(64+4*i)*4,pos*4,4,532*4,
                         0xFAC | (77<<12) | (1<<24) | (3<<28))
    sgprs=struct.pack("<128I",*scalars)
    outputs={"sgprs.bin":sgprs,"guest_mem.bin":mem}
    for name,buf in outputs.items():(folder/name).write_bytes(buf)
    (folder/"root-layout.json").write_text(json.dumps({
        "u0":{"file":"sgprs.bin","offset_bytes":0,"bytes":len(sgprs)},
        "memory":[{"root":f"u{n+2}","file":"guest_mem.bin","offset_bytes":n*16384,"bytes":16384} for n in range(4)],
        "sampled_images":{"0":"features0.rgba32f","2":"features1.rgba32f","4":"direction.rgba32f","6":"indices.r32u"},
        "sha256":{k:sha256(v).hexdigest() for k,v in outputs.items()},
    },indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":main()
