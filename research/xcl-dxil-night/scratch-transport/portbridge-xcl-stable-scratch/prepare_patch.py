# SPDX-License-Identifier: GPL-2.0-only
"""Generate the conservative first-piece scratch-retention experiment for XCL."""

import argparse
from difflib import unified_diff
from hashlib import sha256
from pathlib import Path


PIN = "17a984b8fd72e68dc43d1bc0b98e9446f1c78248"
SOURCE_SHA = "672c8cc98b881ebae69fc0be46a71d5401df21fbf415357112864c0cf0b95f81"
SOURCE = "crates/xcl/src/gpu/dxil/module/split.rs"


def change(body, old, new):
    if body.count(old) != 1:
        raise ValueError(f"unexpected source at {old[:80]!r}")
    return body.replace(old, new)


def variant(body):
    body = change(body, "struct Scratch {", """struct StableScratch {
    // Sorted by Value, in the same order as Edge::live.
    offsets: Vec<(Value, u32)>,
    dynamic_start: u32,
}

impl StableScratch {
    fn offset(&self, value: Value) -> Option<u32> {
        let index = self.offsets.binary_search_by_key(&value, |&(v, _)| v).ok()?;
        Some(self.offsets[index].1)
    }
}

struct Scratch {""")
    body = change(body, """        let pieces = (0..plan.blocks.len()).map(|i| self.make_piece(&plan, i, stride, threads, &prefix)).collect::<Option<Vec<_>>>()?;""",
                            """        let stable = self.m.stable_scratch(&plan)?;
        let pieces = (0..plan.blocks.len())
            .map(|i| self.make_piece(&plan, &stable, i, stride, threads, &prefix))
            .collect::<Option<Vec<_>>>()?;""")
    body = change(body, "fn make_piece(&self, plan: &Plan, stage: usize, stride: u32, threads: [u32; 3], prefix: &[u32])",
                        "fn make_piece(&self, plan: &Plan, stable: &StableScratch, stage: usize, stride: u32, threads: [u32; 3], prefix: &[u32])")
    body = change(body, """                let mut slot = 1;
                for &v in &edge.live {
                    let n = src.transport_words(v)?;""",
                        """                let mut slot = stable.dynamic_start;
                for &v in &edge.live {
                    if stable.offset(v).is_some() { continue; }
                    let n = src.transport_words(v)?;""")
    body = change(body, """            for handle in statics {
                src.rebuild_static(handle, &mut dst.m, &mut values)?;
            }
            let routes""", """            for handle in statics {
                src.rebuild_static(handle, &mut dst.m, &mut values)?;
            }

            if !stable.offsets.is_empty() {
                let mut used = HashSet::new();
                for b in &plan.blocks[stage] {
                    for &id in &src.blocks[b.0 as usize] {
                        src.insts[id as usize].op.for_each_operand(|v| {
                            if stable.offset(v).is_some() { used.insert(v); }
                        });
                    }
                }
                for &(original, slot) in &stable.offsets {
                    if !used.contains(&original) { continue; }
                    let n = src.transport_words(original)?;
                    let words: Vec<_> = (slot..slot + n).map(|word| {
                        let at = scratch.at(&mut dst.m, word);
                        dst.raw_load(scratch.uav, at, 1)[0]
                    }).collect();
                    values.insert(original, src.unpack(original, &words, &mut dst.m));
                }
            }
            let routes""")
    body = change(body, """            let mut slot = 1;
            for &v in &edge.live {
                let n = src.transport_words(v)?;
                if n != 0 {
                    let words = src.pack(v, *values.get(&v)?, &mut dst.m);
                    for (k, word) in words.into_iter().enumerate() {
                        let at = scratch.at(&mut dst.m, slot + k as u32);
                        dst.raw_store(scratch.uav, at, &[word]);
                    }
                    slot += n;
                }
            }""", """            let mut dynamic_slot = stable.dynamic_start;
            for &v in &edge.live {
                let n = src.transport_words(v)?;
                if n == 0 { continue; }
                let slot = if let Some(slot) = stable.offset(v) {
                    if stage != 0 { continue; }
                    slot
                } else {
                    let slot = dynamic_slot;
                    dynamic_slot += n;
                    slot
                };
                let words = src.pack(v, *values.get(&v)?, &mut dst.m);
                for (k, word) in words.into_iter().enumerate() {
                    let at = scratch.at(&mut dst.m, slot + k as u32);
                    dst.raw_store(scratch.uav, at, &[word]);
                }
            }""")
    body = change(body, """    fn static_handle(&self, v: Value) -> bool {""", """    fn stable_scratch(&self, plan: &Plan) -> Option<StableScratch> {
        let mut stable = StableScratch { offsets: Vec::new(), dynamic_start: 1 };
        // Two pieces cannot reuse a value over several crossings.
        if plan.blocks.len() < 3 { return Some(stable); }
        let (first, remaining) = plan.edges.split_first()?;
        let entry_blocks: HashSet<_> = plan.blocks[0].iter().copied().collect();
        for &value in &first.live {
            let id = inst(value)?;
            let ty = self.insts[id].ty;
            if !entry_blocks.contains(&self.def_block[id]) ||
                !matches!(self.types[ty.0 as usize], TypeDef::Int(1..=32) | TypeDef::Int(64) | TypeDef::Float)
            {
                continue;
            }
            // Every lane reaching a later piece carried this value out of
            // piece zero. Later stores start after these common slots.
            if remaining.iter().any(|edge| edge.live.binary_search(&value).is_err()) {
                continue;
            }
            stable.offsets.push((value, stable.dynamic_start));
            stable.dynamic_start = stable.dynamic_start.checked_add(self.transport_words(value)?)?;
        }
        Some(stable)
    }

    fn static_handle(&self, v: Value) -> bool {""")
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raw = args.source.read_bytes()
    if sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError("source does not match the pinned XCL #2080 file")
    old = raw.decode("utf-8")
    new = variant(old)
    diff = f"diff --git a/{SOURCE} b/{SOURCE}\n" + "".join(
        unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                     fromfile=f"a/{SOURCE}", tofile=f"b/{SOURCE}"))
    args.output.mkdir(exist_ok=False)
    (args.output / "xcl-2080-retain-scratch.patch").write_bytes(diff.encode("utf-8"))
    (args.output / "split.rs").write_bytes(new.encode("utf-8"))
    print(f"{PIN} -> {sha256(new.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
