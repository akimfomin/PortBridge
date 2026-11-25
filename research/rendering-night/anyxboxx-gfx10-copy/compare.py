import argparse
import csv
from pathlib import Path
import statistics
import subprocess
import sys


BASE = "22c1cf973e7e2ad89fbec8e801d77d287c48729f"
CRATE = Path("rust/anyxboxx-texture")
SOURCES = ("bc7.rs", "gfx10.rs", "gfx10_eq.rs", "lib.rs", "png.rs", "tiles.rs")
CASES = ("rgba1080_xor", "bc7_4k", "bc7_4k_xor64", "rgba_linear", "bc7_tail", "rgba_wide", "rgba_tall",
    "bc7_one", "bc7_2x1", "bc7_1x2", "bc7_2x2")
VARIANTS = ("baseline", "candidate")
TESTS = ("gfx10_tiling", "gfx10_copy_oracle")

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("phase", choices=("build", "check", "bench"))
parser.add_argument("--repo", type=Path, default=Path.cwd())
parser.add_argument("--out", type=Path, default=root / "generated")
parser.add_argument("--rustc", default="rustc")
parser.add_argument("--linker")
parser.add_argument("--target-cpu")
parser.add_argument("--case", action="append", choices=CASES)
parser.add_argument("--pairs", type=int, choices=(1, 2, 3, 4, 5), default=4)
args = parser.parse_args()
repo = args.repo.resolve()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=True)


def build():
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    assert actual == BASE, actual
    compiler = [args.rustc, "--edition=2021", "-C", "opt-level=3"]
    if args.linker:
        compiler += ["-C", f"linker={args.linker}"]
    if args.target_cpu:
        compiler += ["-C", f"target-cpu={args.target_cpu}"]
    compiler_version = subprocess.check_output([args.rustc, "--version", "--verbose"], text=True)
    (out / "compiler.txt").write_text(compiler_version + f"target-cpu={args.target_cpu or 'default'}\n", encoding="utf-8")
    baseline = out / "baseline" / "source"
    baseline.mkdir(parents=True, exist_ok=True)
    for name in SOURCES:
        content = subprocess.check_output(["git", "show", f"{BASE}:{(CRATE / 'src' / name).as_posix()}"], cwd=repo)
        (baseline / name).write_bytes(content)
    for label, sources in (("baseline", baseline), ("candidate", repo / CRATE / "src")):
        sub = out / label
        sub.mkdir(parents=True, exist_ok=True)
        artifact = sub / "libanyxboxx_texture.rlib"
        subprocess.run([*compiler, "--crate-name", "anyxboxx_texture", "--crate-type", "rlib",
            sources / "lib.rs", "-o", artifact], check=True, timeout=45)
        link = [*compiler, "--extern", f"anyxboxx_texture={artifact}"]
        subprocess.run([*link, root / "gfx10_copy_bench.rs", "-o", sub / "benchmark.exe"], check=True, timeout=45)
        for name in TESTS:
            source = repo / CRATE / "tests" / (name + ".rs")
            subprocess.run([*link, "--test", source, "-o", sub / (name + ".exe")], check=True, timeout=45)
    print(compiler_version, end="")


def checks():
    log = []
    for label in VARIANTS:
        for name in TESTS:
            process = subprocess.run([out / label / (name + ".exe"), "--test-threads=1"], check=True,
                capture_output=True, text=True, timeout=20)
            log.extend([f"{label} {name}", process.stdout.strip()])
    text = "\n\n".join(log) + "\n"
    (out / "checks.txt").write_text(text, encoding="utf-8")
    print(text, end="")


def bench():
    raw = out / "samples.csv"
    with raw.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("case", "pair", "variant", "tile_ns", "detile_ns", "backing_hash", "linear_hash", "bytes"))
        rows = []
        for case in args.case or CASES:
            witness = None
            for i in range(args.pairs):
                for label in VARIANTS if i % 2 == 0 else reversed(VARIANTS):
                    launch = subprocess.run([out / label / "benchmark.exe", case], check=True,
                        capture_output=True, text=True, timeout=12)
                    observed = launch.stdout.strip().split(",")
                    assert observed[0] == case and len(observed) == 6
                    if witness is None:
                        witness = observed[3:]
                    else:
                        assert witness == observed[3:], f"output mismatch on {case}"
                    row = [case, i + 1, label, *observed[1:]]
                    writer.writerow(row)
                    handle.flush()
                    rows.append(row)
    report = ["case,logical_bytes,baseline_tile_ns,candidate_tile_ns,tile_speedup,baseline_detile_ns,candidate_detile_ns,detile_speedup"]
    for case in args.case or CASES:
        samples = {label: [row for row in rows if row[0] == case and row[2] == label] for label in VARIANTS}
        base_tile, base_detile = [statistics.median(int(row[col]) for row in samples["baseline"]) for col in (3, 4)]
        new_tile, new_detile = [statistics.median(int(row[col]) for row in samples["candidate"]) for col in (3, 4)]
        logical_bytes = samples["baseline"][0][7]
        report.append(f"{case},{logical_bytes},{base_tile:.0f},{new_tile:.0f},{base_tile / new_tile:.2f},{base_detile:.0f},{new_detile:.0f},{base_detile / new_detile:.2f}")
    text = "\n".join(report) + "\n"
    (out / "summary.csv").write_text(text, encoding="utf-8")
    print(text, end="")


if args.phase == "build":
    build()
elif args.phase == "check":
    checks()
else:
    bench()
