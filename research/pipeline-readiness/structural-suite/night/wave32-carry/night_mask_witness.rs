// SPDX-License-Identifier: GPL-2.0-only
// A legal wave32 register-alias witness. Each draw compares a measured scalar popcount
// to its own independent expected value, so hardware-dependent wave packing cancels.
use std::collections::BTreeMap;
use std::{env, fs, path::Path};
use windows::Win32::Graphics::Dxgi::Common::DXGI_FORMAT_R32G32_FLOAT;
use xcl::gpu::{dxbc::SigElement, recomp::{self, dxc, runner, Mode, Options, PsInterface}};

fn element(name: &str, system_value: u32) -> SigElement {
    SigElement { name: name.into(), index: 0, system_value, component_type: 3, register: 0,
                 mask: 15, rw_mask: 15, stream: 0 }
}

fn emit(root: &Path, name: &str) -> Result<(), Box<dyn std::error::Error>> {
    let code = fs::read(root.join(format!("{name}.rdna2")))?;
    let ps = PsInterface { inputs: vec![element("SV_Position", 1)], outputs: vec![element("SV_Target", 64)],
                           input_ena: 768, attrs: None };
    let t = recomp::translate(&code, &Options { wave64: false, mode: Mode::Pixel(ps), ..Default::default() })?;
    if !t.complete() { return Err(format!("unsupported: {:?}", t.unsupported).into()); }
    let uses = t.hlsl.matches(" = ballot_px_local(").count();
    let reference = t.hlsl.replace(" = ballot_px_local(", " = ballot_px(");
    for (suffix, hlsl) in [("hlsl-stock", t.hlsl), ("hlsl-whole", reference)] {
        let path = root.join(format!("{name}-{suffix}"));
        let dxil = dxc::compile(&hlsl, "main", "ps_6_6", &[])?;
        fs::write(path.with_extension("hlsl"), hlsl)?;
        fs::write(path.with_extension("dxil"), dxil)?;
    }
    println!("CPU {name} stock fast sites {uses}");
    Ok(())
}

fn draw(root: &Path, name: &str, shader: &str) -> Result<(), Box<dyn std::error::Error>> {
    let vs = dxc::compile("float4 main(float2 p:POSITION):SV_Position { return float4(p,0.5,1); }",
                          "main", "vs_6_6", &[])?;
    let layout = [runner::VertexElement { semantic: "POSITION", index: 0, format: DXGI_FORMAT_R32G32_FLOAT, offset: 0 }];
    let full = [-1.,-1.,3.,-1.,-1.,3.];
    let diagonal = [-1.,-1.,1.,-1.,-1.,1.,1.,-1.,1.,1.,-1.,1.];
    let single_edge = [-1.,-1.,1.,-1.,-1.,1.];
    let cropped = [-0.91,-0.87,0.93,-0.67,-0.65,0.89];
    let ps = fs::read(root.join(format!("{name}-{shader}.dxil")))?;
    println!("adapter {}", runner::adapter()?);
    for (geometry, vertices) in [("full", &full[..]), ("diagonal", &diagonal[..]), ("edge", &single_edge[..]), ("cropped", &cropped[..])] {
        let out = runner::draw(&vs, &ps, &layout, vertices, 8, &[], &[], 32, [-99.; 4])?;
        let mut pairs = BTreeMap::new();
        let mut mismatch = 0usize;
        let mut covered = 0usize;
        for pixel in &out {
            if *pixel == [-99.; 4] { continue; }
            if pixel[2] != 1. || pixel[3] != 1. { return Err(format!("unexpected output: {pixel:?}").into()); }
            covered += 1;
            mismatch += usize::from(pixel[0] != pixel[1]);
            *pairs.entry(format!("{:.0}/{:.0}",pixel[0],pixel[1])).or_insert(0usize) += 1;
        }
        if covered == 0 { return Err("empty coverage".into()); }
        let raw: Vec<u8> = out.iter().flat_map(|p| p.iter().flat_map(|v| v.to_le_bytes())).collect();
        fs::write(root.join(format!("{name}-{shader}-{geometry}.rgba32f")), raw)?;
        println!("{}", serde_json::json!({"shape":name,"shader":shader,"geometry":geometry,"covered_pixels":covered,"mismatches":mismatch,"actual_expected_histogram":pairs}));
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<_> = env::args().skip(1).collect();
    match a.as_slice() {
        [cmd, root, name] if cmd=="emit" => emit(Path::new(root), name),
        [cmd, root, name, shader] if cmd=="draw" => draw(Path::new(root), name, shader),
        _ => Err("usage: emit DIR SHAPE | draw DIR SHAPE SHADER".into()),
    }
}
