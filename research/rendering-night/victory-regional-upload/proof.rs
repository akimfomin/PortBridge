// SPDX-License-Identifier: GPL-3.0-or-later
#![allow(dead_code)]

mod copy_plan;
mod texture;

use copy_plan::{Plan, Rect, plan};
use texture::{Desc, Dimension, Error, Layout, Swizzle};

fn surface(width: u32, height: u32, block: u32, bpe: u32, swizzle: Swizzle) -> Desc {
    Desc {
        dimension: Dimension::Tex2d,
        width,
        height,
        depth: 2,
        mips: 5,
        element_bytes: bpe,
        block,
        samples: 1,
        swizzle,
    }
}

fn copy_to_destination(
    plan: &Plan, old: &mut [u8], staging: &[u8], pitch: usize, side: usize, bpe: usize,
) {
    match plan {
        Plan::Unchanged => {}
        Plan::Full => old.copy_from_slice(staging),
        Plan::Regions(rects) => {
            for r in rects {
                let row_start = r.left as usize / side * bpe;
                let row_end = r.right as usize / side * bpe;
                for y in r.top as usize / side..r.bottom as usize / side {
                    let row = y * pitch + row_start..y * pitch + row_end;
                    old[row.clone()].copy_from_slice(&staging[row]);
                }
            }
        }
    }
}

fn next(seed: &mut u64) -> u64 {
    *seed = seed.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1);
    *seed >> 33
}

fn verify_texture(desc: Desc, seed: &mut u64) -> (usize, usize, usize) {
    let layout = Layout::new(&desc).expect("source-generated valid layout");
    let original: Vec<_> = (0..layout.size).map(|i| (i ^ (i >> 6) ^ (i >> 15)) as u8).collect();
    let mut change = original.clone();
    let bpe = desc.element_bytes as usize;
    let mut outcomes = (0, 0, 0);
    for (mip, m) in layout.mips.iter().enumerate() {
        for slice in 0..layout.slices {
            let pitch = (m.width as usize * bpe).next_multiple_of(256);
            let bytes = pitch * m.height as usize;
            let base = slice as u64 * layout.slice_size + m.offset;
            let area = u64::from(m.rows) * u64::from(m.pitch) * bpe as u64;
            let range_end = (base + area).min(layout.size);
            let slot = layout.offset(mip as u32, m.width / 2, m.height / 2, slice).unwrap();
            let blocks = base..range_end;
            let target = slot..(slot + bpe as u64).min(layout.size);
            let mut spans = vec![
                Vec::new(), vec![target.clone()], vec![blocks.clone()],
                vec![0..layout.size],
            ];
            let relative = next(seed) % (slot - base + 1);
            let end = (base + relative + 257).min(layout.size);
            if base + relative < end {
                spans.push(vec![base + relative..end]);
            }
            let unrelated = if slice == 0 { layout.slice_size } else { 0 };
            spans.push(vec![unrelated..unrelated + bpe as u64]);
            if slot > base && target.end < range_end {
                spans.push(vec![base..base + 1, target, range_end - 1..range_end]);
            }
            let mut before = vec![0xAB; bytes];
            layout.detile(&original, mip as u32, slice, &mut before, pitch, bytes).unwrap();
            let mut exact = before.clone();
            let mut actual = before.clone();
            for ranges in spans {
                change.copy_from_slice(&original);
                for range in &ranges {
                    for v in &mut change[range.start as usize..range.end as usize] {
                        *v = !*v;
                    }
                }
                exact.copy_from_slice(&before);
                actual.copy_from_slice(&before);
                layout.detile(&change, mip as u32, slice, &mut exact, pitch, bytes).unwrap();
                let selection = plan(&layout, mip as u32, slice, true, &ranges).unwrap();
                if let Plan::Regions(rects) = &selection {
                    assert!(rects.len() <= 8);
                    for rect in rects {
                        let side = desc.block;
                        assert!(rect.left < rect.right && rect.top < rect.bottom);
                        assert!(rect.right <= (desc.width >> mip).max(1));
                        assert!(rect.bottom <= (desc.height >> mip).max(1));
                        assert!([rect.left, rect.top, rect.right, rect.bottom].iter().all(|c| c % side == 0));
                    }
                    for (i, a) in rects.iter().enumerate() {
                        for b in &rects[i + 1..] {
                            assert!(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top);
                        }
                    }
                }
                copy_to_destination(&selection, &mut actual, &exact, pitch, desc.block as usize, bpe);
                assert_eq!(exact, actual, "{desc:?}, mip={mip}, slice={slice}, ranges={ranges:?}, {selection:?}");
                match selection {
                    Plan::Unchanged => outcomes.0 += 1,
                    Plan::Full => outcomes.1 += 1,
                    Plan::Regions(_) => outcomes.2 += 1,
                }
            }
        }
    }
    outcomes
}

#[test]
fn plan_matches_full_after_deterministic_dirty_updates() {
    let mut cases = (0, 0, 0);
    let mut seed = 27_228;
    for swizzle in [
        Swizzle::SW_256B_D, Swizzle::SW_4KB_S, Swizzle::SW_4KB_D,
        Swizzle::SW_64KB_S, Swizzle::SW_64KB_D, Swizzle::LINEAR,
    ] {
        for desc in [
            surface(101, 75, 1, 1, swizzle),
            surface(145, 113, 1, 4, swizzle),
            surface(256, 196, 4, 16, swizzle),
            surface(259, 199, 4, 16, swizzle),
        ] {
            let counts = verify_texture(desc, &mut seed);
            cases.0 += counts.0;
            cases.1 += counts.1;
            cases.2 += counts.2;
        }
    }
    println!("plans tested: {} unchanged, {} full, {} regional", cases.0, cases.1, cases.2);
    assert!(cases.0 > 0 && cases.1 > 0 && cases.2 > 0);
}

#[test]
fn exact_tile_fallbacks_and_validated_area() {
    let mut desc = surface(512, 512, 1, 4, Swizzle::SW_64KB_D);
    desc.depth = 1;
    desc.mips = 1;
    let layout = Layout::new(&desc).unwrap();
    assert_eq!(layout.block, [128, 128, 1]);
    let base = layout.offset(0, 256, 128, 0).unwrap();
    let dirty_tile = base..base + 65_536;
    let tile = std::slice::from_ref(&dirty_tile);
    let regions = plan(&layout, 0, 0, true, tile).unwrap();
    assert_eq!(regions, Plan::Regions(vec![Rect { left: 256, top: 128, right: 384, bottom: 256 }]));
    assert_eq!(plan(&layout, 0, 0, false, tile), Ok(Plan::Full));
    assert_eq!(plan(&layout, 9, 0, true, tile), Err(Error::Invalid));
    assert_eq!(plan(&layout, 0, 1, true, tile), Err(Error::Invalid));
    assert_eq!(plan(&layout, 0, 0, true, &[16..32, 8..17]), Err(Error::Invalid));
    assert_eq!(plan(&layout, 0, 0, true, std::slice::from_ref(&(layout.size..layout.size + 1))), Err(Error::Invalid));
    let whole = 0..layout.size;
    assert_eq!(plan(&layout, 0, 0, true, std::slice::from_ref(&whole)), Ok(Plan::Full));
    println!("512x512 generated RGBA8: 1048576 full / 65536 regional bytes");
    let big = Layout::new(&Desc { width: 4096, height: 4096, ..desc }).unwrap();
    let block = big.offset(0, 1024, 2048, 0).unwrap();
    let tile = block..block + 65_536;
    let Plan::Regions(rects) = plan(&big, 0, 0, true, std::slice::from_ref(&tile)).unwrap() else {
        panic!("expected an efficient regional plan");
    };
    assert_eq!(rects.len(),1);
    assert_eq!((rects[0].right - rects[0].left) * (rects[0].bottom - rects[0].top) * 4, 65_536);
    println!("4096x4096 generated RGBA8: 67108864 full / 65536 regional bytes");
}
