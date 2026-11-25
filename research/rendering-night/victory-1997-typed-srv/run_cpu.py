import argparse
from pathlib import Path
import re
import subprocess


PIN = "d732465f64dd868dd0d71811d5596519cdcba889"
SOURCE = "crates/victory-gpu/src/host.rs"
folder = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, default=Path.cwd())
parser.add_argument("--output", type=Path, default=folder / "generated")
parser.add_argument("--rustc", default="rustc")
parser.add_argument("--linker")
args = parser.parse_args()

head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.repo, text=True).strip()
assert head == PIN, head
original = subprocess.check_output(["git", "show", f"{PIN}:{SOURCE}"], cwd=args.repo, text=True, encoding="utf-8")
patched = (args.repo / SOURCE).read_text(encoding="utf-8")
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
fixture = (folder / "srv_fixture.rs.in").read_text(encoding="utf-8")
rustc = [args.rustc, "--edition=2024", "--crate-name", "compositor_srv_fixture"]
if args.linker:
    rustc += ["-C", f"linker={args.linker}"]
log = [subprocess.check_output([args.rustc, "--version"], text=True, timeout=10).strip()]

for label, host, expected in (("baseline", original, 2), ("candidate", patched, 0)):
    start = host.index("fn swap_format(")
    functions = host[start:host.index("const BUFFERS:", start)]
    lines = re.findall(r"^\s+let srv_fmt = [^\n]+;", host, re.MULTILINE)
    assert len(lines) == 1
    for text in ("rt_blend.SrcBlend = D3D12_BLEND_ONE;", "rt_blend.DestBlend = D3D12_BLEND_INV_SRC_ALPHA;",
                 "return tex.Sample(smp, uv);", "Format: srv_fmt,"):
        assert text in host
    rust = fixture.replace("@FORMAT_FUNCTIONS@", functions).replace("@SOURCE_SRV@", lines[0]).replace("@MODE@", label)
    source = out / f"srv.{label}.rs"
    source.write_text(rust, encoding="utf-8")
    exe = source.with_suffix(".exe")
    subprocess.run([*rustc, source, "-o", exe], check=True, timeout=15)
    arm = subprocess.run([exe], capture_output=True, text=True, timeout=5)
    if arm.returncode != expected:
        raise SystemExit(f"{label}: expected {expected}, got {arm.returncode}\n{arm.stdout}{arm.stderr}")
    log.extend([f"{label}: exit {arm.returncode}", arm.stdout.strip()])

result = "\n".join(log) + "\n"
(out / "cpu-results.txt").write_text(result, encoding="utf-8")
print(result, end="")
