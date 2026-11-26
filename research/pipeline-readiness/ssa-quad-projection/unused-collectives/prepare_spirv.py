"""Convert matched XCL arms to validated SPIR-V and separate flags from code sizes."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess

def digest(p):
    return sha256(p.read_bytes()).hexdigest()

def feature_flags(p):
    b = p.read_bytes()
    assert b[:4] == b"DXBC"
    count, = struct.unpack_from("<I", b, 28)
    flags = []
    for offset, in struct.iter_unpack("<I", b[32:32+4*count]):
        if b[offset:offset+4] == b"SFI0":
            length, = struct.unpack_from("<I", b, offset+4)
            assert length == 8
            flags.append(struct.unpack_from("<Q", b, offset+8)[0])
    assert len(flags) == 1
    return flags[0]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("arms", "out", "converter", "tools"):
        p.add_argument("--"+arg, type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    rows = json.loads((a.arms/"structure.json").read_bytes())
    baseline = {r["case"]:r for r in rows if r["mode"] == "whole"}
    out = []
    for r in rows:
        name, mode = r["case"], r["mode"]
        dxil = a.arms/f"{name}-{mode}.dxil"
        assert digest(dxil) == r["sha256"]
        flags = feature_flags(dxil)
        assert flags == feature_flags(a.arms/f"{name}-whole.dxil")
        assert (r["branches"],r["phis"]) == (baseline[name]["branches"],baseline[name]["phis"])
        if name not in ("nerf71", "nerf73", "raylib"):
            continue
        spv = a.out/(dxil.stem+".spv")
        cmd = [a.converter, dxil]
        for slot in (0,2,3,4,5):
            cmd += ["--root-descriptor", "uav", "0", str(slot)]
        subprocess.run(cmd+["--output",spv], check=True, timeout=25, capture_output=True)
        subprocess.run([a.tools/"spirv-val.exe","--target-env","vulkan1.3",spv], check=True, timeout=25)
        dis = subprocess.check_output([a.tools/"spirv-dis.exe","--raw-id",spv], timeout=25).decode()
        out.append(dict(case=name,mode=mode,dxil_sha256=r["sha256"],dxil_features=hex(flags),
                        spirv_bytes=spv.stat().st_size,spirv_sha256=digest(spv),
                        ballots=dis.count("OpGroupNonUniformBallot "),
                        quad_reads=dis.count("OpGroupNonUniformQuadBroadcast ")+dis.count("OpGroupNonUniformQuadSwap ")))
    (a.out/"validated-spirv.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")

if __name__ == "__main__":
    main()

