import argparse
from pathlib import Path
import subprocess
import sys


folder = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--rustc", default="rustc")
parser.add_argument("--linker")
parser.add_argument("--repo", type=Path, default=Path.cwd())
parser.add_argument("--output", type=Path, default=folder / "generated")
args = parser.parse_args()
output = args.output.resolve()
repo = args.repo.resolve()

compiler = [args.rustc, "--edition=2021", "--crate-name", "xcl_blob_accounting_fixture"]
if args.linker:
    compiler += ["-C", f"linker={args.linker}"]

compiler_version = subprocess.check_output([args.rustc, "--version"], text=True, timeout=10).strip()
log = [compiler_version]
for label, expect in (("baseline", 2), ("patched", 0)):
    for budget in ("real", "64"):
        suffix = "." + label + "." + budget
        generate = [sys.executable, folder / "make_accounting.py", label, "--repo", repo, "--output", output]
        if budget == "64":
            generate += ["--small-budget"]
        subprocess.run(generate, check=True, timeout=10)
        source = output / f"accounting{suffix}.rs"
        exe = source.with_suffix(".exe")
        subprocess.run([*compiler, source, "-o", exe], check=True, timeout=15)
        result = subprocess.run([exe], capture_output=True, text=True, timeout=5)
        if result.returncode != expect:
            raise SystemExit(f"{label} budget {budget}: expected exit {expect}, got {result.returncode}\n{result.stdout}{result.stderr}")
        log.extend([f"{label} budget {budget}: exit {result.returncode}", result.stdout.strip()])

report = "\n".join(log) + "\n"
(output / "accounting-results.txt").write_text(report, encoding="utf-8")
print(report, end="")
