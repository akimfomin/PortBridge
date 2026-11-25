# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage only the pinned fork's licensed host source and a narrow patch."""

import difflib
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parent
KNOWN_REPO = BASE.parent / "portbridge-night-fork-pipeline-wait"
GPU = Path("crates/victory-gpu/src")
HOST = GPU / "host.rs"
HELPER = GPU / "relay_fetch_pack.rs"
REVISIONS = {
    "reported": "2119b0e44c53aa9648307b0c5c73590290305b1f",
    "main": "310c6eb6c16822ab95076aad61fce19bba86bb98",
}


def replace(source, before, after):
    if source.count(before) != 1:
        raise ValueError(f"missing or multiple anchors: {before!r}")
    return source.replace(before, after)


def stage(rev):
    sha = REVISIONS[rev]
    original = BASE / rev / "upstream" / HOST
    candidate = BASE / rev / "candidate" / HOST
    original.parent.mkdir(parents=True, exist_ok=True)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    pinned = subprocess.check_output(["git", "-C", str(KNOWN_REPO), "show", f"{sha}:{HOST.as_posix()}"])
    original.write_bytes(pinned)
    before = pinned.decode("utf-8")
    after = replace(before, "use std::sync::atomic::{AtomicU32, Ordering};", "use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};")
    after = replace(after, "use std::sync::{Mutex, OnceLock};", "use std::sync::{Arc, Mutex, OnceLock};")

    after = replace(after, "/// The thread that lands flights ([`relay`]): as soon", """#[path = "relay_fetch_pack.rs"]
mod relay_fetch_pack;

/// Trial with one queue and the original logical merge pieces.
fn relay_pack_fetch() -> bool {
    static ON: OnceLock<bool> = OnceLock::new();
    *ON.get_or_init(|| std::env::var_os("VICTORY_RELAY_PACK_FETCH").is_some_and(|v| v == "1"))
}

/// Logical pieces, recorded copies, logical bytes, recorded bytes.
static RELAY_FETCH_PACK: [AtomicU64; 4] = [const { AtomicU64::new(0) }; 4];

/// The thread that lands flights ([`relay`]): as soon""")

    # Scope the edits to the relay path. The waited copy-back records on a
    # different schedule and its lifetime and counters remain its own.
    a = after.index("    fn relay_card_back(&self,")
    b = after.index("\n    }\n", a) + len("\n    }\n")
    method = after[a:b]
    method = replace(method, "        if fetch.is_none() {", """        let logical_total = total;
        let packed = relay_pack_fetch().then(|| {
            let (copies, packed_bytes) = relay_fetch_pack::pack_reads(&mut pieces, Arc::ptr_eq);
            total = packed_bytes;
            copies
        });
        if fetch.is_none() {""")
    method = replace(method, """                for (shadow, lo, hi, at) in &pieces {
                    list.CopyBufferRegion(&buffer, *at, &shadow.buffer, *lo as u64, (*hi - *lo) as u64);
                }""", """                let record = |(shadow, lo, _, at): &(Arc<crate::shadow::Shadow>, usize, usize, u64), end| {
                    list.CopyBufferRegion(&buffer, *at, &shadow.buffer, *lo as u64, (end - *lo) as u64);
                };
                if let Some(copies) = &packed {
                    for copy in copies {
                        record(&pieces[copy.first], copy.end);
                    }
                } else {
                    for piece in &pieces {
                        record(piece, piece.2);
                    }
                }""")
    method = replace(method, "        let mut title = Vec::new();", """        if let Some(copies) = &packed {
            for (counter, value) in RELAY_FETCH_PACK.iter().zip([
                pieces.len() as u64, copies.len() as u64, logical_total, total,
            ]) {
                counter.fetch_add(value, Ordering::Relaxed);
            }
        }
        let mut title = Vec::new();""")
    after = after[:a] + method + after[b:]

    after = replace(after, """            r[4] / 1000.0,
        );
    }
    if late_exact() {""", """            r[4] / 1000.0,
        );
        if relay_pack_fetch() {
            let [pieces, copies, requested, recorded] = RELAY_FETCH_PACK.each_ref().map(|c| {
                c.swap(0, Ordering::Relaxed) as f64 / frames
            });
            tracing::info!(
                "relay readback packing per frame: {pieces:.0} logical pieces, {copies:.0} recorded copies, \
                 {:.2} MB requested, {:.2} MB recorded",
                requested / 1e6,
                recorded / 1e6,
            );
        }
    }
    if late_exact() {""")

    candidate.write_bytes(after.encode("utf-8"))
    helper = BASE / rev / "candidate" / HELPER
    shutil.copyfile(BASE / HELPER.name, helper)
    patch = BASE / f"{rev}-relay-fetch-pack.patch"
    with patch.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"diff --git a/{HOST.as_posix()} b/{HOST.as_posix()}\n")
        handle.writelines(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                               "a/" + HOST.as_posix(), "b/" + HOST.as_posix()))
        handle.write(f"diff --git a/{HELPER.as_posix()} b/{HELPER.as_posix()}\nnew file mode 100644\n")
        handle.writelines(difflib.unified_diff([], helper.read_text(encoding="utf-8").splitlines(keepends=True),
                                               "/dev/null", "b/" + HELPER.as_posix()))
    print(f"{rev} {sha} host sha256 {hashlib.sha256(pinned).hexdigest()}")


if __name__ == "__main__":
    for name in sys.argv[1:] or REVISIONS:
        stage(name)
