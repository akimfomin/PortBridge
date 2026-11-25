"""Verify pinned VIctory shader and PSO cache key behavior with synthetic data."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
PIN = "80d58f8fe2769d6c857eb27abc159b6cf64530a3"
PREFIX = "cargo:rustc-env=VICTORY_SHADER_SOURCE_HASH="


def identity(executable, crate, env):
    output = subprocess.check_output([executable], text=True, cwd=crate, env=env, timeout=6)
    hashes = [line.removeprefix(PREFIX) for line in output.splitlines() if line.startswith(PREFIX)]
    assert len(hashes) == 1 and len(hashes[0]) == 64
    return hashes[0]


def run(args):
    env = {name: value for name, value in os.environ.items()
           if not name.startswith("CARGO_FEATURE_")}
    env.update(RUSTC=str(args.rustc), TARGET=args.target, CARGO_CFG_TARGET_FEATURE="sse2")
    bindir = args.bin_dir
    build = bindir / "translator-identity.exe"
    probes = bindir / "translated-cache-keys.exe"
    with tempfile.TemporaryDirectory(prefix="keys-", dir=HERE) as directory:
        first = Path(directory) / "one"
        crate = first / "crates" / "victory-shader"
        (crate / "src").mkdir(parents=True)
        app = first / "apps" / "victory" / "src"
        app.mkdir(parents=True)
        (first / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
        (first / "Cargo.lock").write_text("fixture-lock-1\n", encoding="utf-8")
        (crate / "Cargo.toml").write_text("[package]\nname='translator'\n", encoding="utf-8")
        shutil.copyfile(HERE / "translator_identity.rs", crate / "build.rs")
        translator = crate / "src" / "lib.rs"
        translator.write_text("pub fn emit() -> u8 { 1 }\n", encoding="utf-8")
        app_only = app / "main.rs"
        app_only.write_text("fn main() {}\n", encoding="utf-8")
        base = identity(build, crate, env)

        app_only.write_text("fn main() { println!(\"updated shell\"); }\n", encoding="utf-8")
        app_change = identity(build, crate, env)
        clone = Path(directory) / "two"
        shutil.copytree(first, clone)
        clone_id = identity(build, clone / "crates" / "victory-shader", env)
        assert base == app_change == clone_id

        old_source = translator.read_bytes()
        translator.write_text("pub fn emit() -> u8 { 2 }\n", encoding="utf-8")
        changed = identity(build, crate, env)
        translator.write_bytes(old_source)
        (first / "Cargo.lock").write_text("fixture-lock-2\n", encoding="utf-8")
        lock = identity(build, crate, env)
        (first / "Cargo.lock").write_text("fixture-lock-1\n", encoding="utf-8")
        feature = identity(build, crate, env | {"CARGO_FEATURE_DIAGNOSTICS": "1"})
        target = identity(build, crate, env | {"CARGO_CFG_TARGET_FEATURE": "avx2,sse2"})
        repeated = identity(build, crate, env)
        assert repeated == base
        assert len({base, changed, lock, feature, target}) == 5
        output = subprocess.check_output([probes, base, changed], text=True, env=env, timeout=6)
        assert len(output.splitlines()) == 4

    return {
        "source_pin": PIN, "fixture": "synthetic manifests and source", "initial_build": base,
        "app_only": app_change, "relocated_checkout": clone_id, "translator_edit": changed,
        "workspace_lock_edit": lock, "translator_feature": feature, "target_feature": target,
        "restored_source": repeated, "keys": dict(line.split("=", 1) for line in output.splitlines()),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rustc", type=lambda arg: Path(arg).resolve(), required=True)
    parser.add_argument("--bin-dir", type=lambda arg: Path(arg).resolve(), required=True)
    parser.add_argument("--target", default="x86_64-pc-windows-gnullvm")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with args.out.open("x", encoding="utf-8") as output:
        json.dump(run(args), output, indent=2)
        output.write("\n")
