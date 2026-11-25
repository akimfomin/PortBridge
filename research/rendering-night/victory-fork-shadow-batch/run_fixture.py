import argparse
from pathlib import Path
import subprocess
import sys


folder = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, default=Path.cwd())
parser.add_argument("--output", type=Path, default=folder / "generated")
parser.add_argument("--rustc", default="rustc")
parser.add_argument("--linker")
args = parser.parse_args()
out = args.output.resolve()
compiler = [args.rustc, "--edition=2024", "--crate-name", "shadow_submit_fixture"]
if args.linker:
    compiler += ["-C", f"linker={args.linker}"]

version = subprocess.check_output([args.rustc, "--version"], text=True, timeout=10).strip()
log = [version]
for mode, expected in (("baseline", 2), ("candidate", 0)):
    subprocess.run([sys.executable, folder / "extract_submit.py", mode, "--repo", args.repo.resolve(),
        "--out", out], check=True, timeout=10)
    for label, flags in (("default", []), ("diagnostics", ["--cfg", 'feature="diagnostics"'])):
        exe = out / f"state.{mode}.{label}.exe"
        subprocess.run([*compiler, *flags, out / f"state.{mode}.rs", "-o", exe], check=True, timeout=15)
        ran = subprocess.run([exe], capture_output=True, text=True, timeout=5)
        if ran.returncode != expected:
            raise SystemExit(f"{mode} {label} expected {expected}, got {ran.returncode}\n{ran.stdout}{ran.stderr}")
        log.extend([f"{mode} {label}: exit {ran.returncode}", ran.stdout.strip()])

text = "\n".join(log) + "\n"
(out / "results.txt").write_text(text, encoding="utf-8")
print(text, end="")
