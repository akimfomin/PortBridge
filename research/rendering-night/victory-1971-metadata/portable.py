# SPDX-License-Identifier: GPL-3.0-or-later
"""Build and optionally run the standalone source-only metadata probe on Windows x64."""

import argparse
from hashlib import file_digest
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess


ROOT = Path(__file__).resolve().parent
SOURCE = runpy.run_path(str(ROOT / "reconstruct.py"))
TARGET = "x86_64-pc-windows-msvc"
ORIGINAL_ADAPTER = "NVIDIA GeForce RTX 4070 Ti SUPER"
GUARDS = {
    "guard.h": "f07e7302b85bdcdd66745f283768e60a2e266b6a16847e3234f92d95606c161f",
    "launcher.cpp": "aa3586d8fc32ee4c9cd0e006df5106507e980aa413859b52f0b7c8c4ea719a11",
}


def digest(path):
    with path.open("rb") as data:
        return file_digest(data, "sha256").hexdigest()


def run(args, directory, log, timeout, env=None):
    child = subprocess.run(args, cwd=directory, env=env, timeout=timeout,
                           capture_output=True, encoding="utf-8", errors="replace")
    log.write_text(child.stdout + child.stderr, encoding="utf-8")
    if child.returncode:
        raise RuntimeError(f"Exit {child.returncode}; see {log}")
    return child.stdout


def adapter_source(name, vendor):
    if not re.fullmatch(r"[A-Za-z0-9()._ +\-]{3,120}", name):
        raise ValueError("adapter name must be a short literal DXGI name")
    base = (ROOT / "fixture.rs").read_text(encoding="utf-8")
    if name == ORIGINAL_ADAPTER and vendor == "10de":
        return (ROOT / "fixture.rs").read_bytes()
    source, names = re.subn(r'(?<=const ADAPTER: &str = ")[^"]+(?=";)', name, base)
    source, vendors = re.subn(r"(?<=desc\.VendorId == 0x)10de\b", vendor, source)
    if (names, vendors) != (1, 1):
        raise ValueError("pinned adapter selector did not match exactly")
    return source.encode("utf-8")


def build(args, destination):
    exact = SOURCE["extract"]()
    fixture = adapter_source(args.adapter, args.vendor)
    for name, expected in GUARDS.items():
        if digest(ROOT / "guard" / name) != expected:
            raise ValueError(f"guard source changed: {name}")
    dxc = args.dxc.resolve(strict=True)
    reference = destination / "exact.rs"
    crate = destination / "crate"
    destination.mkdir()
    crate.mkdir()
    reference.write_bytes(exact)
    (crate / "fixture.rs").write_bytes(fixture)
    for name in ("Cargo.toml", "Cargo.lock"):
        shutil.copyfile(ROOT / name, crate / name)
    env = os.environ.copy()
    env.update({"PB_METADATA_SOURCE": str(reference), "PATH": f"{dxc}{os.pathsep}{env.get('PATH', '')}"})
    run(["cargo", "build", "--locked", "--jobs", "1", "--target", TARGET,
         "--manifest-path", crate / "Cargo.toml", "--target-dir", destination / "target"],
        destination, destination / "rust.log", 180, env)
    worker = destination / "metadata.exe"
    shutil.copyfile(destination / "target" / TARGET / "debug/metadata.exe", worker)
    output = run([worker, "mock"], destination, destination / "mock.log", 5, env)
    if "exact metadata encoding and deferred registry passed" not in output:
        raise ValueError("the CPU oracle did not finish")

    shader, signature = (destination / name for name in ("shader.dxil", "signature.rootsig"))
    run([dxc / "dxc.exe", "-T", "cs_6_0", "-E", "main", "-O3", "-Fo", shader,
         "-Frs", signature, ROOT / "read_metadata.hlsl"], destination, destination / "dxc.log", 10, env)
    for container in (shader, signature):
        data = container.read_bytes()
        if not 32 <= len(data) <= 4096 or data[:4] != b"DXBC":
            raise ValueError(f"unexpected validated container size or signature for {container}")
    dxv = run([dxc / "dxv.exe", shader], destination, destination / "dxv.log", 8, env)
    if "validation succeeded" not in dxv.lower():
        raise ValueError("DXV did not confirm this shader")

    validated = [worker, shader, signature]
    if args.native_ready:
        guard = destination / "guard.exe"
        run(["cl.exe", "/nologo", "/std:c++20", "/EHsc", "/O2", "/D_WIN32_WINNT=0x0A00",
             ROOT / "guard/launcher.cpp", f"/Fe{guard}", "Psapi.lib"],
            destination, destination / "guard.log", 30, env)
        validated.append(guard)
    evidence = {
        "revision": SOURCE["PIN"], "toolchain_target": TARGET, "adapter": args.adapter,
        "vendor_hex": args.vendor, "source_extraction_sha256": digest(reference),
        "fixture_sha256": digest(crate / "fixture.rs"), "dxv_sha256": digest(dxc / "dxv.exe"),
        "cargo_lock_sha256": digest(crate / "Cargo.lock"),
        "shader_bytes": shader.stat().st_size, "native_ready": args.native_ready,
        "sha256": {path.name: digest(path) for path in validated},
    }
    (destination / "ready.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"CPU packing oracle and DXV passed for {args.adapter}")


def native(destination):
    proof = json.loads((destination / "ready.json").read_text(encoding="utf-8"))
    if not proof["native_ready"] or proof["revision"] != SOURCE["PIN"]:
        raise ValueError("this build has no prepared native worker")
    guard, worker, shader, signature = (destination / name for name in
                                         ("guard.exe", "metadata.exe", "shader.dxil", "signature.rootsig"))
    for path in (guard, worker, shader, signature):
        if digest(path) != proof["sha256"][path.name]:
            raise ValueError(f"prepared native input changed: {path}")
    journal = destination / "native-attempt.json"
    log = destination / "native.log"
    if log.exists():
        raise ValueError("a native log already exists for this build")
    with journal.open("x", encoding="utf-8") as status:
        status.write('{"status":"launch_started"}\n')
    child = subprocess.run([guard, "run", worker, proof["adapter"], shader, signature, log],
                           cwd=destination, timeout=8, capture_output=True, encoding="utf-8", errors="replace")
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    result = {"exit": child.returncode, "guard": child.stdout, "stderr": child.stderr, "worker": text}
    journal.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    report = json.loads(child.stdout)
    if child.returncode or report["guard"] != "returned" or not report["reaped"] or \
       "four exact metadata readbacks passed" not in text:
        raise RuntimeError(f"native admission or readback stopped; see {journal}")
    print(text, end="")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    cpu = sub.add_parser("build", help="compile and run the CPU oracle, no GPU device")
    cpu.add_argument("directory", type=Path)
    cpu.add_argument("--dxc", type=Path, required=True, help="directory with dxc.exe and dxv.exe")
    cpu.add_argument("--adapter", default=ORIGINAL_ADAPTER)
    cpu.add_argument("--vendor", default="10de", choices=("10de", "1002", "8086"))
    cpu.add_argument("--native-ready", action="store_true", help="also compile the bounded launcher")
    gpu = sub.add_parser("native", help="single guarded hardware run of one prepared build")
    gpu.add_argument("directory", type=Path)
    args = parser.parse_args()
    output = args.directory.resolve()
    if output.parent != ROOT:
        parser.error("the run directory must be a direct child of this source folder")
    if args.mode == "build":
        build(args, output)
    else:
        native(output)
