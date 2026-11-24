// SPDX-License-Identifier: GPL-2.0-only
#![allow(dead_code)]

mod bitstream;
mod module;

use std::io::{BufWriter, Write};

use module::{BinOp, Block, FnAttrs, Module, Pred, Value};

fn next(seed: &mut u64, bound: usize) -> usize {
    *seed ^= *seed << 13;
    *seed ^= *seed >> 7;
    *seed ^= *seed << 17;
    (*seed >> 32) as usize % bound
}

fn choose(seed: &mut u64, chain: &[Value], a: Value, b: Value) -> Value {
    match next(seed, chain.len() + 3) {
        0 | 1 => a,
        2 => b,
        i => chain[i - 3],
    }
}

fn build(mut seed: u64) -> Module {
    let count = 12 + next(&mut seed, 61);
    let mut m = Module::new();
    m.define_entry("main");
    let ty = m.i32();
    let void = m.void();
    let sink_ty = m.func_ty(void, &[ty]);
    let sink = m.declare("observe", sink_ty, FnAttrs::None);
    let zero = m.i32c(0);
    let one = m.i32c(1);
    let two = m.i32c(2);
    let a = m.i32c(23);
    let b = m.i32c(29);
    let equivalent = m.bin(BinOp::Add, a, zero);
    let header = m.new_block();
    let branch = m.new_block();
    let left = m.new_block();
    let right = m.new_block();
    let exit = m.new_block();
    m.br(header);
    m.set_block(header);
    let counter = m.phi(ty);
    let chain: Vec<_> = (0..count).map(|_| m.phi(ty)).collect();
    let again = m.cmp(Pred::Ne, counter, zero);
    m.cond_br(again, branch, exit);
    m.set_block(branch);
    let sub = m.bin(BinOp::Sub, counter, one);
    let select = match seed % 4 {
        0 => m.i1c(true),
        1 => m.i1c(false),
        _ => m.cmp(Pred::Eq, counter, two),
    };
    m.cond_br(select, left, right);
    m.set_block(left);
    m.br(header);
    m.set_block(right);
    m.br(header);
    m.set_block(exit);
    for &v in &chain {
        m.call(sink, &[v]);
    }
    m.ret();
    m.add_incoming(counter, two, Block(0));
    m.add_incoming(counter, sub, left);
    m.add_incoming(counter, sub, right);
    for (i, &phi) in chain.iter().enumerate() {
        let (entry, vleft, vright) = if i + 1 == count {
            (a, a, if seed & 1 == 0 { equivalent } else { a })
        } else if i > count / 2 {
            (a, chain[i + 1], chain[i + 1])
        } else {
            let entry = if next(&mut seed, 4) == 0 { b } else { a };
            (entry, choose(&mut seed, &chain, a, b), choose(&mut seed, &chain, a, b))
        };
        m.add_incoming(phi, entry, Block(0));
        m.add_incoming(phi, vleft, left);
        m.add_incoming(phi, vright, right);
    }
    m
}

fn main() {
    let path = std::env::args().nth(1).expect("output path");
    let mut output = BufWriter::new(std::fs::File::create(path).unwrap());
    for i in 1u64..=2_048 {
        let mut m = build(i.wrapping_mul(0x9E37_79B9_7F4A_7C15));
        m.optimize();
        let bitcode = m.to_bitcode("dxil-ms-dx", "");
        output.write_all(&(bitcode.len() as u32).to_le_bytes()).unwrap();
        output.write_all(&bitcode).unwrap();
    }
    output.flush().unwrap();
    println!("2,048 loop graphs compiled");
}
