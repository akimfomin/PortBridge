#!/usr/bin/env python3
"""Compare equivalent finite SPIR-V layouts outside Continued's emitter contract."""

from pathlib import Path
import argparse
import subprocess
import sys
import tempfile


def check(assembler, validator):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from spirv_loop_guard import add_guards

    source = Path(__file__).with_name("layout-control.spvasm").read_text(encoding="utf-8")
    moved = "%late = OpLabel\nOpBranch %header\n"
    earlier = source.replace(moved, "").replace("%header = OpLabel\n", moved + "%header = OpLabel\n")

    with tempfile.TemporaryDirectory() as scratch:
        def validate(name, assembly):
            path = Path(scratch) / (name + ".spvasm")
            spv = path.with_suffix(".spv")
            path.write_text(assembly, encoding="utf-8")
            subprocess.run([assembler, "--target-env", "vulkan1.3", path, "-o", spv], check=True, timeout=10)
            subprocess.run([validator, "--target-env", "vulkan1.3", spv], check=True, timeout=10)
            print(f"{name}: Vulkan 1.3 SPIR-V valid")

        validate("forward-predecessors-earlier", earlier)
        validate("one-forward-predecessor-later", source)
        validate("earlier-guarded", add_guards(earlier, 3))
        try:
            add_guards(source, 3)
        except ValueError as error:
            if str(error) != "expected one back edge at %header, found 2":
                raise
            print(f"later-guarded: {error}")
        else:
            raise AssertionError("expected the guard's physical-order precondition to reject the later arm")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assembler")
    parser.add_argument("validator")
    args = parser.parse_args()
    check(args.assembler, args.validator)
