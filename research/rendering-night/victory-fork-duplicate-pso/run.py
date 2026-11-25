#!/usr/bin/env python3
"""Run the exact pipeline-library admission logic with a fake host library."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess

PIN = "c96b4f2b8365bf43d54ab074940923ef8267f4c6"
LIBRARY = "crates/victory-gpu/src/pipeline/library.rs"


def extract(source: str, candidate: bool) -> str:
    start = "type ActiveNames" if candidate else "fn same_name("
    helpers = source[source.index(start) : source.index("const LIBRARY_FILE:")]
    if candidate:
        # Signal the controlled test immediately before a waiter drops the map lock.
        wait = "            active = done.wait(active)"
        if helpers.count(wait) != 1:
            raise ValueError("candidate wait point did not match exactly once")
        helpers = helpers.replace(wait, "            observe_wait();\n" + wait)
    fn_start = source.index("pub(crate) fn pipeline(")
    fn_end = source.index("/// Writes the library", fn_start)
    return helpers + source[fn_start:fn_end]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rustc", default="rustc")
    parser.add_argument("--linker")
    args = parser.parse_args()

    proof = Path(__file__).resolve().parent
    repo = proof.parent
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=10).strip()
    if head != PIN:
        raise ValueError(f"expected {PIN}, got {head}")
    baseline = subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{PIN}:{LIBRARY}"], text=True, encoding="utf-8", timeout=10
    )
    candidate = (repo / LIBRARY).read_text(encoding="utf-8")

    for arm, source in (("baseline", baseline), ("candidate", candidate)):
        output = proof / "ab" / arm
        output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(proof / "harness.rs", output / "harness.rs")
        (output / "extracted.rs").write_text(extract(source, arm == "candidate"), encoding="utf-8")
        target = output / "pipeline_test.exe"
        compile_args = [args.rustc, "--edition=2024", "--test", str(output / "harness.rs"), "-o", str(target)]
        if arm == "candidate":
            compile_args.extend(["--cfg", "pb_candidate"])
        if args.linker:
            compile_args.extend(["-C", f"linker={args.linker}"])
        subprocess.run(compile_args, check=True, timeout=40)
        env = os.environ.copy()
        env.pop("VICTORY_LIBRARY_LOCK", None)
        for mode in ("default", "legacy-lock"):
            if mode == "legacy-lock":
                env["VICTORY_LIBRARY_LOCK"] = "1"
            tested = subprocess.run(
                [str(target), "--test-threads=1", "--nocapture"],
                capture_output=True, text=True, timeout=30, env=env,
            )
            log = tested.stdout + tested.stderr
            (output / f"{mode}-test.log").write_text(log, encoding="utf-8")
            print(f"{arm} {mode}\n{log}")
            tested.check_returncode()


if __name__ == "__main__":
    main()
