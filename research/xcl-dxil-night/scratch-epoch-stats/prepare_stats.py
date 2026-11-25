# SPDX-License-Identifier: GPL-2.0-only
"""Prepare opt-in XCL scratch allocation size/lifetime counters."""

import argparse
from difflib import unified_diff
from hashlib import sha256
from pathlib import Path


PIN = "12cd2fa9a25eb7e04b650ddf3080489981aa40a0"
FILE = "crates/xcl/src/hle/d3d12x/real/dispatch_chain.rs"
SHA = "2a79c5276d37073d54f9171a6916387bd29abf671247f058c52711c0c487370b"

BUCKETS = """#[derive(Clone, Copy)]
struct ScratchAllocation {
    requested_bytes: u64,
    create_ns: u64,
}

#[derive(Default)]
struct ScratchEpoch {
    counts: [u64; 4],
    requested_bytes: u64,
    create_ns: u64,
}

fn scratch_epoch(samples: impl Iterator<Item = ScratchAllocation>) -> ScratchEpoch {
    let mut epoch = ScratchEpoch::default();
    for allocation in samples {
        let bucket = match allocation.requested_bytes {
            0..=65_536 => 0,
            65_537..=262_144 => 1,
            262_145..=1_048_576 => 2,
            _ => 3,
        };
        epoch.counts[bucket] = epoch.counts[bucket].saturating_add(1);
        epoch.requested_bytes = epoch.requested_bytes.saturating_add(allocation.requested_bytes);
        epoch.create_ns = epoch.create_ns.saturating_add(allocation.create_ns);
    }
    epoch
}
"""


def change(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"unexpected pinned context {old[:70]!r}")
    return source.replace(old, new)


def apply(old):
    body = change(old, "static DISPATCHES: AtomicU64 = AtomicU64::new(0);",
                  """static DISPATCHES: AtomicU64 = AtomicU64::new(0);
static SCRATCH_ALLOCATION_FAILURES: AtomicU64 = AtomicU64::new(0);

fn scratch_stats_enabled() -> bool {
    static ENABLED: OnceLock<bool> = OnceLock::new();
    *ENABLED.get_or_init(|| matches!(std::env::var("XCL_SCRATCH_ALLOCATION_STATS").as_deref(), Ok("1")))
}""")
    body = change(body, """        PROGRAMS.load(Ordering::Relaxed), PIECES.load(Ordering::Relaxed), DISPATCHES.load(Ordering::Relaxed));
}""", """        PROGRAMS.load(Ordering::Relaxed), PIECES.load(Ordering::Relaxed), DISPATCHES.load(Ordering::Relaxed));
    if scratch_stats_enabled() {
        let active: Vec<_> = RECORDINGS.lock().unwrap().values()
            .map(|batch| scratch_epoch(batch.iter().filter_map(|record| record.allocation)))
            .collect();
        for epoch in active { log_scratch_epoch("active", epoch); }
        crate::xlog_info!("compute scratch failed creates={}", SCRATCH_ALLOCATION_FAILURES.load(Ordering::Relaxed));
    }
}""")
    body = change(body, "struct Recording {", BUCKETS + """
fn log_scratch_epoch(kind: &str, epoch: ScratchEpoch) {
    if epoch.counts == [0; 4] { return; }
    crate::xlog_info!("compute scratch {kind}: <=64KiB={} <=256KiB={} <=1MiB={} >1MiB={} requested_bytes={} create_ns={}",
        epoch.counts[0], epoch.counts[1], epoch.counts[2], epoch.counts[3],
        epoch.requested_bytes, epoch.create_ns);
}

struct Recording {""")
    body = change(body, """    first: ID3D12PipelineState,
    chain: Arc<Chain>,
}""", """    first: ID3D12PipelineState,
    chain: Arc<Chain>,
    allocation: Option<ScratchAllocation>,
}""")
    body = change(body, """    let recordings = RECORDINGS.lock().unwrap().remove(&allocator);
    drop(recordings);""", """    let recordings = RECORDINGS.lock().unwrap().remove(&allocator);
    let epoch = recordings.as_ref().filter(|_| scratch_stats_enabled())
        .map(|batch| scratch_epoch(batch.iter().filter_map(|record| record.allocation)));
    drop(recordings);
    if let Some(epoch) = epoch { log_scratch_epoch("retired", epoch); }""")
    body = change(body, """        .and_then(|n| scratch_buffer(&chain.builder.device, n));
    let Some(scratch) = scratch else {""", """        .and_then(|n| {
            let started = scratch_stats_enabled().then(std::time::Instant::now);
            let resource = scratch_buffer(&chain.builder.device, n);
            let allocation = started.map(|start| {
                if resource.is_none() {
                    SCRATCH_ALLOCATION_FAILURES.fetch_add(1, Ordering::Relaxed);
                }
                ScratchAllocation {
                    requested_bytes: n,
                    create_ns: start.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                }
            });
            resource.map(|scratch| (scratch, allocation))
        });
    let Some((scratch, allocation)) = scratch else {""")
    return change(body, """    let held = Arc::new(Recording { scratch, first, chain });""",
                        """    let held = Arc::new(Recording { scratch, first, chain, allocation });""")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raw = args.source.read_bytes()
    if sha256(raw).hexdigest() != SHA:
        raise ValueError("the source is not the pinned XCL #2080 dispatch_chain.rs")
    old = raw.decode()
    new = apply(old)
    patch = f"diff --git a/{FILE} b/{FILE}\n" + "".join(unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{FILE}", tofile=f"b/{FILE}"))
    args.output.mkdir(exist_ok=False)
    (args.output / "scratch-epoch-stats.patch").write_bytes(patch.encode())
    (args.output / "dispatch_chain.rs").write_bytes(new.encode())
    print(f"{PIN} candidate {sha256(new.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
