// SPDX-License-Identifier: GPL-3.0-or-later
#[path = "../relay_fetch_pack.rs"]
mod pack;

const TILE: usize = 64 * 1024;

fn emit(name: &str, ranges: &[(usize, usize)], expected: (usize, u64)) {
    let mut stock_bytes = 0;
    let stock: Vec<_> = ranges.iter().map(|&(lo, hi)| {
        let piece = (0u8, lo, hi, stock_bytes);
        stock_bytes += (hi - lo) as u64;
        piece
    }).collect();
    let mut pieces = stock.clone();
    let (packed, bytes) = pack::pack_reads(&mut pieces, |a, b| a == b);
    assert_eq!((packed.len(), bytes), expected);
    print!("{{\"{name}\",{}, {}, {stock_bytes}, {bytes}, {{", stock.len(), packed.len());
    for &(_, lo, hi, at) in &stock {
        print!("{{{lo},{},{at}}},", hi - lo);
    }
    print!("}}, {{");
    for copy in packed {
        let (_, lo, _, at) = pieces[copy.first];
        print!("{{{lo},{},{at}}},", copy.end - lo);
    }
    print!("}}, {{");
    for (_, _, _, at) in pieces {
        print!("{at},");
    }
    println!("}}}},");
}

fn main() {
    emit("dense", &(0..16).map(|i| (i * TILE, (i + 1) * TILE)).collect::<Vec<_>>(), (1, (16 * TILE) as u64));
    emit("overlap", &[(0, 48 << 10), (32 << 10, TILE), (TILE, 96 << 10)], (1, 96 << 10));
    emit("sparse", &(0..16).map(|i| (2 * i * TILE, (2 * i + 1) * TILE)).collect::<Vec<_>>(), (16, (16 * TILE) as u64));
}
