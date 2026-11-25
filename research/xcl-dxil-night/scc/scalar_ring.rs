// SPDX-License-Identifier: GPL-2.0-only
#![allow(dead_code)]

#[path = "../portbridge-night-xcl-phi-scc/crates/xcl/src/gpu/rdna2.rs"]
mod rdna2;
#[path = "../portbridge-night-xcl-phi-scc/crates/xcl/src/gpu/rdna2_spec.rs"]
mod rdna2_spec;
#[path = "../portbridge-night-xcl-phi-scc/crates/xcl/src/gpu/rdna2_xbox.rs"]
mod rdna2_xbox;

fn push(code: &mut Vec<u8>, opcode: &str, encoding: &str, fields: &[(&str, u64)]) {
    code.extend(rdna2::encode(opcode, encoding, fields, None).unwrap());
}

fn mov(code: &mut Vec<u8>, dest: u64, src: u64) {
    push(code, "S_MOV_B32", "ENC_SOP1", &[("SDST", dest), ("SSRC0", src)]);
}

fn ring(width: u64, two_seeds: bool) -> Vec<u8> {
    let mut code = Vec::new();
    for i in 0..width {
        mov(&mut code, 4 + i, u64::from(two_seeds && i % 2 != 0));
    }
    mov(&mut code, 71, 132); // Loop count 4.
    let head = code.len() / 4;
    mov(&mut code, 70, 4);
    for i in 0..width - 1 {
        mov(&mut code, 4 + i, 5 + i);
    }
    mov(&mut code, 4 + width - 1, 70);
    push(&mut code, "S_SUB_U32", "ENC_SOP2", &[("SDST", 71), ("SSRC0", 71), ("SSRC1", 129)]);
    push(&mut code, "S_CMP_LG_U32", "ENC_SOPC", &[("SSRC0", 71), ("SSRC1", 128)]);
    let back = i16::try_from(head as isize - code.len() as isize / 4 - 1).unwrap() as u16;
    push(&mut code, "S_CBRANCH_SCC1", "ENC_SOPP", &[("SIMM16", back.into())]);
    for i in 0..width {
        push(&mut code, "V_MOV_B32", "ENC_VOP1", &[("VDST", 8), ("SRC0", 4 + i)]);
        push(&mut code, "BUFFER_STORE_DWORD", "ENC_MUBUF", &[
            ("VDATA", 8), ("SRSRC", 20), ("SOFFSET", 128), ("OFFSET", 4 * i),
        ]);
    }
    push(&mut code, "S_ENDPGM", "ENC_SOPP", &[]);
    code
}

fn main() {
    let path = std::path::PathBuf::from(std::env::args_os().nth(1).expect("output directory"));
    for (name, width, controls) in [("one-seed2", 2, false), ("one-seed16", 16, false),
                                    ("one-seed64", 64, false), ("two-seeds2", 2, true),
                                    ("two-seeds16", 16, true), ("two-seeds64", 64, true)] {
        let code = ring(width, controls);
        println!("{name} {} bytes of generated RDNA2", code.len());
        std::fs::write(path.join(format!("{name}.rdna2")), code).unwrap();
    }
}
