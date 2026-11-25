# SPDX-License-Identifier: GPL-2.0-only
"""Build the type-checked reservation path from the patched production source."""

from hashlib import sha256
from pathlib import Path
import argparse
import re

from extract_legacy import extract


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = args.source.read_bytes()
    origin, pieces = extract(source, True)
    body = source.decode("utf-8")
    start = body.index("static DRIVER_COMMIT_RESERVED:")
    end = body.index("#[cfg(test)]\nmod big_compile_tests", start)
    pieces.append(body[start:end])
    for name in ("BIG_COMPILES", "GIANT_COMPILES"):
        match, = re.finditer(rf"^static {name}: Slots = .*;$", body, re.MULTILINE)
        pieces.append(match[0])
    glue = """
pub fn attempt(lane: usize, bytes: usize, free: impl Fn() -> u64, wanted: impl Fn() -> bool)
    -> (impl Drop, impl Drop) {
    let (reserved, lane) = shared_driver_turn(&LANES[lane], bytes, || Some(free()), wanted);
    (reserved.expect("budget charge attached to the gate"), lane)
}
pub fn reserved() -> u64 { *DRIVER_COMMIT_RESERVED.lock().unwrap() }
static LANES: [Slots; 2] = [
    Slots { n: Mutex::new(0), cv: std::sync::Condvar::new(), most: 1, wanted_most: 2 },
    Slots { n: Mutex::new(0), cv: std::sync::Condvar::new(), most: 1, wanted_most: 1 },
];
"""
    generated = "use std::sync::Mutex;\n" + "\n\n".join(pieces) + glue
    with args.output.open("x", newline="\n", encoding="utf-8") as output:
        output.write(generated)
    print(f"patched source SHA-256 {origin} / extracted SHA-256 {sha256(generated.encode()).hexdigest()}")
