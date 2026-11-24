"""Compare one Scarlett Commons case with Continued's CPU interpreter."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


COMMONS_REVISION = "ba9549c254647b9f6ef3b4e47684e69a668b9ec1"
CONTINUED_REVISION = "5496f79f93c41f1134ce4c9e1d2674aa00c6bb55"
CASE = Path("cases/valu-f32/add-basic.json")
ADD = "v_add_f32 v1, 0x40100000, v0"
SUBTRACT = "v_sub_f32 v1, 0x40100000, v0"


def checked_checkout(path, revision, *used_paths):
    path = path.resolve()
    git = ["git", "-C", str(path)]
    head = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    if head != revision:
        raise SystemExit(f"Expected {revision} at {path}, found {head}")
    clean = subprocess.run([*git, "diff", "--quiet", "HEAD", "--", *used_paths], check=False)
    if clean.returncode:
        raise SystemExit(f"Could not verify unchanged input files at {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scarlett_commons", type=Path)
    parser.add_argument("continued", type=Path)
    args = parser.parse_args()
    commons = checked_checkout(args.scarlett_commons, COMMONS_REVISION, "tools/cases.py", "bot/rules.py", CASE.as_posix())
    continued = checked_checkout(args.continued, CONTINUED_REVISION, "tools", "tests/semantic")

    case_bytes = (commons / CASE).read_bytes()
    with tempfile.TemporaryDirectory() as scratch:
        case_file = Path(scratch) / CASE
        case_file.parent.mkdir(parents=True)
        case_file.write_bytes(case_bytes)
        subprocess.run(
            [sys.executable, "-B", "-I", str(commons / "tools/cases.py"), str(case_file.parents[1])],
            check=True,
        )
    case = json.loads(case_bytes)

    sys.dont_write_bytecode = True
    os.environ.pop("LEONIDA_TOOLS_DIR", None)
    sys.path.insert(0, str(continued / "tests/semantic"))
    from lds_run import VSHARP, fssm
    from spirv_mini_interp import run_workgroup
    from support import translate_lines

    def execute(source):
        assembly = translate_lines("cs_portbridge_scarlett_add", source, fssm=fssm(size=tuple(case["group"])))
        words = run_workgroup(
            assembly, 1, case["wave"],
            inputs_for=lambda lane: {"%wg_id": (0, 0, 0), "%local_id": (lane, 0, 0), "%sg_lane": lane},
            push_constants=VSHARP + [0] * 28,
            memory={},
        )
        return assembly, words

    original = case["source"]
    if original.count(ADD) != 1:
        raise SystemExit("Expected one unmodified addition instruction")
    expected = int(case["expect"][0], 16)
    assembly, words = execute(original)
    if "OpFAdd" not in assembly or words != {0: expected}:
        raise SystemExit(f"Original returned {words!r}, expected {expected:#010x} at byte 0")
    print(f"{case['id']} original: expected {expected:#010x}, observed {words[0]:#010x}")

    assembly, words = execute([SUBTRACT if line == ADD else line for line in original])
    if "OpFSub" not in assembly or words != {0: 0x3F400000} or words[0] == expected:
        raise SystemExit(f"Subtraction control returned {words!r}, expected rejection of 0x3f400000")
    print(f"{case['id']} subtraction control: rejected {words[0]:#010x} against {expected:#010x}")


if __name__ == "__main__":
    main()
