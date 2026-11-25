// SPDX-License-Identifier: GPL-3.0-or-later
#![allow(dead_code)]
mod copy_plan;
mod texture;

use copy_plan::{Plan, plan};
use texture::{Desc, Dimension, Layout, Swizzle};

fn main() {
    let desc = Desc {
        dimension: Dimension::Tex2d,
        width: 512,
        height: 512,
        depth: 1,
        mips: 1,
        element_bytes: 4,
        block: 1,
        samples: 1,
        swizzle: Swizzle::SW_64KB_D,
    };
    let layout = Layout::new(&desc).unwrap();
    let tile = layout.alignment;
    assert_eq!(tile, 65_536);
    for (name, numbers) in [
        ("one-tile", &[6u64][..]),
        ("four-adjacent", &[5, 6, 9, 10]),
        ("four-separated", &[0, 2, 8, 10]),
        ("eight-separated", &[0, 2, 4, 6, 8, 10, 12, 14]),
    ] {
        let dirty: Vec<_> = numbers.iter().map(|&n| n * tile..(n + 1) * tile).collect();
        let Plan::Regions(boxes) = plan(&layout, 0, 0, true, &dirty).unwrap() else {
            panic!("expected partial copy for {name}");
        };
        print!("    Case{{\"{name}\", {}, {}, {{{{", numbers.len() as u64 * tile, boxes.len());
        for r in boxes {
            print!("{{{}, {}, 0, {}, {}, 1}},", r.left, r.top, r.right, r.bottom);
        }
        println!("}}}}}},");
    }
}
