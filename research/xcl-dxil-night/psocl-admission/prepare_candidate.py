# SPDX-License-Identifier: GPL-2.0-only
"""Prepare the scoped cross-lane reservation patch for exact XCL #1996."""

from difflib import unified_diff
from hashlib import sha256
from pathlib import Path
import argparse

from extract_legacy import WANTED_HEAD, WANTED_SOURCE, SOURCE


TURN = (
    "big_compile_turn(compile_slots(bytes), || big_compile_commit_free(big_compile_headroom(bytes)), "
    "super::pso_async::build_is_wanted)"
)
FREE = """/// That much commit is free (true when that is not known).
fn big_compile_commit_free(need: u64) -> bool {
    use windows_sys::Win32::System::SystemInformation::{GlobalMemoryStatusEx, MEMORYSTATUSEX};
    let mut m: MEMORYSTATUSEX = unsafe { std::mem::zeroed() };
    m.dwLength = std::mem::size_of::<MEMORYSTATUSEX>() as u32;
    unsafe { GlobalMemoryStatusEx(&mut m) == 0 || m.ullAvailPageFile >= need }
}
"""
REPLACEMENT = """/// Maximum additional commit available to this process right now.
fn driver_free_commit() -> Option<u64> {
    use windows_sys::Win32::System::SystemInformation::{GlobalMemoryStatusEx, MEMORYSTATUSEX};
    let mut m: MEMORYSTATUSEX = unsafe { std::mem::zeroed() };
    m.dwLength = std::mem::size_of::<MEMORYSTATUSEX>() as u32;
    (unsafe { GlobalMemoryStatusEx(&mut m) } != 0).then_some(m.ullAvailPageFile)
}

// Both size lanes share this admission estimate. The actual driver can use
// more or less memory. The running estimate is deliberately conservative.
static DRIVER_COMMIT_RESERVED: Mutex<u64> = Mutex::new(0);

struct DriverReservation(u64);

impl Drop for DriverReservation {
    fn drop(&mut self) {
        *DRIVER_COMMIT_RESERVED.lock().unwrap() -= self.0;
        BIG_COMPILES.cv.notify_all();
        GIANT_COMPILES.cv.notify_all();
    }
}

fn reserve_driver_commit(bytes: usize, free: impl FnOnce() -> Option<u64>) -> Option<DriverReservation> {
    let use_bytes = (bytes as u64).saturating_mul(512).max(1536 << 20);
    let mut reserved = DRIVER_COMMIT_RESERVED.lock().unwrap();
    let after = reserved.checked_add(use_bytes)?;
    if free().is_some_and(|free| free < big_compile_headroom(bytes).max(after)) {
        return None;
    }
    *reserved = after;
    Some(DriverReservation(use_bytes))
}

/// Preserve the lane limits and wanted priority while sharing a commit budget.
fn shared_driver_turn(slots: &'static Slots, bytes: usize, free: impl Fn() -> Option<u64>, wanted: impl Fn() -> bool)
    -> (Option<DriverReservation>, SlotGuard) {
    let reservation = std::cell::Cell::new(None);
    let slot = big_compile_turn(slots, || {
        let held = reserve_driver_commit(bytes, &free);
        let available = held.is_some();
        reservation.set(held);
        available
    }, wanted);
    // A wanted build keeps the existing commit bypass but contributes to
    // the estimate considered for later background builds.
    (reservation.into_inner().or_else(|| reserve_driver_commit(bytes, || None)), slot)
}
"""


def replace_once(text, before, after, count=1):
    if text.count(before) != count:
        raise ValueError(f"unexpected source matches for {before[:54]}")
    return text.replace(before, after)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    original = args.source.read_bytes()
    if sha256(original).hexdigest() != WANTED_SOURCE:
        raise ValueError("#1996 source does not match the pinned revision")
    args.output.mkdir(exist_ok=False)
    old = original.decode("utf-8")
    fixed = replace_once(old, TURN,
                         "shared_driver_turn(compile_slots(bytes), bytes, driver_free_commit, "
                         "super::pso_async::build_is_wanted)", 2)
    fixed = replace_once(fixed, FREE, REPLACEMENT)
    fixed = replace_once(fixed, "(3u64 << 30).max(dxil_len as u64 * 512)",
                         "(3u64 << 30).max((dxil_len as u64).saturating_mul(512))")
    patch = f"diff --git a/{SOURCE} b/{SOURCE}\n" + "".join(
        unified_diff(old.splitlines(keepends=True), fixed.splitlines(keepends=True),
                     fromfile=f"a/{SOURCE}", tofile=f"b/{SOURCE}")
    )
    patched = args.output / "real.rs"
    patched.write_bytes(fixed.encode("utf-8"))
    (args.output / "shared-psocl-commit.patch").write_bytes(patch.encode("utf-8"))
    print(f"{WANTED_HEAD} / patched {sha256(patched.read_bytes()).hexdigest()}")
