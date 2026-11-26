# SPDX-License-Identifier: MIT
"""Rebuild and validate all six Mobile NeRF DXIL containers from the licensed guest streams."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline", "candidate", "dxc-dir", "dxv", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    guest_dir = Path(__file__).resolve().parent / "guest"
    manifest = json.loads((guest_dir / "manifest.json").read_bytes())
    args.out.mkdir(parents=True, exist_ok=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith("XCL_")}
    env["XCL_DXC_DIR"] = str(args.dxc_dir.resolve())
    for row in manifest["cases"]:
        guest = gzip.decompress((guest_dir / row["guest"]).read_bytes())
        source = (guest_dir / row["source"]).read_bytes().replace(b"\r\n", b"\n")
        if sha(guest) != row["guest_sha256"] or sha(source) != row["source_lf_sha256"]:
            raise ValueError(f"Source or guest checksum differs for {row['id']}")
        guest_path = args.out / f"{row['id']:03}.rdna2"
        guest_path.write_bytes(guest)
        fields = ("wave", "spi_ps_input_ena", "interpolants", "color_mask", "depth_mode")
        abi = [str(row["abi"][key]) for key in fields]
        for name, program, mode in (("whole", args.baseline, "whole"), ("strict", args.baseline, "project"),
                                    ("compound", args.candidate, "project")):
            out = args.out / f"{row['id']:03}-{name}.dxil"
            subprocess.run([program.resolve(), guest_path.resolve(), out.resolve(), *abi, "root-4",
                            "generic", mode], env=env, check=True, timeout=90)
            subprocess.run([args.dxv.resolve(), out.resolve()], check=True, timeout=30)
            got = sha(out.read_bytes())
            if got != row["variants"][name]["sha256"]:
                raise ValueError(f"Validated DXIL hash differs for {out.name}: {got}")
            print(out.name, got)


if __name__ == "__main__":
    main()
