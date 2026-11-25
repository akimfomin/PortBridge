# SPDX-License-Identifier: GPL-3.0-or-later
"""Produce the additive tile detile patch from VIctory's exact public file."""

import argparse
from difflib import unified_diff
from hashlib import sha256
from pathlib import Path
import shutil


SOURCE = "crates/victory-formats/src/texture.rs"
PIN = "940d32f69b22265690a0b5a15d6ded572ba33baf"
SHA = "09f0d5b71bd8c8186bfc147dc9e3447ae4abf0928ab486a64833b802e945b4eb"
HERE = Path(__file__).resolve().parent


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", type=Path)
    args = cli.parse_args()
    raw = args.source.read_bytes()
    if sha256(raw).hexdigest() != SHA:
        raise ValueError("unexpected texture.rs digest")
    old = raw.decode()
    marker = "    /// The reverse of [`Layout::detile`]: linear rows into tiled memory.\n"
    if old.count(marker) != 1:
        raise ValueError("detile method anchor missing")
    after = old.replace(marker, (HERE / "detile_method.rs.in").read_text(encoding="utf-8") + "\n" + marker)
    out = HERE / "prepared"
    out.mkdir(exist_ok=False)
    shutil.copyfile(args.source, out / "stock.rs")
    (out / "candidate.rs").write_bytes(after.encode())
    diff = f"diff --git a/{SOURCE} b/{SOURCE}\n" + "".join(
        unified_diff(old.splitlines(keepends=True), after.splitlines(keepends=True),
                     fromfile=f"a/{SOURCE}", tofile=f"b/{SOURCE}"))
    (out / "victory-detile-one-color-tile.patch").write_bytes(diff.encode())
    print(f"{PIN} candidate {sha256(after.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
