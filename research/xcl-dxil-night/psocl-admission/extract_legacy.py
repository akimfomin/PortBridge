# SPDX-License-Identifier: GPL-2.0-only
"""Extract the untouched current XCL slot code for the CPU differential."""

from hashlib import sha256
from pathlib import Path
import argparse
import re
import subprocess


PIN = "cbc296ab65a2661a61e3e2da109134bcd5319f60"
SOURCE = "crates/xcl/src/hle/d3d12x/real.rs"
WANTED_HEAD = "ae00ec73ed21cc4d266a8f42649eaeae3387ae84"
WANTED_SOURCE = "3ba091d7c9d198f90874aabd561cc463df2324268bca6582e25490eead4edc39"


def extract(original, wanted):
    text = original.decode("utf-8")
    patterns = [
        r"^fn huge_pso_concurrency\(",
        r"^fn env_count\(",
        r"^struct Slots \{",
        r"^impl Slots \{",
        r"^struct SlotGuard\(&'static Slots\);",
        r"^impl Drop for SlotGuard \{",
        r"^fn big_compile_turn\(",
        r"^fn big_compile_headroom\(",
    ]
    if wanted:
        patterns.insert(1, r"^fn huge_pso_wanted_concurrency\(")
    pieces = []
    for pattern in patterns:
        start, = re.finditer(pattern, text, re.MULTILINE)
        end = start.end() if pattern.endswith(";") else text.index("\n}", start.end()) + 2
        pieces.append(text[start.start():end])
    return sha256(original).hexdigest(), pieces


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--wanted-pr-source", type=Path)
    args = parser.parse_args()
    if args.wanted_pr_source:
        original = args.wanted_pr_source.read_bytes()
        if sha256(original).hexdigest() != WANTED_SOURCE:
            raise ValueError("#1996 source hash does not match its pin")
        pin = WANTED_HEAD
    else:
        original = subprocess.check_output(
            ["git", "-C", args.checkout.resolve(strict=True), "show", f"{PIN}:{SOURCE}"], timeout=10
        )
        pin = PIN
    origin, pieces = extract(original, bool(args.wanted_pr_source))
    prefix = "use std::sync::Mutex;\n"
    exports = """
pub fn attempt(lane: usize, bytes: usize, free: impl Fn() -> u64, wanted: impl Fn() -> bool)
    -> Option<impl Drop> {
    big_compile_turn(&LANES[lane], || free() >= big_compile_headroom(bytes), wanted)
}
pub fn held(lane: usize) -> usize { *LANES[lane].n.lock().unwrap() }
static LANES: [Slots; 2] = [
    Slots { n: Mutex::new(0), cv: std::sync::Condvar::new(), most: 1 },
    Slots { n: Mutex::new(0), cv: std::sync::Condvar::new(), most: 1 },
];
"""
    if args.wanted_pr_source:
        exports = exports.replace("-> Option<impl Drop>", "-> impl Drop").replace(
            "most: 1 },\n    Slots", "most: 1, wanted_most: 2 },\n    Slots"
        ).replace("most: 1 },\n];", "most: 1, wanted_most: 1 },\n];")
    out = prefix + "\n\n".join(pieces) + exports
    with args.output.open("x", newline="\n", encoding="utf-8") as outstream:
        outstream.write(out)
    print(f"{pin} / source SHA-256 {origin} / extracted SHA-256 {sha256(out.encode()).hexdigest()}")
