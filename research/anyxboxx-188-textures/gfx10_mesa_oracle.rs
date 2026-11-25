// SPDX-License-Identifier: MIT
use anyxboxx_texture::gfx10::{PipeConfig, SurfaceDesc, SurfaceLayout, SwizzleMode};
use std::{env, fs};

fn main() {
    let cases = fs::read_to_string(env::args_os().nth(1).expect("coordinate corpus")).unwrap();
    let mut measurements = 0;
    let mut mismatch = 0;
    for line in cases.lines() {
        let (name, numeric) = line.split_once(';').unwrap();
        let values: Vec<u32> = numeric.split(',').map(|value| value.parse().unwrap()).collect();
        let [width, height, mip_levels, layout_id, element_bytes, block_side, mip, x, y, expected] =
            <[u32; 10]>::try_from(values).unwrap();
        let swizzle = match layout_id {
            0x102 => SwizzleMode::Sw256BD,
            0x105 => SwizzleMode::Sw4KS,
            0x106 => SwizzleMode::Sw4KD,
            0x109 => SwizzleMode::Sw64KS,
            0x10A => SwizzleMode::Sw64KD,
            other => panic!("unsupported published layout {other:X}"),
        };
        let desc = SurfaceDesc {
            width, height, mip_levels, array_size: 1, element_bytes, block_side, swizzle,
            pipes: PipeConfig::SCARLETT, pipe_bank_xor: 0,
        };
        let layout = SurfaceLayout::compute(desc).unwrap();
        let expected = expected as usize;
        let byte_count = element_bytes as usize;
        let offset = layout.element_offset(mip, 0, x, y).unwrap();
        let width_elements = layout.mips[mip as usize].width_elements as usize;
        let at = (y as usize * width_elements + x as usize) * byte_count;
        let source: Vec<_> = (0..layout.total_size as usize)
            .map(|i| (i ^ (i >> 5) ^ (i >> 11)) as u8)
            .collect();
        let linear = layout.detile_subresource(&source, mip, 0).unwrap();
        let mut back = vec![0x7B; layout.total_size as usize];
        layout.tile_subresource(&linear, &mut back, mip, 0).unwrap();
        measurements += 1;
        if offset != expected
            || linear[at..at + byte_count] != source[expected..expected + byte_count]
            || back[expected..expected + byte_count] != source[expected..expected + byte_count]
        {
            println!("{name}: mip {mip} ({x},{y}) expected {expected:X}, actual {offset:X}");
            mismatch += 1;
        }
    }
    println!("{measurements} Mesa coordinates; {mismatch} mismatches");
    assert_eq!(mismatch, 0);
}
