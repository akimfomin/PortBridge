"""Build exact-base and patched standalone XCL DXIL fixture snapshots."""

import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
CHECKOUT = WORK / "portbridge-night-xcl-phi-scc"
REV = "20cf13022f764208384c610c2ae6a3f4eed201a2"
DXIL = Path("crates/xcl/src/gpu/dxil")
RUSTC = WORK / "portbridge-lds-pilot/toolchain/rustup/toolchains/stable-x86_64-pc-windows-gnullvm/bin/rustc.exe"
LINKER = WORK / "Leonida-portable-vulkan/tools/llvm-mingw-20261117-ucrt-x86_64/bin/x86_64-w64-mingw32-clang.exe"
DXV = WORK / "portbridge-xcl-925-evidence/dxc-v1.9.2602/bin/x64/dxv.exe"
FILES = ("bitstream.rs", "container.rs", "module.rs", "shader.rs", "module/opt.rs")


def build(arm):
    target = ROOT / arm
    (target / "module").mkdir(parents=True, exist_ok=True)
    for name in FILES:
        path = DXIL / name
        data = subprocess.check_output(["git", "-C", str(CHECKOUT), "show", f"{REV}:{path.as_posix()}"])
        if arm == "candidate" and name == "module/opt.rs":
            data = (CHECKOUT / path).read_bytes()
        (target / name).write_bytes(data)
    shutil.copyfile(ROOT / "phi_ring.rs", target / "phi_ring.rs")
    env = {key: value for key, value in os.environ.items() if key.upper() != "XCL_DXIL_NO_OPT"}
    env["PATH"] = os.pathsep.join([str(LINKER.parent), str(RUSTC.parent), env["PATH"]])
    compile_args = [str(RUSTC), "--edition", "2024", "-D", "warnings", "-C", f"linker={LINKER}"]
    subprocess.run([*compile_args, "-o", "phi_ring.exe", "phi_ring.rs"], cwd=target, env=env, timeout=20, check=True)
    print(f"{arm} ({REV})", flush=True)
    subprocess.run([str(target / "phi_ring.exe"), str(target)], cwd=target, env=env, timeout=10, check=True)
    for blob in sorted(target.glob("*.dxil")):
        validation = subprocess.run([str(DXV), str(blob)], cwd=target, timeout=8, capture_output=True, check=True, text=True)
        print(f"{arm}/{blob.name} {validation.stdout.strip()} {validation.stderr.strip()}".rstrip(), flush=True)
    if arm == "candidate":
        shutil.copyfile(ROOT / "opt_tests.rs", target / "opt_tests.rs")
        subprocess.run([*compile_args, "--test", "-o", "phi_ring_tests.exe", "opt_tests.rs"], cwd=target, env=env, timeout=20, check=True)
        subprocess.run([str(target / "phi_ring_tests.exe"), "--test-threads=1", "phi_scc"], cwd=target, env=env, timeout=10, check=True)


if __name__ == "__main__":
    build("baseline")
    build("candidate")
