use std::hint::black_box;
use std::time::Instant;

use anyxboxx_texture::gfx10::{PipeConfig, SurfaceDesc, SurfaceLayout, SwizzleMode};

fn case(name: &str) -> (SurfaceDesc, u32, u32, usize) {
    use SwizzleMode::*;
    let (width, height, bpe, block_side, mode, pipes, mips, mip, slice, repeats) = match name {
        "rgba1080_xor" => (1920, 1080, 4, 1, Sw64KSX, PipeConfig::SCARLETT, 1, 0, 1, 2),
        "bc7_4k" => (3840, 2160, 16, 4, Sw64KS, PipeConfig::SCARLETT, 1, 0, 0, 3),
        "bc7_4k_xor64" => (4096, 4096, 16, 4, Sw64KDX, PipeConfig::new(64, 32).unwrap(), 1, 0, 0, 2),
        "rgba_linear" => (1919, 1079, 4, 1, Linear, PipeConfig::SCARLETT, 1, 0, 1, 3),
        "bc7_tail" => (1024, 512, 16, 4, Sw64KSX, PipeConfig::SCARLETT, 11, 3, 1, 300),
        "rgba_wide" => (8192, 1, 4, 1, Sw4KSX, PipeConfig::SCARLETT, 1, 0, 0, 100),
        "rgba_tall" => (1, 8192, 4, 1, Sw4KSX, PipeConfig::SCARLETT, 1, 0, 1, 100),
        "bc7_one" => (4, 4, 16, 4, Sw64KSX, PipeConfig::SCARLETT, 1, 0, 1, 80_000),
        "bc7_2x1" => (8, 4, 16, 4, Sw64KSX, PipeConfig::SCARLETT, 1, 0, 1, 80_000),
        "bc7_1x2" => (4, 8, 16, 4, Sw64KSX, PipeConfig::SCARLETT, 1, 0, 1, 80_000),
        "bc7_2x2" => (8, 8, 16, 4, Sw64KSX, PipeConfig::SCARLETT, 1, 0, 1, 80_000),
        _ => panic!("unknown case {name}"),
    };
    (SurfaceDesc { width, height, mip_levels: mips, array_size: slice + 1, element_bytes: bpe,
        block_side, swizzle: mode, pipes, pipe_bank_xor: 0xad }, mip, slice, repeats)
}

fn fingerprint(data: &[u8]) -> u64 {
    data.iter().fold(0xcbf2_9ce4_8422_2325, |acc, &b| (acc ^ u64::from(b)).wrapping_mul(0x100_0000_01b3))
}

fn main() {
    let name = std::env::args().nth(1).unwrap();
    let (desc, mip, slice, repeats) = case(&name);
    let layout = SurfaceLayout::compute(desc).unwrap();
    if name == "bc7_tail" { assert!(layout.mips[mip as usize].tail.is_some()); }
    let layout_mip = &layout.mips[mip as usize];
    let elements = layout_mip.width_elements as usize * layout_mip.height_elements as usize;
    let mut state = 0xb902_d4e1u32;
    let linear: Vec<_> = (0..elements * desc.element_bytes as usize).map(|_| {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        state as u8
    }).collect();
    let mut tiled = vec![0x33; layout.total_size as usize];
    layout.tile_subresource(&linear, &mut tiled, mip, slice).unwrap();
    assert_eq!(layout.detile_subresource(&tiled, mip, slice).unwrap(), linear);

    let start = Instant::now();
    for _ in 0..repeats {
        layout.tile_subresource(black_box(&linear), black_box(&mut tiled), mip, slice).unwrap();
    }
    let tile_ns = start.elapsed().as_nanos() / repeats as u128;

    let start = Instant::now();
    for _ in 0..repeats {
        black_box(layout.detile_subresource(black_box(&tiled), mip, slice).unwrap());
    }
    let detile_ns = start.elapsed().as_nanos() / repeats as u128;

    println!("{name},{tile_ns},{detile_ns},{:016x},{:016x},{}", fingerprint(&tiled), fingerprint(&linear), linear.len());
}
