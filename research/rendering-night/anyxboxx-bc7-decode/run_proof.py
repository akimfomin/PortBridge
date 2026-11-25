import argparse
import csv
from pathlib import Path
import statistics
import subprocess


PIN = "b92a71b9308e76f8ec9059c01d6e18f21611dc20"
CRATE = "rust/anyxboxx-texture"
FILES = ("bc7.rs", "lib.rs", "png.rs", "tiles.rs")
VARIANTS = ("baseline", "candidate")
CASES = ("rgba4k", "rgba1080_odd", "thin_crop", "block")
folder = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("phase", choices=("build", "check", "bench"))
parser.add_argument("--repo", type=Path, default=Path.cwd())
parser.add_argument("--output", type=Path, default=folder / "generated")
parser.add_argument("--rustc", default="rustc")
parser.add_argument("--linker")
parser.add_argument("--pairs", type=int, choices=(1, 2, 3, 4, 5), default=4)
parser.add_argument("--case", choices=CASES, action="append")
args = parser.parse_args()
repo = args.repo.resolve()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)


def build():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    assert head == PIN, head
    compiler = [args.rustc, "--edition=2021", "-C", "opt-level=3"]
    if args.linker:
        compiler += ["-C", f"linker={args.linker}"]
    version = subprocess.check_output([args.rustc, "--version", "--verbose"], text=True, timeout=10)
    (out / "compiler.txt").write_text(version, encoding="utf-8")
    original = out / "baseline"
    original.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        data = subprocess.check_output(["git", "show", f"{PIN}:{CRATE}/src/{name}"], cwd=repo)
        (original / name).write_bytes(data)

    libraries = []
    for label, source in (("baseline", original), ("candidate", repo / CRATE / "src")):
        name = f"anyxboxx_{label}"
        lib = out / f"lib{name}.rlib"
        subprocess.run([*compiler, "--crate-type", "rlib", "--crate-name", name, source / "lib.rs",
                        "-o", lib], check=True, timeout=60)
        libraries.extend(["--extern", f"{name}={lib}"])
        subprocess.run([*compiler, "--test", "--extern", f"anyxboxx_texture={lib}",
                        repo / CRATE / "tests/bc7_surface_copy.rs", "-o", out / f"unit-{label}.exe"],
                       check=True, timeout=60)
    for label, cfg in (("check", ["--cfg", "count_allocations"]), ("bench", [])):
        subprocess.run([*compiler, *libraries, *cfg, folder / "fixture.rs", "-o", out / f"{label}.exe"],
                       check=True, timeout=60)
    print(version, end="")


def check():
    log = []
    for label in VARIANTS:
        unit = subprocess.run([out / f"unit-{label}.exe", "--test-threads=1"], check=True,
                              capture_output=True, text=True, timeout=15)
        log.extend([f"unit_{label}", unit.stdout.strip()])
    proof = subprocess.run([out / "check.exe"], check=True, capture_output=True, text=True, timeout=15)
    log.append(proof.stdout.strip())
    report = "\n".join(log) + "\n"
    (out / "checks.txt").write_text(report, encoding="utf-8")
    print(report, end="")


def bench():
    raw = out / "samples.csv"
    results = {name: {label: [] for label in VARIANTS} for name in (args.case or CASES)}
    with raw.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("case", "pair", "variant", "ns_per_decode_surface", "output_hash"))
        for name, samples in results.items():
            witness = None
            for i in range(args.pairs):
                for label in VARIANTS if i % 2 == 0 else reversed(VARIANTS):
                    arm = subprocess.run([out / "bench.exe", name, label], check=True,
                                         capture_output=True, text=True, timeout=20)
                    case, variant, ns, digest = arm.stdout.strip().split(",")
                    assert (case, variant) == (name, label)
                    if witness is None:
                        witness = digest
                    else:
                        assert witness == digest, name
                    samples[label].append(int(ns))
                    writer.writerow((name, i + 1, label, ns, digest))
                    handle.flush()
    summary = ["case,baseline_ns,candidate_ns,speedup"]
    for name, samples in results.items():
        original, patched = (statistics.median(samples[label]) for label in VARIANTS)
        summary.append(f"{name},{original:.0f},{patched:.0f},{original / patched:.2f}")
    report = "\n".join(summary) + "\n"
    (out / "summary.csv").write_text(report, encoding="utf-8")
    print(report, end="")


{"build": build, "check": check, "bench": bench}[args.phase]()
