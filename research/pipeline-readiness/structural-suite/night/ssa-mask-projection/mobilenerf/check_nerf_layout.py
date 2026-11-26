# SPDX-License-Identifier: MIT
"""Verify the pinned extracted guest code and PAL layout used by the 4-texture MLP draw."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("corpus","llpc","extractors","out"):
        p.add_argument("--"+arg,type=Path,required=True)
    a=p.parse_args()
    manifest=json.loads(a.corpus.read_bytes())
    sys.path.insert(0,str(a.extractors.resolve()))
    from open_pixel_census import pixel_code
    if digest_bytes(a.llpc.read_bytes())!=manifest["tools_sha256"]["llpc"]:
        raise ValueError("Unexpected PAL compiler")
    a.out.mkdir(parents=True,exist_ok=False)
    results=[]
    for index in (71,73):
        row=manifest["observations"][index]
        original=a.corpus.parent/f"{index:03}"
        dest=a.out/f"{index:03}";dest.mkdir()
        spv=original/"source.spv"
        elf=dest/"rebuilt.elf"
        binary=original/"shader.rdna2"
        if digest_bytes(spv.read_bytes())!=row["spirv"]["sha256"] or digest_bytes(binary.read_bytes())!=row["rdna"]["sha256"]:
            raise ValueError("Original source or extracted guest hash differs")
        cmd=[a.llpc.resolve(),"--gfxip=10.3.0","--filetype=obj","--shader-cache-mode=0","--auto-layout-desc",
             "--enable-pipeline-dump",f"--pipeline-dump-dir={dest.resolve()}","-o",elf.resolve(),f"{spv.resolve()},main"]
        subprocess.run(cmd,check=True,timeout=45,capture_output=True)
        if pixel_code(elf.read_bytes())!=binary.read_bytes():
            raise ValueError("Enabling reflection changed the guest instructions")
        pipe,=dest.glob("*.pipe")
        text=pipe.read_text(encoding="utf-8")
        if "userDataNode[0].type = DescriptorTableVaPtr" not in text:
            raise ValueError("Descriptor table pointer unavailable")
        raw={}
        for i,k,v in re.findall(r"userDataNode\[0\]\.next\[(\d+)\]\.(\w+) = (\w+)",text):
            raw.setdefault(int(i),{})[k]=v
        reflected={int(entry["binding"]):(entry["type"],int(entry["offsetInDwords"]),int(entry["sizeInDwords"])) for entry in raw.values()}
        expected={i:("DescriptorResource",64+8*i,8) for i in range(4)}
        expected[4]=("DescriptorBuffer",0,64)
        if reflected!=expected or any(int(v["set"],0) for v in raw.values()):
            raise ValueError(f"Reflected table differs for {index}: {reflected}")
        pal=(original/"pal.txt").read_text(encoding="utf-8")
        if not re.search(r"\.user_data_reg_map:\s+- 268435456\s+- 0\s+- 4294967295",pal):
            raise ValueError("Cannot bind user SGPR1 to table pointer")
        results.append({"id":index,"source":row["source"],"source_sha256":row["source_sha256"],
                        "spirv_sha256":digest_bytes(spv.read_bytes()),"rdna_sha256":row["rdna"]["sha256"],
                        "pal_bytes":len(binary.read_bytes()),"binding_kind_offset_length_dwords":reflected,
                        "table_user_sgpr":1,"reflected_guest_matches":True,"abi":row["rdna"]})
    (a.out/"bindings.json").write_text(json.dumps({"llpc_sha256":manifest["tools_sha256"]["llpc"],"cases":results},indent=2)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
