"""Compile and validate the source-generated transport shaders."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess


def run(args):
    result = subprocess.run(args, capture_output=True, timeout=8, check=False)
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr).decode(errors="replace"))
    return (result.stdout + result.stderr).decode(errors="replace").strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dxc", type=Path, required=True)
    parser.add_argument("--dxv", type=Path, required=True)
    parser.add_argument("--sticky", action="store_true")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    dxc = args.dxc.resolve(strict=True)
    dxv = args.dxv.resolve(strict=True)
    source = Path(__file__).resolve().with_name("sticky-transport.hlsl" if args.sticky else "transport.hlsl")
    stages = ("send", "forward", "receive") if args.sticky else ("send", "receive")
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    embedded = []
    rows = {}
    version = run([dxc, "--version"])
    for threads in (32, 64):
        for layout, tiled in (("scalar", 0), ("tiled", 1)):
            for action in stages:
                name = f"{action}_{threads}_{layout}"
                shader = out / f"{name}.dxil"
                asm = out / f"{name}.ll"
                run([dxc, "-T", "cs_6_6", "-E", action, "-O3", "-WX",
                     "-D", f"THREADS={threads}", "-D", f"TILED={tiled}",
                     "-Fo", shader, "-Fc", asm, source])
                validation = run([dxv, shader])
                bytecode = shader.read_bytes()
                if bytecode[:4] != b"DXBC" or len(bytecode) > 24 * 1024:
                    raise ValueError(f"unexpected container {name}")
                text = asm.read_text(encoding="utf-8")
                usage = {key: len(re.findall(rf"(?m)^\s+.*call .*@dx\.op\.rawBuffer{op}\.i32\(", text))
                         for key, op in (("loads", "Load"), ("stores", "Store"))}
                if not sum(usage.values()):
                    raise ValueError(f"no raw transport instructions in {name}")
                rows[name] = {"bytes": len(bytecode), "sha256": sha256(bytecode).hexdigest(),
                              **usage, "validation": validation}
                hexbytes = [f"0x{byte:02x}" for byte in bytecode]
                lines = ["    " + ", ".join(hexbytes[i:i + 16]) + "," for i in range(0, len(hexbytes), 16)]
                embedded.append(f"constexpr unsigned char {name}[]{{\n" + "\n".join(lines) + "\n};")
    for threads in (32, 64):
        choices = (("forward", "loads"), ("forward", "stores")) if args.sticky else (
            ("send", "stores"), ("receive", "loads"))
        for action, op in choices:
            if rows[f"{action}_{threads}_tiled"][op] >= rows[f"{action}_{threads}_scalar"][op]:
                raise ValueError(f"the fixture did not reduce {op} in {action}")
    (out / "programs.inc").write_text("\n".join(embedded) + "\n", encoding="ascii")
    (out / "validation.json").write_text(json.dumps({"compiler": version, "shaders": rows}, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
