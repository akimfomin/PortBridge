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
    let size = layout.alignment;
    let first = layout.offset(0, 256, 128, 0).unwrap();
    let dirty = first..first + size;
    let result = plan(&layout, 0, 0, true, std::slice::from_ref(&dirty)).unwrap();
    let Plan::Regions(boxes) = result else {
        panic!("expected partial copy");
    };
    assert_eq!(boxes.len(), 1);
    let region = boxes[0];
    println!("constexpr unsigned width = {}, height = {};", desc.width, desc.height);
    println!("constexpr D3D12_BOX dirty_region{{{}, {}, 0, {}, {}, 1}};",
             region.left, region.top, region.right, region.bottom);
}
