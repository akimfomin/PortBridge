// SPDX-License-Identifier: GPL-2.0-only
#![allow(dead_code)]

mod bitstream;
mod container;
mod module;
mod shader;

// The production Shader builder uses only this constant. Microsoft dxv.exe
// validates the resulting containers as a separate CPU-only step.
mod validate { pub const VALVER: (u32, u32) = (1, 8); }

use container::Stage;
use module::{BinOp, Block, Pred, Value};
use shader::Shader;
use std::path::Path;

fn ring(width: usize, two_seeds: bool, constant: bool) -> Vec<u8> {
    let mut shader = Shader::new(Stage::Compute, (6, 6));
    let sink = shader.raw_uav(0, 0);
    let lane = shader.thread_id(0);
    let m = &mut shader.m;
    let i32_ty = m.i32();
    let a = m.i32c(17);
    let b = m.i32c(53);
    let seed = if constant { a } else { m.bin(BinOp::Xor, lane, a) };
    let one = m.i32c(1);
    let zero = m.i32c(0);
    let three = m.i32c(3);
    let masked = m.bin(BinOp::And, lane, three);
    let initial_count = m.bin(BinOp::Add, masked, one);
    let stride = m.i32c((4 * width) as u32);
    let start_offset = m.bin(BinOp::Mul, lane, stride);
    let head = m.new_block();
    let body = m.new_block();
    let exit = m.new_block();
    m.br(head);
    m.set_block(head);
    let remaining = m.phi(i32_ty);
    let members: Vec<Value> = (0..width).map(|_| m.phi(i32_ty)).collect();
    let again = m.cmp(Pred::Ne, remaining, zero);
    m.cond_br(again, body, exit);
    m.set_block(body);
    let next_count = m.bin(BinOp::Sub, remaining, one);
    m.br(head);
    m.add_incoming(remaining, initial_count, Block(0));
    m.add_incoming(remaining, next_count, body);
    for (i, &value) in members.iter().enumerate() {
        m.add_incoming(value, if two_seeds && i % 2 != 0 { b } else { seed }, Block(0));
        m.add_incoming(value, members[(i + 1) % width], body);
    }
    m.set_block(exit);
    for (i, &value) in members.iter().enumerate() {
        let delta = shader.m.i32c((4 * i) as u32);
        let offset = shader.m.bin(BinOp::Add, start_offset, delta);
        shader.raw_store(sink, offset, &[value]);
    }
    shader.finish([32, 1, 1], None)
}

fn main() {
    let path = std::env::args().nth(1).expect("output directory");
    let path = Path::new(&path);
    for (shape, width, two, constant) in [
        ("constant2", 2, false, true),
        ("dynamic2", 2, false, false),
        ("dynamic16", 16, false, false),
        ("dynamic64", 64, false, false),
        ("two-seeds16", 16, true, false),
    ] {
        let bytes = ring(width, two, constant);
        println!("{shape} {} bytes", bytes.len());
        std::fs::write(path.join(format!("{shape}.dxil")), bytes).unwrap();
    }
}
