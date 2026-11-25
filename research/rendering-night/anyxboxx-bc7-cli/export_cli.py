"""Stage an exact fresh-process CLI export comparison. Benchmarks run only on `time`."""

import argparse
import csv
import hashlib
from pathlib import Path
import statistics
import struct
import subprocess
import tempfile
from time import perf_counter_ns
import zlib


PIN = "b92a71b9308e76f8ec9059c01d6e18f21611dc20"
CRATE = "rust/anyxboxx-texture/src"
CASES = {"rgba4k": (3840, 2160), "rgba1080_odd": (1919, 1079)}
VARIANTS = ("baseline", "candidate")
HEADER_WIDTHS = ((4, 0, 0), (6, 0, 0), (6, 0, 0), (6, 0, 0),
                 (0, 2, 1), (0, 2, 0), (0, 0, 0), (6, 0, 0))
SIGNATURE = b"\x89PNG\r\n\x1a\n"
MASK64 = (1 << 64) - 1

folder = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("phase", choices=("build", "time"))
parser.add_argument("--repo", type=Path, default=Path.cwd())
parser.add_argument("--output", type=Path, default=folder / "generated")
parser.add_argument("--rustc", default="rustc")
parser.add_argument("--linker")
parser.add_argument("--pairs", type=int, choices=(1, 2, 3, 4, 5), default=4)
parser.add_argument("--case", choices=CASES, action="append")
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)


def build():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.repo, text=True).strip()
    assert head == PIN, head
    entry = f"{CRATE}/main.rs"
    original = subprocess.check_output(["git", "show", f"{PIN}:{entry}"], cwd=args.repo,
                                       text=True, encoding="utf-8")
    assert original == (args.repo / entry).read_text(encoding="utf-8"), "entry point changed"
    rust = [args.rustc, "--edition=2021", "-C", "opt-level=3", "--crate-name", "anyxboxx_texture"]
    if args.linker:
        rust += ["-C", f"linker={args.linker}"]
    for variant in VARIANTS:
        library = out / f"libanyxboxx_{variant}.rlib"
        if not library.is_file():
            raise SystemExit("Build the same-pin libraries with run_proof.py build first")
        binary = out / f"cli-{variant}.exe"
        subprocess.run([*rust, "--extern", f"anyxboxx_texture={library}", args.repo / entry,
                        "-o", binary], check=True, timeout=30)


def blocks(width, height):
    """Use the same mode schedule, seed, and xorshift64 stream as fixture.rs."""
    state = 0x69BE_BADA_AC90_7221

    def random_word():
        nonlocal state
        state ^= (state << 13) & MASK64
        state ^= state >> 7
        state ^= (state << 17) & MASK64
        return state

    count = ((width + 3) // 4) * ((height + 3) // 4)
    result = bytearray(count * 16)
    for index in range(count):
        mode = index % len(HEADER_WIDTHS)
        partition_bits, rotation_bits, selection_bits = HEADER_WIDTHS[mode]
        partition = random_word() & ((1 << partition_bits) - 1)
        rotation = random_word() & ((1 << rotation_bits) - 1)
        selection = random_word() & ((1 << selection_bits) - 1)
        mode_bits = mode + 1
        rotation_at = mode_bits + partition_bits
        selection_at = rotation_at + rotation_bits
        header_bits = selection_at + selection_bits
        fields = (1 << mode) | (partition << mode_bits) | (rotation << rotation_at) | (selection << selection_at)
        payload = (random_word() << 64) | random_word()
        offset = 16 * index
        result[offset:offset + 16] = ((payload >> header_bits << header_bits) | fields).to_bytes(16, "little")
    return result


def validate_png(data, width, height):
    assert data[:len(SIGNATURE)] == SIGNATURE
    view = memoryview(data)
    pos = len(SIGNATURE)
    chunks = {}
    while pos < len(data):
        size, kind = struct.unpack_from(">I4s", view, pos)
        stored_at = pos + 8 + size
        want_crc, = struct.unpack_from(">I", view, stored_at)
        assert zlib.crc32(view[pos + 4:stored_at]) == want_crc
        assert kind not in chunks
        chunks[kind] = view[pos + 8:stored_at]
        pos = stored_at + 4
    assert list(chunks) == [b"IHDR", b"IDAT", b"IEND"] and pos == len(data)
    assert bytes(chunks[b"IHDR"]) == struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    assert len(chunks[b"IEND"]) == 0
    pixels = zlib.decompress(chunks[b"IDAT"])
    stride = width * 4 + 1
    assert len(pixels) == stride * height and all(pixels[y * stride] == 0 for y in range(height))


def measure(case, width, height, raw):
    scratch = Path(tempfile.mkdtemp(prefix="bc7-cli-", dir=out)).resolve()
    assert scratch.parent == out
    source = scratch / "generated.bc7"
    expected = None
    samples = {variant: [] for variant in VARIANTS}
    try:
        data = blocks(width, height)
        source_hash = hashlib.sha256(data).hexdigest()
        source.write_bytes(data)
        del data
        for pair in range(args.pairs):
            for variant in VARIANTS if pair % 2 == 0 else reversed(VARIANTS):
                exported = scratch / f"result-{pair}-{variant}.png"
                status, digest, size, verified = "spawn-error", "", 0, False
                command = [out / f"cli-{variant}.exe", "bc7", source, str(width), str(height), exported]
                start = perf_counter_ns()
                try:
                    child = subprocess.run(command, capture_output=True, timeout=20)
                    ns = perf_counter_ns() - start
                    status = child.returncode
                    if status != 0:
                        raise RuntimeError(f"{case} {variant} exited {status}")
                    data = exported.read_bytes()
                    digest = hashlib.sha256(data).hexdigest()
                    size = len(data)
                    if expected is None:
                        validate_png(data, width, height)
                        expected = (digest, size)
                    assert (digest, size) == expected, f"PNG mismatch on {case}"
                    verified = True
                    samples[variant].append(ns)
                    del data
                except subprocess.TimeoutExpired:
                    status = "timeout"
                    raise
                finally:
                    if not isinstance(status, int):
                        ns = perf_counter_ns() - start
                    raw.writerow((case, pair + 1, variant, status, verified, ns, source_hash, digest, size))
                    exported.unlink(missing_ok=True)
    finally:
        source.unlink(missing_ok=True)
        scratch.rmdir()
    return tuple(statistics.median(samples[variant]) for variant in VARIANTS)


def time():
    rows = ["case,baseline_ns,candidate_ns,speedup"]
    with (out / "cli-samples.csv").open("w", newline="", encoding="utf-8") as stream:
        raw = csv.writer(stream)
        raw.writerow(("case", "pair", "variant", "exit", "verified", "ns", "input_sha256", "png_sha256", "png_bytes"))
        for name in args.case or CASES:
            baseline, candidate = measure(name, *CASES[name], raw)
            rows.append(f"{name},{baseline:.0f},{candidate:.0f},{baseline / candidate:.2f}")
            stream.flush()
    report = "\n".join(rows) + "\n"
    (out / "cli-summary.csv").write_text(report, encoding="utf-8")
    print(report, end="")


{"build": build, "time": time}[args.phase]()
