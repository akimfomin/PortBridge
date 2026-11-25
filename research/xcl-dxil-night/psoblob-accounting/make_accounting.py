import argparse
from pathlib import Path
import re
import subprocess


folder = Path(__file__).resolve().parent
source = Path("crates/xcl/src/hle/d3d12x/real.rs")
base = "cbc296ab65a2661a61e3e2da109134bcd5319f60"

parser = argparse.ArgumentParser()
parser.add_argument("version", choices=("baseline", "patched"))
parser.add_argument("--small-budget", action="store_true")
parser.add_argument("--repo", type=Path, default=Path.cwd())
parser.add_argument("--output", type=Path, default=folder)
args = parser.parse_args()
root = args.repo.resolve()

if args.version == "baseline":
    real = subprocess.check_output(["git", "show", f"{base}:{source.as_posix()}"], cwd=root, text=True, encoding="utf-8")
else:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    assert head == base
    real = (root / source).read_text(encoding="utf-8")

compute = real[real.index("static COMPUTE_BLOBS:"):].split("#[cfg(test)]", 1)[0]
insert_compute = "unsafe fn keep_compute_blob(" + real.split("unsafe fn keep_compute_blob(", 1)[1].split("\n///", 1)[0]
graphics = real[real.index("static GRAPHICS_BLOBS:"):].split("\n///", 1)[0]
code = "\n".join([compute, insert_compute, graphics])
if args.small_budget:
    code, count = re.subn(r"(const (?:COMPUTE|GRAPHICS)_BLOBS_MAX: usize = )[^;]+;", r"\g<1>64;", code)
    assert count == 2

template = (folder / "accounting_fixture.rs.in").read_text(encoding="utf-8")
assert template.count("@PRODUCTION_CACHE@") == 1
size = "64" if args.small_budget else "real"
args.output.mkdir(parents=True, exist_ok=True)
(args.output / f"accounting.{args.version}.{size}.rs").write_text(
    template.replace("@PRODUCTION_CACHE@", code), encoding="utf-8"
)
