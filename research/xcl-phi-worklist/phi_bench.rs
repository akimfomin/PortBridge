// SPDX-License-Identifier: GPL-2.0-only
#![allow(dead_code)]

mod bitstream;
mod module;

use std::path::Path;
use std::time::Instant;

use module::{BinOp, Block, FnAttrs, Module, Pred};

fn build(count: usize, shape: &str) -> (Module, Block, usize) {
    let mut m = Module::new();
    m.define_entry("main");
    let ty = m.i32();
    let void = m.void();
    let sink_ty = m.func_ty(void, &[ty, ty, ty]);
    let sink = m.declare("observe", sink_ty, FnAttrs::None);
    let a = m.i32c(23);
    let b = m.i32c(29);
    let zero = m.i32c(0);
    let one = m.i32c(1);
    let three = m.i32c(3);
    let tail = if shape == "after-cse" { m.bin(BinOp::Add, a, zero) } else { a };
    let header = m.new_block();
    let latch = m.new_block();
    let exit = m.new_block();
    m.br(header);
    m.set_block(header);
    let counter = m.phi(ty);
    let left = m.phi(ty);
    let right = m.phi(ty);
    let chain: Vec<_> = (0..count).map(|_| m.phi(ty)).collect();
    let test = m.cmp(Pred::Ne, counter, zero);
    m.cond_br(test, latch, exit);
    m.set_block(latch);
    let sub = m.bin(BinOp::Sub, counter, one);
    m.br(header);
    m.set_block(exit);
    let root = if shape == "forward" { chain[count - 1] } else { chain[0] };
    m.call(sink, &[root, left, right]);
    m.ret();
    for (phi, from_entry, from_latch) in [(counter, three, sub), (left, a, right), (right, b, left)] {
        m.add_incoming(phi, from_entry, Block(0));
        m.add_incoming(phi, from_latch, latch);
    }
    for (i, &phi) in chain.iter().enumerate() {
        let input = match shape {
            "forward" if i == 0 => tail,
            "forward" => chain[i - 1],
            "persistent" if i + 1 == count => b,
            _ => chain.get(i + 1).copied().unwrap_or(tail),
        };
        m.add_incoming(phi, a, Block(0));
        m.add_incoming(phi, input, latch);
    }
    let retained = if shape == "persistent" { count + 3 } else { 3 };
    (m, header, retained)
}

fn main() {
    let args: Vec<_> = std::env::args().collect();
    assert_eq!(args.len(), 5, "usage: SHAPE PHIS REPEATS BITCODE_OUT");
    let shape = &args[1];
    assert!(matches!(shape.as_str(), "forward" | "reverse" | "after-cse" | "persistent"));
    let count = args[2].parse::<usize>().unwrap();
    let repeats = args[3].parse::<usize>().unwrap();
    assert!((1..=16_384).contains(&count) && (1..=15).contains(&repeats));
    let path = Path::new(&args[4]);
    let mut times = Vec::with_capacity(repeats);
    let mut first = None;
    for _ in 0..repeats {
        let (mut module, header, retained) = build(count, shape);
        let start = Instant::now();
        module.optimize();
        times.push(start.elapsed().as_secs_f64() * 1e3);
        // Three live, genuinely nontrivial loop PHIs must remain plus cmp + cond_br.
        // In the persistent shape, the extra chain is deliberately nontrivial too.
        assert_eq!(module.block_insts(header).len(), retained + 2);
        let output = module.to_bitcode("dxil-ms-dx", "");
        if let Some(ref previous) = first {
            assert_eq!(previous, &output);
        } else {
            first = Some(output);
        }
    }
    std::fs::write(path, first.as_ref().unwrap()).unwrap();
    times.sort_by(f64::total_cmp);
    println!(
        "shape={shape} phis={count} median_ms={:.6} min_ms={:.6} max_ms={:.6} times={times:?}",
        times[times.len() / 2], times[0], times[times.len() - 1],
    );
}
