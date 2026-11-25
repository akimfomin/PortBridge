// SPDX-License-Identifier: GPL-3.0-or-later
#![allow(dead_code)]
#[path = "../portbridge-victory-dirty-tile-upload/copy_plan.rs"]
mod copy_plan;
#[path = "../portbridge-victory-dirty-tile-upload/texture.rs"]
mod texture;

use copy_plan::{Plan, plan};
use texture::{Desc, Dimension, Layout, Swizzle};

fn main() {
    let desc = Desc {
        dimension: Dimension::Tex2d,
        width: 1024,
        height: 1024,
        depth: 2,
        mips: 2,
        element_bytes: 16,
        block: 4,
        samples: 1,
        swizzle: Swizzle::SW_64KB_D,
    };
    let layout = Layout::new(&desc).expect("valid synthetic BC7 layout");
    let changed_slice = 1;
    let changed_mip = 0;
    let [tile_w, tile_h, _] = layout.block;
    let m = &layout.mips[changed_mip as usize];
    assert!(m.tail.is_none() && 2 * tile_w < m.width && 2 * tile_h < m.height);
    assert_eq!(layout.alignment, 65536);
    let base = u64::from(changed_slice) * layout.slice_size + m.offset;
    let element = layout.offset(changed_mip, tile_w, tile_h, changed_slice).unwrap();
    let start = base + (element - base) / layout.alignment * layout.alignment;
    let dirty = start..start + layout.alignment;
    let plan_for = |mip, slice| plan(&layout, mip, slice, true, std::slice::from_ref(&dirty)).unwrap();
    let Plan::Regions(boxes) = plan_for(changed_mip, changed_slice) else {
        panic!("expected one partial copy");
    };
    assert_eq!(boxes.len(), 1);
    let b = boxes[0];
    assert_eq!([b.left, b.top, b.right, b.bottom],
               [tile_w * 4, tile_h * 4, tile_w * 8, tile_h * 8]);
    assert!([b.left, b.top, b.right, b.bottom].iter().all(|n| n.is_multiple_of(16)));
    assert_eq!((b.right - b.left) / 4 * ((b.bottom - b.top) / 4) * 16, 65536);

    let mut touched = 0;
    for slice in 0..layout.slices {
        for mip in 0..desc.mips {
            let is_target = (mip, slice) == (changed_mip, changed_slice);
            if !is_target {
                assert_eq!(plan_for(mip, slice), Plan::Unchanged, "mip={mip}, slice={slice}");
            }
            let extent = &layout.mips[mip as usize];
            for y in 0..extent.height {
                for x in 0..extent.width {
                    let address = layout.offset(mip, x, y, slice).unwrap();
                    let changed = dirty.contains(&address);
                    let in_box = is_target &&
                        (b.left..b.right).contains(&(x * 4)) && (b.top..b.bottom).contains(&(y * 4));
                    assert_eq!(changed, in_box, "mip={mip}, slice={slice}, block=({x},{y})");
                    touched += u32::from(changed);
                }
            }
        }
    }
    assert_eq!(touched, 4096);

    println!("// Fixed BC7 fixture; physical range [{:#x},{:#x}), {} changed elements.",
             dirty.start, dirty.end, touched);
    println!("constexpr unsigned width = {}, height = {};", desc.width, desc.height);
    println!("constexpr unsigned array_size = {}, mip_levels = {};", desc.depth, desc.mips);
    println!("constexpr unsigned target = {};", changed_mip + changed_slice * desc.mips);
    println!("constexpr D3D12_BOX dirty_region{{{}, {}, 0, {}, {}, 1}};",
             b.left, b.top, b.right, b.bottom);
}
