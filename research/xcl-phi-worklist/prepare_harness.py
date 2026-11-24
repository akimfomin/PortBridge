"""Build and compare the isolated production-module harness snapshots."""

import argparse
import difflib
import hashlib
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
CHECKOUT = WORK / "portbridge-rnd-xcl-1d027e5"
DXIL = Path("crates/xcl/src/gpu/dxil")
BASE = "1d027e5c76c9a86a7ee2ca1cc677edf0be95d331"
CFG = "365148bcc935ef04aeb9608debe0d72ba7db866f"
RUSTC = WORK / "portbridge-lds-pilot/toolchain/rustup/toolchains/stable-x86_64-pc-windows-gnullvm/bin/rustc.exe"
LINKER = WORK / "Leonida-portable-vulkan/tools/llvm-mingw-20261117-ucrt-x86_64/bin/x86_64-w64-mingw32-clang.exe"


def upstream(checkout, rev, path):
    return subprocess.check_output(
        ["git", "-C", str(checkout), "show", f"{rev}:{(DXIL / path).as_posix()}"],
        text=True, encoding="utf-8",
    )


def combined(original, candidate):
    method = r"(?ms)^    /// [^\n]*[Pp]hi[^\n]*\n(?:    ///[^\n]*\n)*    fn simplify_phis\(.+?^    }"
    old = re.findall(method, original)
    new = re.findall(method, candidate)
    assert len(old) == len(new) == 1
    helper = re.findall(r"(?ms)^const NO_WATCH:.*?(?=^/// The value)", candidate)
    assert len(helper) == 1
    assert original.count("use std::collections::HashMap;") == 1
    result = original.replace("use std::collections::HashMap;",
        "use std::cmp::Reverse;\nuse std::collections::{BinaryHeap, HashMap};")
    result = result.replace(old[0], new[0])
    return result.replace("/// The value \x60v\x60 stands", helper[0] + "/// The value \x60v\x60 stands")


def snapshot(args, name, rev, optimizer):
    path = ROOT / name
    (path / "module").mkdir(parents=True, exist_ok=True)
    for file in ("bitstream.rs", "module.rs"):
        (path / file).write_text(upstream(args.checkout, rev, file), encoding="utf-8", newline="\n")
    (path / "module/opt.rs").write_text(optimizer, encoding="utf-8", newline="\n")
    for fixture in ("phi_bench", "phi_graph_compare"):
        source = f"{fixture}.rs"
        (path / source).write_bytes((ROOT / source).read_bytes())
        cmd = [args.rustc, "--edition=2021", "-C", "opt-level=3"]
        if args.linker:
            cmd.extend(("-C", f"linker={args.linker}"))
        subprocess.run(cmd + ["-o", f"{fixture}.exe", source], cwd=path, check=True, timeout=60)
    subprocess.run(
        [str(path / "phi_graph_compare.exe"), "loop-graphs.bcpack"], cwd=path, check=True, timeout=30,
    )


def verify(first, second):
    a = (ROOT / first / "loop-graphs.bcpack").read_bytes()
    b = (ROOT / second / "loop-graphs.bcpack").read_bytes()
    assert a == b, (first, second)
    print(f"{first} vs {second}: 2048 byte-identical graphs {hashlib.sha256(a).hexdigest()}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=CHECKOUT)
    parser.add_argument("--rustc", default=str(RUSTC) if RUSTC.exists() else "rustc")
    parser.add_argument("--linker", default=str(LINKER) if LINKER.exists() else "")
    parser.add_argument("--optimizer", type=Path, help="Specify an alternate optimizer source file")
    args = parser.parse_args()
    optimizer = (args.optimizer or (args.checkout / DXIL / "module/opt.rs")).read_text(encoding="utf-8")
    cfg_optimizer = upstream(args.checkout, CFG, "module/opt.rs")
    cfg_candidate = combined(cfg_optimizer, optimizer)
    snapshot(args, "base", BASE, upstream(args.checkout, BASE, "module/opt.rs"))
    snapshot(args, "candidate", BASE, optimizer)
    snapshot(args, "cfg", CFG, cfg_optimizer)
    snapshot(args, "cfg-combined", CFG, cfg_candidate)
    verify("base", "candidate")
    verify("cfg", "cfg-combined")
    file = (DXIL / "module/opt.rs").as_posix()
    (ROOT / "xcl-1818-phi-adaptation.patch").write_text(
        "".join(difflib.unified_diff(
            cfg_optimizer.splitlines(keepends=True), cfg_candidate.splitlines(keepends=True),
            fromfile=f"a/{file}", tofile=f"b/{file}",
        )), encoding="utf-8", newline="\n",
    )


if __name__ == "__main__":
    main()
