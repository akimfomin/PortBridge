// SPDX-License-Identifier: GPL-2.0-only
// Optional integration test for XCL 20cf130; intentionally lives outside Cargo discovery.
#![cfg(windows)]

use xcl::gpu::dxil::kernel::{KernelOptions, translate};
use xcl::gpu::rdna2::encode;
use xcl::gpu::recomp::runner::{self, KernelState};

const FIRST_RING_SGPR: u64 = 4;
const FIRST_RESULT_VGPR: u64 = 8;
const ROTATIONS: usize = 3;
const SEEDS: [u32; 2] = [0x1357_9bdf, 0x2468_ace0];

fn push(code: &mut Vec<u8>, op: &str, encoding: &str, fields: &[(&str, u64)]) {
    code.extend(encode(op, encoding, fields, None).unwrap());
}

fn mov(code: &mut Vec<u8>, dest: u64, src: u64) {
    push(code, "S_MOV_B32", "ENC_SOP1", &[("SDST", dest), ("SSRC0", src)]);
}

fn kernel(width: u64, seeds: usize) -> Vec<u8> {
    let mut code = Vec::new();
    let end = FIRST_RING_SGPR + width;
    for i in 0..width {
        mov(&mut code, FIRST_RING_SGPR + i, i % seeds as u64);
    }
    mov(&mut code, 71, 128 + ROTATIONS as u64);
    let head = code.len() / 4;
    mov(&mut code, 70, FIRST_RING_SGPR);
    for dest in FIRST_RING_SGPR..end - 1 {
        mov(&mut code, dest, dest + 1);
    }
    mov(&mut code, end - 1, 70);
    push(&mut code, "S_SUB_U32", "ENC_SOP2", &[("SDST", 71), ("SSRC0", 71), ("SSRC1", 129)]);
    push(&mut code, "S_CMP_LG_U32", "ENC_SOPC", &[("SSRC0", 71), ("SSRC1", 128)]);
    let offset = i16::try_from(head as isize - code.len() as isize / 4 - 1).unwrap();
    push(&mut code, "S_CBRANCH_SCC1", "ENC_SOPP", &[("SIMM16", u64::from(offset as u16))]);
    // Only registers leave the guest program. XCL's existing runner owns all memory bindings.
    for i in 0..width {
        push(&mut code, "V_ADD_NC_U32", "ENC_VOP2",
            &[("VDST", FIRST_RESULT_VGPR + i), ("SRC0", FIRST_RING_SGPR + i), ("VSRC1", 0)]);
    }
    push(&mut code, "S_ENDPGM", "ENC_SOPP", &[]);
    code
}

fn check(wave64: bool, split: bool) {
    let lanes = if wave64 { 64 } else { 32 };
    let hardware_width = if wave64 && !split { 64 } else { 32 };
    let supported = if hardware_width == 64 { runner::wave64_supported() } else { runner::wave32_supported() };
    let adapter = runner::adapter().expect("physical D3D12 adapter");
    assert!(supported.expect("wave capability"), "{adapter} lacks wave{hardware_width}");
    let mut state = KernelState::default();
    state.sgpr[..SEEDS.len()].copy_from_slice(&SEEDS);
    for lane in 0..lanes {
        state.vgpr[lane][0] = lane as u32;
    }
    let options = KernelOptions { wave64, split, mem_windows: 1, sampler_base: 0 };
    let memory = [0x5a5a_a5a5; 64];
    for (width, seed_count) in [(64, 1), (16, 2)] {
        let dxil = translate(&kernel(width as u64, seed_count), options).expect("translate synthetic register ring");
        let result = runner::run(&dxil, &state, &memory).expect("run synthetic register ring");
        for i in 0..width {
            let seed = SEEDS[((i + ROTATIONS) % width) % seed_count];
            let vgpr = FIRST_RESULT_VGPR as usize + i;
            assert_eq!(result.sgpr[FIRST_RING_SGPR as usize + i], seed, "SGPR {i}");
            for lane in 0..lanes {
                assert_eq!(result.vgpr[lane][vgpr], seed.wrapping_add(lane as u32), "v{vgpr}, lane {lane}");
            }
        }
        assert_eq!(result.mem.as_slice(), &memory, "guest memory changed");
        println!("{adapter}: wave{lanes} split={split}, {width} SGPRs, {seed_count} seed(s), {} DXIL bytes", dxil.len());
    }
}

#[test]
#[ignore = "runs two synthetic kernels on a physical D3D12 wave32 GPU"]
fn phi_ring_native_wave32() {
    check(false, false);
}

#[test]
#[ignore = "runs two synthetic kernels on a physical D3D12 wave64 GPU"]
fn phi_ring_native_wave64() {
    check(true, false);
}

#[test]
#[ignore = "runs two synthetic kernels on a physical D3D12 wave32 GPU"]
fn phi_ring_split_wave64() {
    check(true, true);
}
