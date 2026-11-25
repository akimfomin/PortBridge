// SPDX-License-Identifier: GPL-3.0-or-later
use std::mem::{ManuallyDrop, size_of};
use windows::Win32::Foundation::E_INVALIDARG;
use windows::Win32::Graphics::Direct3D::{D3D_FEATURE_LEVEL_12_0, ID3DBlob};
use windows::Win32::Graphics::Direct3D12::*;
use windows::Win32::Graphics::Dxgi::Common::*;
use windows::Win32::Graphics::Dxgi::{
    CreateDXGIFactory2, DXGI_ADAPTER_FLAG_SOFTWARE, DXGI_CREATE_FACTORY_FLAGS, DXGI_ERROR_NOT_FOUND,
    IDXGIAdapter1, IDXGIFactory4,
};

const EXPECTED_ADAPTER: &str = "NVIDIA GeForce RTX 4070 Ti SUPER";
const VERTEX: &[u8] = include_bytes!("build/vertex.dxil");
const PIXEL: &[u8] = include_bytes!("build/pixel.dxil");
const INTEGER_FORMAT: DXGI_FORMAT = DXGI_FORMAT_R8_UINT;
const FLOAT_FORMAT: DXGI_FORMAT = DXGI_FORMAT_R16G16B16A16_FLOAT;

struct GraphicsState {
    blend: D3D12_BLEND_DESC,
    targets: D3D12_RT_FORMAT_ARRAY,
}

#[allow(dead_code)]
mod baseline {
    use super::*;
    include!("../ab/baseline/host_blend.rs");
    pub fn choose(g: &GraphicsState) -> D3D12_BLEND_DESC {
        graphics(g)
    }
}

#[allow(dead_code)]
mod candidate {
    use super::*;
    include!("../ab/candidate/host_blend.rs");
    pub fn choose(g: &GraphicsState) -> D3D12_BLEND_DESC {
        graphics(g)
    }
}

fn adapter() -> Result<IDXGIAdapter1, String> {
    // SAFETY: the factory and returned adapters are live COM objects.
    unsafe {
        let factory: IDXGIFactory4 = CreateDXGIFactory2(DXGI_CREATE_FACTORY_FLAGS(0))
            .map_err(|error| format!("DXGI factory: {error}"))?;
        for index in 0..16 {
            let adapter = match factory.EnumAdapters1(index) {
                Ok(adapter) => adapter,
                Err(error) if error.code() == DXGI_ERROR_NOT_FOUND => break,
                Err(error) => return Err(format!("DXGI adapter enumeration: {error}")),
            };
            let desc = adapter.GetDesc1().map_err(|error| error.to_string())?;
            let end = desc.Description.iter().position(|&unit| unit == 0).unwrap_or(desc.Description.len());
            let name = String::from_utf16_lossy(&desc.Description[..end]);
            if name.trim() == EXPECTED_ADAPTER
                && desc.VendorId == 0x10de
                && desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE.0 as u32 == 0
            {
                println!("ADAPTER {EXPECTED_ADAPTER} LUID {:08x}:{:08x}", desc.AdapterLuid.HighPart as u32, desc.AdapterLuid.LowPart);
                return Ok(adapter);
            }
        }
    }
    Err(format!("required adapter unavailable: {EXPECTED_ADAPTER}"))
}

fn format_support(device: &ID3D12Device, format: DXGI_FORMAT, blendable: bool) -> Result<(), String> {
    let mut support = D3D12_FEATURE_DATA_FORMAT_SUPPORT { Format: format, ..Default::default() };
    // SAFETY: the selected query matches the typed writable structure and its size.
    unsafe {
        device.CheckFeatureSupport(
            D3D12_FEATURE_FORMAT_SUPPORT,
            (&raw mut support).cast(),
            size_of::<D3D12_FEATURE_DATA_FORMAT_SUPPORT>() as u32,
        ).map_err(|error| format!("format support: {error}"))?;
    }
    if support.Support1.0 & D3D12_FORMAT_SUPPORT1_RENDER_TARGET.0 == 0
        || (support.Support1.0 & D3D12_FORMAT_SUPPORT1_BLENDABLE.0 != 0) != blendable
    {
        return Err(format!("unexpected features for DXGI {}: {:#x}", format.0, support.Support1.0));
    }
    println!("FORMAT {} render_target=1 blendable={}", format.0, u8::from(blendable));
    Ok(())
}

fn root_signature(device: &ID3D12Device) -> Result<ID3D12RootSignature, String> {
    let desc = D3D12_ROOT_SIGNATURE_DESC {
        Flags: D3D12_ROOT_SIGNATURE_FLAG_ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT,
        ..Default::default()
    };
    let mut blob: Option<ID3DBlob> = None;
    // SAFETY: desc has no parameters or samplers. The returned blob owns the bytes.
    unsafe {
        D3D12SerializeRootSignature(&desc, D3D_ROOT_SIGNATURE_VERSION_1, &mut blob, None)
            .map_err(|error| format!("serialize empty root signature: {error}"))?;
        let blob = blob.ok_or("empty root signature blob missing")?;
        let bytes = std::slice::from_raw_parts(blob.GetBufferPointer().cast(), blob.GetBufferSize());
        device.CreateRootSignature(0, bytes).map_err(|error| format!("create empty root signature: {error}"))
    }
}

fn input() -> GraphicsState {
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
        RenderTargetWriteMask: D3D12_COLOR_WRITE_ENABLE_ALL.0 as u8,
    };
    let mut formats = [DXGI_FORMAT_UNKNOWN; 8];
    formats[0] = INTEGER_FORMAT;
    formats[1] = FLOAT_FORMAT;
    GraphicsState {
        blend: D3D12_BLEND_DESC {
            AlphaToCoverageEnable: false.into(),
            IndependentBlendEnable: false.into(),
            RenderTarget: [target; 8],
        },
        targets: D3D12_RT_FORMAT_ARRAY { NumRenderTargets: 2, RTFormats: formats },
    }
}

fn effective(blend: &D3D12_BLEND_DESC, slot: usize) -> D3D12_RENDER_TARGET_BLEND_DESC {
    blend.RenderTarget[if blend.IndependentBlendEnable.as_bool() { slot } else { 0 }]
}

fn bytecode(bytes: &[u8]) -> D3D12_SHADER_BYTECODE {
    D3D12_SHADER_BYTECODE { pShaderBytecode: bytes.as_ptr().cast(), BytecodeLength: bytes.len() }
}

fn run() -> Result<(), String> {
    if std::env::var("PORTBRIDGE_UINT_BLEND_APPROVED").as_deref() != Ok("1") {
        return Err("native PSO creation requires the approved job launcher".into());
    }
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [arm] = args.as_slice() else { return Err("select exactly one fixed arm".into()); };
    let g = input();
    let (blend, baseline) = match arm.as_str() {
        "baseline" => (baseline::choose(&g), true),
        "candidate" => (candidate::choose(&g), false),
        _ => return Err("unknown arm".into()),
    };
    if effective(&blend, 0).BlendEnable.as_bool() != baseline
        || effective(&blend, 1) != effective(&g.blend, 1)
        || blend.IndependentBlendEnable.as_bool() == baseline
    {
        return Err("actual blend expression differs from expected A/B".into());
    }
    println!("ARM {arm} uint_blend={} float_blend=1", u8::from(baseline));

    let adapter = adapter()?;
    let mut device: Option<ID3D12Device> = None;
    // SAFETY: the adapter is live and the device output matches its interface.
    unsafe { D3D12CreateDevice(&adapter, D3D_FEATURE_LEVEL_12_0, &mut device) }
        .map_err(|error| format!("D3D12 device: {error}"))?;
    let device = device.ok_or("D3D12 device missing")?;
    format_support(&device, INTEGER_FORMAT, false)?;
    format_support(&device, FLOAT_FORMAT, true)?;
    let root = root_signature(&device)?;
    let keep = D3D12_DEPTH_STENCILOP_DESC {
        StencilFailOp: D3D12_STENCIL_OP_KEEP,
        StencilDepthFailOp: D3D12_STENCIL_OP_KEEP,
        StencilPassOp: D3D12_STENCIL_OP_KEEP,
        StencilFunc: D3D12_COMPARISON_FUNC_ALWAYS,
    };
    let mut desc = D3D12_GRAPHICS_PIPELINE_STATE_DESC {
        pRootSignature: ManuallyDrop::new(Some(root)),
        VS: bytecode(VERTEX),
        PS: bytecode(PIXEL),
        BlendState: blend,
        SampleMask: u32::MAX,
        RasterizerState: D3D12_RASTERIZER_DESC {
            FillMode: D3D12_FILL_MODE_SOLID,
            CullMode: D3D12_CULL_MODE_NONE,
            DepthClipEnable: true.into(),
            ..Default::default()
        },
        DepthStencilState: D3D12_DEPTH_STENCIL_DESC {
            DepthWriteMask: D3D12_DEPTH_WRITE_MASK_ZERO,
            DepthFunc: D3D12_COMPARISON_FUNC_ALWAYS,
            StencilReadMask: u8::MAX,
            StencilWriteMask: u8::MAX,
            FrontFace: keep,
            BackFace: keep,
            ..Default::default()
        },
        IBStripCutValue: D3D12_INDEX_BUFFER_STRIP_CUT_VALUE_DISABLED,
        PrimitiveTopologyType: D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE,
        NumRenderTargets: g.targets.NumRenderTargets,
        RTVFormats: g.targets.RTFormats,
        SampleDesc: DXGI_SAMPLE_DESC { Count: 1, Quality: 0 },
        ..Default::default()
    };
    // SAFETY: shader bytecode and the retained root interface outlive the call.
    let result = unsafe { device.CreateGraphicsPipelineState::<ID3D12PipelineState>(&desc) };
    // SAFETY: the API call is over and the descriptor owns exactly one root reference.
    unsafe { ManuallyDrop::drop(&mut desc.pRootSignature) };
    // SAFETY: query of an existing device after PSO creation.
    unsafe { device.GetDeviceRemovedReason() }.map_err(|error| format!("device status: {error}"))?;
    match result {
        Ok(_) => println!("PSO {arm} 0x00000000"),
        Err(error) if baseline && error.code() == E_INVALIDARG => println!("PSO {arm} 0x80070057"),
        Err(error) => return Err(format!("unexpected PSO result for {arm}: {error}")),
    }
    Ok(())
}

fn main() {
    if let Err(message) = run() {
        eprintln!("ERROR {message}");
        std::process::exit(1);
    }
}
