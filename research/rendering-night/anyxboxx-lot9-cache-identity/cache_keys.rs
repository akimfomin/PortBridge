// SPDX-License-Identifier: GPL-3.0-or-later
include!("source_keys.rs");

fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    assert_eq!(args.len(), 2);
    let build = *blake3::hash(args[0].as_bytes()).as_bytes();
    let update = *blake3::hash(args[1].as_bytes()).as_bytes();
    let mut source = [0u8; 48];
    source[..4].copy_from_slice(b"DXBC");
    source[24..28].copy_from_slice(&32u32.to_le_bytes());
    source[32..].fill(7);
    let input = canonical_container(&source);

    let initial = shader_key(&build, [32, 1000], input);
    assert_eq!(initial, shader_key(&build, [32, 1000], &source[..32]));
    assert_ne!(initial, shader_key(&update, [32, 1000], input));
    assert_ne!(initial, shader_key(&build, [64, 1000], input));
    assert_ne!(initial, shader_key(&build, [32, 1001], input));
    println!("initial_shader_key={}", initial.to_hex());
    println!("updated_shader_key={}", shader_key(&update, [32, 1000], input).to_hex());

    let initial_pso = name("compute", b"synthetic root", &[b"synthetic old DXIL"], "");
    let updated_pso = name("compute", b"synthetic root", &[b"synthetic new DXIL"], "");
    assert_ne!(initial_pso, updated_pso);
    assert_eq!(initial_pso, name("compute", b"synthetic root", &[b"synthetic old DXIL"], ""));
    assert_ne!(initial_pso, name("compute", b"other root", &[b"synthetic old DXIL"], ""));
    assert_ne!(initial_pso, name("compute", b"synthetic root", &[b"synthetic old DXIL"], "other state"));
    println!("initial_pipeline_name={initial_pso}");
    println!("updated_pipeline_name={updated_pso}");
}
