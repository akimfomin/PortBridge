// SPDX-License-Identifier: GPL-2.0-only
//! Compile-only DXIL shape observation for public AMD PAL pixel instruction streams.
//! The synthetic XCL interface deliberately does not emulate Vulkan resource bindings.
use std::path::Path;
use xcl::gpu::dxbc::SigElement;
use xcl::gpu::dxil::{kernel::{
    translate_pixel, translate_pixel_for_lane_local_masks, translate_pixel_for_uma_aperture, KernelOptions,
}, validate};
use xcl::gpu::recomp::{PsInterface, HEAP_WINDOWS};

fn sig(name: &str, index: u32, system_value: u32, component_type: u32, register: u32, mask: u8) -> SigElement {
    SigElement { name: name.into(), index, system_value, component_type, register, mask, rw_mask: mask, stream: 0 }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let [code, out, wave, ena, interps, targets, depth, windows, proof_base, mode] = args.as_slice() else {
        return Err("expected RDNA DXIL wave spi_ps_input_ena input_locations color_mask depth_mode windows-layout generic-or-proved-base-hi whole-or-local".into());
    };
    let mut inputs = vec![sig("SV_Position", 0, 1, 3, 0, 15)];
    let interps = interps.parse::<u32>()?;
    for index in 0..interps {
        inputs.push(sig("TEXCOORD", index, 0, 3, 1 + index, 15));
    }
    let input_ena = ena.parse::<u32>()?;
    if input_ena & (1 << 12) != 0 {
        inputs.push(sig("SV_IsFrontFace", 0, 9, 1, 1 + interps, 1));
    }
    let targets = targets.parse::<u32>()?;
    let mut outputs: Vec<_> = (0..8).filter(|i| targets & (1 << i) != 0)
        .map(|i| sig("SV_Target", i, 64, 3, i, 15)).collect();
    match depth.as_str() {
        "0" => outputs.push(sig("SV_Depth", 0, 65, 3, u32::MAX, 1)),
        "1" => outputs.push(sig("SV_DepthLessEqual", 0, 68, 3, u32::MAX, 1)),
        "2" => outputs.push(sig("SV_DepthGreaterEqual", 0, 67, 3, u32::MAX, 1)),
        "-1" => {}
        _ => return Err("invalid conservative depth export type".into()),
    }
    let abi = PsInterface { inputs, outputs, input_ena, attrs: None };
    let (layout, count) = windows.split_once('-').ok_or("windows-layout must be heap-N or root-N")?;
    let flags = match layout {
        "heap" => HEAP_WINDOWS,
        "root" => 0,
        _ => return Err("unknown memory-window layout".into()),
    };
    let mem_windows = count.parse::<u32>()? | flags;
    let options = KernelOptions { wave64: wave == "64", split: false, mem_windows, sampler_base: 0 };
    let code = std::fs::read(code)?;
    let base = if proof_base == "generic" { None } else { Some(proof_base.parse::<u32>()?) };
    let shader = match (mode.as_str(), base) {
        ("whole", None) => translate_pixel(&code, options, &abi)?,
        ("whole", Some(base)) => translate_pixel_for_uma_aperture(&code, options, &abi, base)?,
        ("local", _) => translate_pixel_for_lane_local_masks(&code, options, &abi, base)?,
        _ => return Err("mode must be whole or local".into()),
    };
    validate::validate(&shader.dxil)?;
    std::fs::write(out, &shader.dxil)?;
    std::fs::write(Path::new(out).with_extension("ll"), validate::disassemble(&shader.dxil)?)?;
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
