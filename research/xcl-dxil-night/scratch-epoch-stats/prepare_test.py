# SPDX-License-Identifier: GPL-2.0-only
"""Extract exact aggregate types and the counter loop from the staged patch."""

import argparse
from pathlib import Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patched", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = args.patched.read_text(encoding="utf-8")
    begin = source.index("#[derive(Clone, Copy)]\nstruct ScratchAllocation {")
    end = source.index("\nfn log_scratch_epoch", begin)
    template = Path(__file__).with_name("test_epoch.rs.in").read_text(encoding="utf-8")
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        output.write(template.replace("/**GEN**/", source[begin:end]))
