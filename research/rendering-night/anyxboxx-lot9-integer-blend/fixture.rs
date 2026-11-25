// SPDX-License-Identifier: GPL-3.0-or-later
use windows::Win32::Graphics::Direct3D12::*;
use windows::Win32::Graphics::Dxgi::Common::*;

struct GraphicsState {
    blend: D3D12_BLEND_DESC,
    #[allow(dead_code)] // The lot-9 baseline forwards only the blend field.
    targets: D3D12_RT_FORMAT_ARRAY,
}

include!("host_blend.rs");

const PATHS: [(&str, fn(&GraphicsState) -> D3D12_BLEND_DESC); 4] = [
    ("graphics", graphics),
    ("graphics_depth_bounds", graphics_depth_bounds),
    ("mesh_legacy_depth", mesh_legacy_depth),
    ("mesh_depth_bounds", mesh_depth_bounds),
];

fn blend_state(independent: bool) -> D3D12_BLEND_DESC {
    let target = D3D12_RENDER_TARGET_BLEND_DESC {
        BlendEnable: true.into(),
        LogicOpEnable: false.into(),
        SrcBlend: D3D12_BLEND_SRC_ALPHA,
        DestBlend: D3D12_BLEND_INV_SRC_ALPHA,
        BlendOp: D3D12_BLEND_OP_ADD,
        SrcBlendAlpha: D3D12_BLEND_ONE,
        DestBlendAlpha: D3D12_BLEND_ZERO,
        BlendOpAlpha: D3D12_BLEND_OP_ADD,
        LogicOp: D3D12_LOGIC_OP_NOOP,
        RenderTargetWriteMask: 0b0011,
    };
    let mut blend = D3D12_BLEND_DESC {
        AlphaToCoverageEnable: false.into(),
        IndependentBlendEnable: independent.into(),
        RenderTarget: [target; 8],
    };
    // Different full slot states expose accidental slot-0 overwrite.
    blend.RenderTarget[1].SrcBlend = D3D12_BLEND_ONE;
    blend.RenderTarget[1].BlendOpAlpha = D3D12_BLEND_OP_MAX;
    blend.RenderTarget[1].RenderTargetWriteMask = 0b1001;
    blend.RenderTarget[2].DestBlend = D3D12_BLEND_ONE;
    blend.RenderTarget[2].RenderTargetWriteMask = 0b0001;
    blend.RenderTarget[7].BlendEnable = false.into();
    blend.RenderTarget[7].RenderTargetWriteMask = 0b1100;
    blend
}

fn targets(formats: &[DXGI_FORMAT]) -> D3D12_RT_FORMAT_ARRAY {
    let mut desc = D3D12_RT_FORMAT_ARRAY {
        NumRenderTargets: formats.len() as u32,
        RTFormats: [DXGI_FORMAT_UNKNOWN; 8],
    };
    desc.RTFormats[..formats.len()].copy_from_slice(formats);
    desc
}

fn effective(blend: &D3D12_BLEND_DESC, slot: usize) -> D3D12_RENDER_TARGET_BLEND_DESC {
    let shared = !blend.IndependentBlendEnable.as_bool();
    blend.RenderTarget[if shared { 0 } else { slot }]
}

fn check_case(label: &str, g: &GraphicsState, integer_slots: &[usize]) {
    let original = g.blend;
    let before = integer_slots.iter().filter(|&&slot| effective(&original, slot).BlendEnable.as_bool()).count();
    for (path, construct) in PATHS {
        let got = construct(g);
        let after = integer_slots.iter().filter(|&&slot| effective(&got, slot).BlendEnable.as_bool()).count();
        assert_eq!(after, if cfg!(pb_candidate) { 0 } else { before });
        if before == 0 || !cfg!(pb_candidate) {
            assert_eq!(got, original, "{label}/{path} changed uninterpreted descriptor");
        } else if !original.IndependentBlendEnable.as_bool() {
            assert!(got.IndependentBlendEnable.as_bool());
        }
        assert_eq!(got.AlphaToCoverageEnable, original.AlphaToCoverageEnable);
        for slot in 0..g.targets.NumRenderTargets as usize {
            let mut expected = effective(&original, slot);
            if cfg!(pb_candidate) && integer_slots.contains(&slot) {
                expected.BlendEnable = false.into();
            }
            assert_eq!(effective(&got, slot), expected, "{label}/{path} effective slot {slot}");
        }
        if original.IndependentBlendEnable.as_bool() {
            let end = g.targets.NumRenderTargets as usize;
            assert_eq!(got.RenderTarget[end..], original.RenderTarget[end..]);
        }
        println!("{label}/{path} enabled_integer_slots={after} float_and_other_fields=preserved");
    }
}

#[test]
fn shared_r8_uint_slot_zero_does_not_disable_float_mrt() {
    let g = GraphicsState {
        blend: blend_state(false),
        targets: targets(&[DXGI_FORMAT_R8_UINT, DXGI_FORMAT_R16G16B16A16_FLOAT, DXGI_FORMAT_R8_SINT]),
    };
    check_case("shared_uint_first", &g, &[0, 2]);
}

#[test]
fn shared_r8_uint_after_float_preserves_alpha_and_write_masks() {
    let mut blend = blend_state(false);
    blend.AlphaToCoverageEnable = true.into();
    let g = GraphicsState {
        blend,
        targets: targets(&[DXGI_FORMAT_R8G8B8A8_UNORM, DXGI_FORMAT_R16G16B16A16_FLOAT, DXGI_FORMAT_R8_UINT]),
    };
    check_case("shared_uint_last", &g, &[2]);
}

#[test]
fn separate_blend_slots_retain_all_non_blend_fields_and_inactive_entries() {
    let mut targets = targets(&[DXGI_FORMAT_R8_UINT, DXGI_FORMAT_R16G16B16A16_FLOAT, DXGI_FORMAT_R16_SINT]);
    targets.RTFormats[6] = DXGI_FORMAT_R8_UINT; // Inactive format is irrelevant.
    let g = GraphicsState { blend: blend_state(true), targets };
    check_case("independent_distinct_slots", &g, &[0, 2]);
}

#[test]
fn already_legal_states_pass_unchanged() {
    let mut blend = blend_state(true);
    blend.RenderTarget[1].BlendEnable = false.into();
    check_case("uint_already_off", &GraphicsState {
        blend,
        targets: targets(&[DXGI_FORMAT_R8G8B8A8_UNORM, DXGI_FORMAT_R8_UINT]),
    }, &[1]);

    let mut uniform_logic = blend_state(false);
    uniform_logic.RenderTarget[0].BlendEnable = false.into();
    uniform_logic.RenderTarget[0].LogicOpEnable = true.into();
    uniform_logic.RenderTarget[0].LogicOp = D3D12_LOGIC_OP_XOR;
    check_case("logic_without_blend", &GraphicsState {
        blend: uniform_logic,
        targets: targets(&[DXGI_FORMAT_R8_UINT]),
    }, &[0]);

    let g = GraphicsState {
        blend: blend_state(false),
        targets: targets(&[DXGI_FORMAT_R16G16B16A16_FLOAT, DXGI_FORMAT_R8G8B8A8_UNORM_SRGB]),
    };
    check_case("float_and_srgb_only", &g, &[]);
}
