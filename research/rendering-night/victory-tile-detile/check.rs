// SPDX-License-Identifier: GPL-3.0-or-later
#[path = "prepared/candidate.rs"]
mod texture;
#[cfg(use_2026)]
#[path = "prepared/full_2026.rs"]
mod current_full;

use std::hint::black_box;
use std::ops::Range;
use std::time::Instant;
use texture::{Desc, Dimension, Layout, Swizzle};

const TILE: usize = 64 * 1024;

#[derive(Clone, Copy)]
struct Shape {
    name: &'static str,
    side: u32,
    block: u32,
    element_bytes: u32,
    swizzle: Swizzle,
}

const SHAPES: [Shape; 4] = [
    Shape { name: "rgba8-512-S", side: 512, block: 1, element_bytes: 4, swizzle: Swizzle::SW_64KB_S },
    Shape { name: "rgba8-1024-D", side: 1024, block: 1, element_bytes: 4, swizzle: Swizzle::SW_64KB_D },
    Shape { name: "bc7-1024-D", side: 1024, block: 4, element_bytes: 16, swizzle: Swizzle::SW_64KB_D },
    Shape { name: "bc7-2048-S", side: 2048, block: 4, element_bytes: 16, swizzle: Swizzle::SW_64KB_S },
];

struct Image {
    layout: Layout,
    #[cfg(use_2026)]
    alternate: current_full::Layout,
    tiled: Vec<u8>,
    linear: Vec<u8>,
    pitch: usize,
}

impl Image {
    fn new(s: Shape) -> Self {
        let layout = Layout::new(&Desc {
            dimension: Dimension::Tex2d, width: s.side, height: s.side, depth: 1, mips: 1,
            element_bytes: s.element_bytes, block: s.block, samples: 1, swizzle: s.swizzle,
        }).unwrap();
        let mip = layout.mips[0];
        let pitch = (mip.width * s.element_bytes) as usize + 256;
        let tiled = (0..layout.size as usize).map(|i| {
            (i.wrapping_mul(0x1c69b3) ^ (i >> 7) ^ (i >> 13)) as u8
        }).collect::<Vec<_>>();
        let mut linear = vec![0xb8; pitch * mip.height as usize];
        layout.detile(&tiled, 0, 0, &mut linear, pitch, 0).unwrap();
        #[cfg(use_2026)]
        let alternate = current_full::Layout::new(&current_full::Desc {
            dimension: current_full::Dimension::Tex2d, width: s.side, height: s.side, depth: 1, mips: 1,
            element_bytes: s.element_bytes, block: s.block, samples: 1,
            swizzle: if s.swizzle == Swizzle::SW_64KB_S {
                current_full::Swizzle::SW_64KB_S
            } else {
                current_full::Swizzle::SW_64KB_D
            },
        }).unwrap();
        Self {
            layout,
            #[cfg(use_2026)]
            alternate,
            tiled, linear, pitch,
        }
    }

    fn whole(&self, tiled: &[u8], linear: &mut [u8]) {
        #[cfg(use_2026)]
        self.alternate.detile(tiled, 0, 0, linear, self.pitch, 0).unwrap();
        #[cfg(not(use_2026))]
        self.layout.detile(tiled, 0, 0, linear, self.pitch, 0).unwrap();
    }

    fn extents(&self) -> (u32, u32) {
        (self.layout.mips[0].width / self.layout.block[0],
         self.layout.mips[0].height / self.layout.block[1])
    }

    fn next(&self, tile: (u32, u32)) -> (Vec<u8>, Range<usize>) {
        let [tw, th, _] = self.layout.block;
        let base = self.layout.offset(0, tile.0 * tw, tile.1 * th, 0).unwrap() as usize & !(TILE - 1);
        let covered = base..base + TILE;
        let mut next = self.tiled.clone();
        for b in &mut next[covered.clone()] { *b ^= 0x57; }
        (next, covered)
    }
}

fn outside_unchanged(old: &[u8], new: &[u8], tile: &Range<usize>) -> bool {
    old[..tile.start] == new[..tile.start] && old[tile.end..] == new[tile.end..]
}

fn correctness() {
    let mut cases = 0;
    for s in SHAPES {
        let img = Image::new(s);
        let (cols, rows) = img.extents();
        let layout = &img.layout;
        for y in 0..rows {
            for x in 0..cols {
                let (next, span) = img.next((x, y));
                assert!(outside_unchanged(&img.tiled, &next, &span));
                let mut full = img.linear.clone();
                let mut region = img.linear.clone();
                img.whole(&next, &mut full);
                layout.detile_color_tile(&next, &mut region, img.pitch, x, y).unwrap();
                assert_eq!(full, region, "{} ({x},{y})", s.name);
                let changed = region.iter().zip(&img.linear).filter(|(a, b)| a != b).count();
                assert_eq!(changed, TILE, "changed element count");
                cases += 1;
            }
        }
        let mut contents = img.linear.clone();
        assert!(layout.detile_color_tile(&img.tiled, &mut contents, img.pitch, cols, 0).is_err());
        assert!(layout.detile_color_tile(&img.tiled[..img.tiled.len()-1], &mut contents, img.pitch, 0, 0).is_err());
        assert!(layout.detile_color_tile(&img.tiled, &mut contents, usize::MAX, 0, 0).is_err());
        assert!(layout.detile_color_tile(&img.tiled, &mut contents, img.pitch, u32::MAX, 0).is_err());
        assert_eq!(img.linear, contents);
    }
    println!("full_byte_equality_cases={cases}; all padded rows preserved; 16 invalid input controls");
}

fn benchmark() {
    println!("case,pair,order,texture_bytes,full_ns,tile_ns,checked_tile_ns");
    for (index, s) in SHAPES.into_iter().enumerate() {
        let img = Image::new(s);
        let (cols, rows) = img.extents();
        let tile = (cols / 2, rows / 2);
        let (next, span) = img.next(tile);
        let mut out = [img.linear.clone(), img.linear.clone(), img.linear.clone()];
        for pair in 0..=12 {
            let shift = (pair + index) % out.len();
            let order = if pair % 2 == 0 { [shift, (shift + 1) % 3, (shift + 2) % 3] }
                        else { [shift, (shift + 2) % 3, (shift + 1) % 3] };
            let mut intervals = [0; 3];
            for arm in order {
                out[arm].copy_from_slice(&img.linear);
                let begin = Instant::now();
                if arm == 0 {
                    img.whole(black_box(&next), black_box(&mut out[arm]));
                } else {
                    if arm == 2 { assert!(outside_unchanged(black_box(&img.tiled), black_box(&next), &span)); }
                    img.layout.detile_color_tile(black_box(&next), black_box(&mut out[arm]),
                                                 img.pitch, tile.0, tile.1).unwrap();
                }
                intervals[arm] = begin.elapsed().as_nanos();
            }
            assert!(out[0] == out[1] && out[0] == out[2]);
            let steps = order.map(|i| ["full", "tile", "checked"][i]).join("-");
            println!("{},{},{},{},{},{},{}", s.name, pair, steps, next.len(),
                     intervals[0], intervals[1], intervals[2]);
        }
    }
}

fn main() {
    match std::env::args().nth(1).as_deref() {
        Some("--check") => correctness(),
        Some("--time") => benchmark(),
        _ => panic!("use --check or --time"),
    }
}
