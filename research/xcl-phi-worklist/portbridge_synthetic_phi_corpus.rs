// SPDX-License-Identifier: GPL-2.0-only
use std::time::Instant;

use xcl::gpu::dxil::kernel::{translate, KernelOptions};
use xcl::gpu::rdna2::encode;
use xcl::gpu::recomp::HEAP_WINDOWS;

fn append(code: &mut Vec<u8>, name: &str, enc: &str, fields: &[(&str, u64)]) {
    code.extend(encode(name, enc, fields, None).unwrap());
}

fn formatted_loads(count: u64) -> Vec<u8> {
    let mut code = Vec::new();
    for i in 0..count {
        append(&mut code, "BUFFER_LOAD_FORMAT_X", "ENC_MUBUF", &[
            ("VDATA", 16 + i % 192), ("VADDR", 0), ("SRSRC", 3 + i % 4),
            ("SOFFSET", 128), ("IDXEN", 1), ("OFFSET", 16 * (i % 192)),
        ]);
    }
    append(&mut code, "S_ENDPGM", "ENC_SOPP", &[]);
    code
}

fn scalar_loops(count: u64) -> Vec<u8> {
    let mut code = Vec::new();
    for i in 0..count {
        append(&mut code, "S_MOV_B32", "ENC_SOP1", &[("SDST", 16), ("SSRC0", 130)]);
        append(&mut code, "V_ADD_NC_U32", "ENC_VOP2", &[("VDST", 8), ("SRC0", 256 + i % 4), ("VSRC1", 8)]);
        append(&mut code, "S_SUB_U32", "ENC_SOP2", &[("SDST", 16), ("SSRC0", 16), ("SSRC1", 129)]);
        append(&mut code, "S_CMP_LG_U32", "ENC_SOPC", &[("SSRC0", 16), ("SSRC1", 128)]);
        append(&mut code, "S_CBRANCH_SCC1", "ENC_SOPP", &[("SIMM16", 0xfffc)]);
    }
    append(&mut code, "S_ENDPGM", "ENC_SOPP", &[]);
    code
}

fn loop_carries(count: u64) -> Vec<u8> {
    let mut code = Vec::new();
    append(&mut code, "S_MOV_B32", "ENC_SOP1", &[("SDST", 16), ("SSRC0", 130)]);
    for i in 0..count {
        append(&mut code, "V_ADD_NC_U32", "ENC_VOP2", &[
            ("VDST", 4 + i % 96), ("SRC0", 258 + i % 96), ("VSRC1", 4 + i % 96),
        ]);
    }
    append(&mut code, "S_SUB_U32", "ENC_SOP2", &[("SDST", 16), ("SSRC0", 16), ("SSRC1", 129)]);
    append(&mut code, "S_CMP_LG_U32", "ENC_SOPC", &[("SSRC0", 16), ("SSRC1", 128)]);
    append(&mut code, "S_CBRANCH_SCC1", "ENC_SOPP", &[("SIMM16", 0x10000 - (3 + count))]);
    append(&mut code, "S_ENDPGM", "ENC_SOPP", &[]);
    code
}

fn scalar_copy_loops(count: u64) -> Vec<u8> {
    let mut code = Vec::new();
    let registers = 96;
    for i in 0..registers {
        append(&mut code, "S_MOV_B32", "ENC_SOP1", &[("SDST", i), ("SSRC0", 151)]);
    }
    for _ in 0..count {
        append(&mut code, "S_MOV_B32", "ENC_SOP1", &[("SDST", 100), ("SSRC0", 130)]);
        for i in 0..registers - 1 {
            append(&mut code, "S_MOV_B32", "ENC_SOP1", &[("SDST", i), ("SSRC0", i + 1)]);
        }
        append(&mut code, "S_MOV_B32", "ENC_SOP1", &[("SDST", registers - 1), ("SSRC0", 151)]);
        append(&mut code, "S_SUB_U32", "ENC_SOP2", &[("SDST", 100), ("SSRC0", 100), ("SSRC1", 129)]);
        append(&mut code, "S_CMP_LG_U32", "ENC_SOPC", &[("SSRC0", 100), ("SSRC1", 128)]);
        append(&mut code, "S_CBRANCH_SCC1", "ENC_SOPP", &[("SIMM16", 0x10000 - (registers + 3))]);
    }
    append(&mut code, "S_ENDPGM", "ENC_SOPP", &[]);
    code
}

#[test]
fn synthetic_shader_corpus() {
    let mut output = Vec::new();
    for (family, builder) in [
        ("formatted", formatted_loads as fn(u64) -> Vec<u8>),
        ("scalar_loops", scalar_loops),
        ("loop_carries", loop_carries),
        ("scalar_copies", scalar_copy_loops),
    ] {
        for count in [8, 32, 128] {
            let code = builder(count);
            for (flavor, wave64, split, mem_windows) in [
                ("switch", false, false, 4),
                ("heap_split", true, true, 4 | HEAP_WINDOWS),
            ] {
                let opts = KernelOptions { wave64, split, mem_windows, sampler_base: 0 };
                let first = translate(&code, opts).unwrap_or_else(|e| panic!("{family} {count}: {e}"));
                let mut times = [0.0; 5];
                for sample in &mut times {
                    let start = Instant::now();
                    let dxil = translate(&code, opts).unwrap();
                    *sample = start.elapsed().as_secs_f64() * 1e3;
                    assert_eq!(dxil, first);
                }
                times.sort_by(f64::total_cmp);
                let bytes = first.len() as u32;
                output.extend(bytes.to_le_bytes());
                output.extend(first);
                println!("{family} n={count} mode={flavor} dxil_bytes={bytes} translation_ms={:.4}", times[2]);
            }
        }
    }
    let path = std::env::var_os("PORTBRIDGE_RND_CORPUS_OUTPUT").expect("output path");
    std::fs::write(path, output).unwrap();
}
