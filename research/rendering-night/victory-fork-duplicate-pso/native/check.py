# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the exact-source single-flight probe, with separate mock and native entry points."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
PROOF = ROOT.parent
REPOSITORY = PROOF.parent
WORK = REPOSITORY.parent
EXTRACTION = runpy.run_path(str(PROOF / "run.py"))
PATCH = PROOF / "victory-fork-name-flight-c96b4f2.patch"
PATCH_SHA = "c73e5eeeecf119ce078a66796135b5d11b7ab99691fb36173bc9745b88e3f21b"
RUST = WORK / "portbridge-lds-pilot/toolchain/rustup/toolchains/stable-x86_64-pc-windows-gnullvm/bin"
LLVM = WORK / "Leonida-portable-vulkan/tools/llvm-mingw-20261117-ucrt-x86_64/bin"
DXC = WORK / "portbridge-xcl-925-evidence/dxc-v1.9.2602/bin/x64"
ARTIFACTS = WORK / "portbridge-xcl-2034-budget/native-build-candidate.jsonl"
FIXTURE = WORK / "portbridge-night-driver"
ARMS = ("baseline", "candidate")
ADAPTER = "NVIDIA GeForce RTX 4070 Ti SUPER"


def digest(path):
    result = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def env():
    result = os.environ.copy()
    result.pop("VICTORY_LIBRARY_LOCK", None)
    result["PATH"] = os.pathsep.join([str(LLVM), str(RUST), str(DXC), result.get("PATH", "")])
    return result


def command(args, directory, log, timeout, environment=None):
    result = subprocess.run(args, cwd=directory, capture_output=True, encoding="utf-8", errors="replace",
                            env=environment, timeout=timeout)
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}), see {log}")
    return result.stdout


def actual_head():
    return subprocess.check_output(["git", "-C", REPOSITORY, "rev-parse", "HEAD"], text=True, timeout=8).strip()


def input_source():
    pin, file = EXTRACTION["PIN"], EXTRACTION["LIBRARY"]
    if actual_head() != pin or digest(PATCH) != PATCH_SHA:
        raise ValueError("unexpected candidate source identity")
    subprocess.run(["git", "-C", REPOSITORY, "apply", "--reverse", "--check", PATCH],
                   check=True, timeout=8)
    old = subprocess.check_output(["git", "-C", REPOSITORY, "show", f"{pin}:{file}"],
                                  encoding="utf-8", timeout=8)
    current = (REPOSITORY / file).read_text(encoding="utf-8")
    actual = {key: EXTRACTION["extract"](source, key == "candidate")
              for key, source in zip(ARMS, (old, current), strict=True)}
    if any(text != (PROOF / "ab" / key / "extracted.rs").read_text(encoding="utf-8")
           for key, text in actual.items()):
        raise ValueError("extracted source differs from the archived CPU proof")
    return actual


def bindings():
    rows = [json.loads(line) for line in ARTIFACTS.read_text(encoding="utf-8-sig").splitlines()]
    paths = set()
    chosen = {}
    for row in rows:
        if row["reason"] != "compiler-artifact":
            continue
        name = row["target"]["name"]
        for file in row["filenames"]:
            path = Path(file)
            # Cargo places host procedural macros in separate artifact directories.
            if path.suffix in (".rlib", ".rmeta", ".dll") and path.is_file():
                paths.add(path.parent)
                if path.suffix != ".rlib":
                    continue
                if name == "windows" or (name == "windows_sys" and
                                           "Win32_System_JobObjects" in row["features"]):
                    if name in chosen:
                        raise ValueError(f"multiple available Windows binding variants for {name}")
                    chosen[name] = path
    if set(chosen) != {"windows", "windows_sys"}:
        raise ValueError("missing checked Windows Rust binding dependencies")
    args = [f"-Ldependency={path}" for path in sorted(paths)]
    for name, path in chosen.items():
        args.extend(["--extern", f"{name}={path}"])
    return args, {name: digest(path) for name, path in chosen.items()}


def build(directory):
    source = input_source()
    dependencies, binding_hashes = bindings()
    directory.mkdir()
    guard = directory / "native-guard.exe"
    command([LLVM / "clang++.exe", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror", "-Wformat=2",
             "-D_WIN32_WINNT=0x0A00", "-static", "-municode", ROOT / "guard.cpp", "-o", guard, "-lpsapi"],
            directory, directory / "guard-build.log", 12, env())
    manifest = {"pin": EXTRACTION["PIN"], "candidate_patch_sha256": PATCH_SHA,
                "bindings": binding_hashes, "guard_sha256": digest(guard),
                "fixture_source_sha256": digest(ROOT / "fixture.rs"),
                "shader_source_sha256": digest(FIXTURE / "fixture.hlsl"), "arms": {}}
    for arm, text in source.items():
        extracted = directory / f"{arm}-extracted.rs"
        extracted.write_text(text, encoding="utf-8", newline="\n")
        executable = directory / f"{arm}.exe"
        rust_env = env() | {"PB_EXTRACTED_SOURCE": str(extracted)}
        args = [RUST / "rustc.exe", "--edition=2024", ROOT / "fixture.rs", "-o", executable,
                "-C", f"linker={LLVM / 'clang.exe'}", *dependencies]
        if arm == "candidate":
            args.extend(("--cfg", "pb_candidate"))
        command(args, directory, directory / f"{arm}-build.log", 20, rust_env)
        for mode in ("default", "legacy-lock"):
            mock_env = env()
            if mode == "legacy-lock":
                mock_env["VICTORY_LIBRARY_LOCK"] = "1"
            result = command([executable, "mock"], directory, directory / f"{arm}-{mode}-mock.log", 5, mock_env)
            if "single-flight oracle passed, warm hit verified" not in result:
                raise ValueError("the mock did not complete its oracle")
        manifest["arms"][arm] = {"source_sha256": digest(extracted), "exe_sha256": digest(executable)}
    image, root = directory / "shader.dxil", directory / "signature.rootsig"
    shutil.copyfile(FIXTURE / "A.dxil", image)
    shutil.copyfile(FIXTURE / "fixture.rootsig", root)
    for path in (image, root):
        if not 32 <= path.stat().st_size <= 4096 or not path.read_bytes().startswith(b"DXBC"):
            raise ValueError("bad source-generated container")
    image_sha = digest(image)
    command([DXC / "dxv.exe", image], directory, directory / "dxv.log", 8, env())
    if digest(image) != image_sha:
        raise ValueError("validator changed the input")
    manifest.update({"shader_bytes": image.stat().st_size, "shader_sha256": image_sha,
                     "root_sha256": digest(root), "dxv_sha256": digest(DXC / "dxv.exe")})
    (directory / "ready.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("both exact-source lock modes passed on the CPU; one bounded shader validated")


def native(directory):
    manifest = json.loads((directory / "ready.json").read_text(encoding="utf-8"))
    guard, image, root = (directory / name for name in ("native-guard.exe", "shader.dxil", "signature.rootsig"))
    if (manifest["pin"] != EXTRACTION["PIN"] or manifest["candidate_patch_sha256"] != PATCH_SHA or
        digest(guard) != manifest["guard_sha256"] or digest(image) != manifest["shader_sha256"] or
        digest(root) != manifest["root_sha256"]):
        raise ValueError("prepared native fixture identity mismatch")
    identity = None
    with (directory / "native-attempts.jsonl").open("x", encoding="utf-8", buffering=1) as journal:
        for arm in ARMS:
            runner = directory / f"{arm}.exe"
            if digest(runner) != manifest["arms"][arm]["exe_sha256"]:
                raise ValueError("runner executable changed")
            worker_log = directory / f"{arm}-native.log"
            child = subprocess.run([guard, "run", runner, ADAPTER, image, root, worker_log],
                                   cwd=directory, capture_output=True, encoding="utf-8", errors="replace",
                                   timeout=8, env=env())
            output = worker_log.read_text(encoding="utf-8", errors="replace") if worker_log.exists() else ""
            try:
                report = json.loads(child.stdout)
            except json.JSONDecodeError:
                report = None
            journal.write(json.dumps({"arm": arm, "guard": report, "exit": child.returncode,
                                      "stderr": child.stderr, "worker": output}) + "\n")
            if (child.returncode or not report or report["guard"] != "returned" or not report["reaped"] or
                "single-flight oracle passed, warm hit verified" not in output):
                raise RuntimeError(f"{arm}: native guard or event oracle stopped")
            adapter = next((line for line in output.splitlines() if line.startswith("native adapter=")), "")
            if not adapter or (identity is not None and adapter != identity):
                raise ValueError("adapter or driver identity changed")
            identity = adapter
            print(f"{arm}: actual API call sequence and warm hit verified", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "native"))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.parent != ROOT:
        parser.error("choose a fresh direct child of this fixture directory")
    try:
        (build if args.mode == "build" else native)(directory)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
