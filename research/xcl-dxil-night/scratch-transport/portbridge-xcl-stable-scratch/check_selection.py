# SPDX-License-Identifier: GPL-2.0-only
"""Extract the exact selection/offset methods into a tiny Rust type check."""

import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patched", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--rustc", required=True, type=Path)
    parser.add_argument("--linker", type=Path)
    args = parser.parse_args()
    p = args.patched.read_text(encoding="utf-8")
    scratch = p[p.index("struct StableScratch {"):p.index("struct Scratch {")]
    select = p[p.index("    fn stable_scratch("):p.index("    fn static_handle(")]
    fixture = Path(__file__).with_name("selection.rs.in").read_text(encoding="utf-8")
    output = args.output.resolve()
    output.mkdir(exist_ok=False)
    src = output / "selection.rs"
    src.write_text(fixture.replace("/*STABLE_SCRATCH*/", scratch).replace("/*SELECT*/", select), encoding="utf-8")
    lib = output / "selection.exe"
    cmd = [args.rustc.resolve(strict=True), "--edition=2024", "--test", "-D", "warnings"]
    if args.linker:
        cmd += ["-C", f"linker={args.linker.resolve(strict=True)}"]
    subprocess.run([*cmd, src, "-o", lib], check=True, timeout=8)
    subprocess.run([lib, "--test-threads=1"], check=True, timeout=5)


if __name__ == "__main__":
    main()
