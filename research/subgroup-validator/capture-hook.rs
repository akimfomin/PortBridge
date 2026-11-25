// SPDX-License-Identifier: GPL-2.0-only
// Fixture hook for the pinned XCL test module.
#[test]
fn portbridge_capture_direct_bpermute_dxil() {
    use crate::gpu::dxil::{kernel, validate};
    let version = validate::validator_version().expect("DXIL validator version");
    assert!(validate::validator_supported(), "DXIL validator 1.8 or newer required");
    eprintln!("PortBridge fixture DXIL validator {}.{}", version.0, version.1);
    let code = prog(&[
        ("DS_BPERMUTE_B32", "ENC_DS", &[("VDST", 10), ("ADDR", 1), ("DATA0", 0)], None),
        ("DS_BPERMUTE_B32", "ENC_DS", &[("VDST", 11), ("ADDR", 2), ("DATA0", 0), ("OFFSET0", 4)], None),
        ("DS_BPERMUTE_B32", "ENC_DS", &[("VDST", 12), ("ADDR", 1), ("DATA0", 0), ("OFFSET0", 128)], None),
        ("S_MOV_B32", "ENC_SOP1", &[("SDST", 126), ("SSRC0", 255)], Some(0x5555_5555)),
        ("S_MOV_B32", "ENC_SOP1", &[("SDST", 127), ("SSRC0", 255)], Some(0xAAAA_AAAA)),
        ("DS_BPERMUTE_B32", "ENC_DS", &[("VDST", 16), ("ADDR", 4), ("DATA0", 0)], None),
    ]);
    let out = std::path::PathBuf::from(std::env::var_os("PORTBRIDGE_DXIL_CAPTURE").expect("capture directory"));
    std::fs::create_dir_all(&out).unwrap();
    for (name, split) in [("native64", false), ("split32", true)] {
        let options = kernel::KernelOptions { wave64: true, split, mem_windows: 1, sampler_base: 0 };
        let translated = kernel::translate_full_as(&code, options, false).unwrap();
        validate::validate(&translated.dxil).unwrap();
        let listing = validate::disassemble(&translated.dxil).unwrap();
        assert!(listing.contains("dx.op.waveReadLaneAt.i32"));
        std::fs::write(out.join(format!("{name}.dxil")), &translated.dxil).unwrap();
        std::fs::write(out.join(format!("{name}.ll")), listing).unwrap();
    }
}
