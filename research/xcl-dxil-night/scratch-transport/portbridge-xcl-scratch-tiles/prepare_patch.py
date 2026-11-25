# SPDX-License-Identifier: GPL-2.0-only
"""Prepare a four-word tiled scratch experiment against XCL #2080."""

import argparse
from difflib import unified_diff
from hashlib import sha256
from pathlib import Path


SOURCE = "crates/xcl/src/gpu/dxil/module/split.rs"
PIN = "af2bd61e39344b0db2f37f14d950c78e0022e7df"


def replace_once(body, old, new):
    if body.count(old) != 1:
        raise ValueError(f"expected one exact occurrence of {old[:80]!r}")
    return body.replace(old, new)


def patch(body):
    first = body.index("struct Scratch {")
    last = body.index("\nimpl Shader {", first)
    body = body[:first] + """struct Scratch {
    uav: RawUav,
    group_base: Value,
    lane_bytes: Value,
    tag: Value,
    threads: u32,
    payload_capacity: u32,
}

impl Scratch {
    fn new(s: &mut Shader, group_bytes: u32, threads: u32, lane: Value) -> Self {
        let uav = s.raw_uav(0, 2);
        let cb = s.cbv(0, 2, 16);
        let zero = s.m.i32c(0);
        let ty = s.m.i32();
        let [width, height, _, _] = s.cbuffer_load_legacy(cb, zero, ty);
        let [x, y, z] = [0, 1, 2].map(|axis| s.group_id(axis));
        let row = s.m.bin(BinOp::Mul, z, height);
        let row = s.m.bin(BinOp::Add, row, y);
        let first = s.m.bin(BinOp::Mul, row, width);
        let group = s.m.bin(BinOp::Add, first, x);
        let group_size = s.m.i32c(group_bytes);
        let group_base = s.m.bin(BinOp::Mul, group, group_size);
        let four = s.m.i32c(4);
        let lane_bytes = s.m.bin(BinOp::Mul, lane, four);
        let tag = s.m.bin(BinOp::Add, group_base, lane_bytes);
        let payload_capacity = group_bytes / (threads * 4) - 1;
        Self { uav, group_base, lane_bytes, tag, threads, payload_capacity }
    }

    fn payload_at(&self, m: &mut Module, first: u32) -> Value {
        // Tag words remain lane-contiguous. Each payload tile is one to
        // four adjacent words per lane. All divergent edges use the same
        // lane spacing, even when some edges store fewer payload words.
        let offset = m.i32c((1 + first) * self.threads * 4);
        let width = m.i32c((self.payload_capacity - first).min(4));
        let lane_offset = m.bin(BinOp::Mul, self.lane_bytes, width);
        let at = m.bin(BinOp::Add, self.group_base, offset);
        m.bin(BinOp::Add, at, lane_offset)
    }

    fn tiles(words: u32) -> impl Iterator<Item = (u32, u32)> {
        (0..words).step_by(4).map(move |first| (first, (words - first).min(4)))
    }
}
""" + body[last:]
    body = replace_once(body, """        let mut stride = 1;
        for edge in &plan.edges {
            let mut words = 1;
            for &v in &edge.live {
                words += self.m.transport_words(v)?;
            }
            stride = stride.max(words);
        }
        let pieces = (0..plan.blocks.len()).map(|i| self.make_piece(&plan, i, stride, threads, &prefix)).collect::<Option<Vec<_>>>()?;
        Some(DispatchChain { pieces, dwords_per_group: stride.checked_mul(threads[0])? })
""", """        let edge_words = plan.edges.iter().map(|edge| {
            edge.live.iter().try_fold(0u32, |words, &v| words.checked_add(self.m.transport_words(v)?))
        }).collect::<Option<Vec<_>>>()?;
        let stride = edge_words.iter().copied().max().unwrap_or(0).checked_add(1)?;
        let dwords_per_group = stride.checked_mul(threads[0])?;
        let group_bytes = dwords_per_group.checked_mul(4).filter(|bytes| *bytes != 0)?;
        let pieces = (0..plan.blocks.len())
            .map(|i| self.make_piece(&plan, &edge_words, i, group_bytes, threads, &prefix))
            .collect::<Option<Vec<_>>>()?;
        Some(DispatchChain { pieces, dwords_per_group })
""")
    body = replace_once(body,
                        "fn make_piece(&self, plan: &Plan, stage: usize, stride: u32, threads: [u32; 3], prefix: &[u32])",
                        "fn make_piece(&self, plan: &Plan, edge_words: &[u32], stage: usize, group_bytes: u32, threads: [u32; 3], prefix: &[u32])")
    body = replace_once(body, "Scratch::new(&mut dst, stride, threads[0], lane)",
                        "Scratch::new(&mut dst, group_bytes, threads[0], lane)")
    body = replace_once(body, "let mut slot = 1;\n                for &v in &edge.live {",
                        """let mut payload = Vec::new();
                for (first, width) in Scratch::tiles(edge_words[index]) {
                    let at = scratch.payload_at(&mut dst.m, first);
                    payload.extend(dst.raw_load(scratch.uav, at, (1u8 << width) - 1));
                }
                let mut slot = 0;
                for &v in &edge.live {""")
    body = replace_once(body, """                    let words = (slot..slot + n).map(|word| {
                        let at = scratch.at(&mut dst.m, word);
                        dst.raw_load(scratch.uav, at, 1)[0]
                    }).collect();
                    incoming.entry(v).or_default().push((words, bridge));
                    slot += n;""", """                    let end = slot + n as usize;
                    incoming.entry(v).or_default().push((payload.get(slot..end)?.to_vec(), bridge));
                    slot = end;""")
    body = replace_once(body, """        for edge in &plan.edges {
            let Some(&(b, tag)) = exits.get(&(edge.from, edge.to)) else { continue };
            dst.m.set_block(b);
            let mut slot = 1;
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
            }""", """        for (index, edge) in plan.edges.iter().enumerate() {
            let Some(&(b, tag)) = exits.get(&(edge.from, edge.to)) else { continue };
            dst.m.set_block(b);
            let mut payload = Vec::with_capacity(edge_words[index] as usize);
            for &v in &edge.live {
                if src.transport_words(v)? != 0 {
                    payload.extend(src.pack(v, *values.get(&v)?, &mut dst.m));
                }
            }
            if payload.len() != edge_words[index] as usize { return None; }
            for (first, width) in Scratch::tiles(edge_words[index]) {
                let at = scratch.payload_at(&mut dst.m, first);
                dst.raw_store(scratch.uav, at, &payload[first as usize..(first + width) as usize]);
            }""")
    if body.count("scratch.base") != 3:
        raise ValueError("unexpected tag layout")
    return body.replace("scratch.base", "scratch.tag")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    original = args.source.read_bytes()
    before = original.decode("utf-8")
    after = patch(before)
    args.output.mkdir(exist_ok=False)
    diff = f"diff --git a/{SOURCE} b/{SOURCE}\n" + "".join(
        unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                     fromfile=f"a/{SOURCE}", tofile=f"b/{SOURCE}"))
    (args.output / "xcl-2080-scratch-tiles.patch").write_bytes(diff.encode("utf-8"))
    (args.output / "split.rs").write_bytes(after.encode("utf-8"))
    print(f"{PIN}: source {sha256(original).hexdigest()}, candidate {sha256(after.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
