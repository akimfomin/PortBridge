// SPDX-License-Identifier: GPL-3.0-or-later
//! Single-dispatch, fixed-input readback wrapper for exact VIctory #1716 evidence.

#[allow(dead_code)]
#[path = "host_slice.rs"]
mod host;

use host::{Dispatch, Host, Root, View};
use victory_shader::emit::{HostShader, ROOT_CBV_SPACE, SAMPLER_SPACE, USER_DATA_SPACE, UserData};
use victory_shader::{HwStage, RootType};
use windows::Win32::Graphics::Dxgi::{
    CreateDXGIFactory2, DXGI_ADAPTER_FLAG_SOFTWARE, DXGI_CREATE_FACTORY_FLAGS, IDXGIAdapter1,
    IDXGIFactory4,
};

const ADAPTER: &str = "NVIDIA GeForce RTX 4070 Ti SUPER";
const INPUTS: [u32; 2] = [0x1357_9bdf, 0x2468_ace0];

struct Case {
    arm: &'static str,
    width: usize,
    seeds: usize,
    dxil: &'static [u8],
}

include!("case_table.rs");

fn check_adapter(host: &Host) -> Result<(), String> {
    // SAFETY: use the live device's adapter LUID to query its DXGI description.
    let (luid, description) = unsafe {
        let luid = host.device.GetAdapterLuid();
        let factory: IDXGIFactory4 =
            CreateDXGIFactory2(DXGI_CREATE_FACTORY_FLAGS(0)).map_err(|e| e.to_string())?;
        let adapter: IDXGIAdapter1 = factory.EnumAdapterByLuid(luid).map_err(|e| e.to_string())?;
        (luid, adapter.GetDesc1().map_err(|e| e.to_string())?)
    };
    let end = description.Description.iter().position(|&word| word == 0)
        .unwrap_or(description.Description.len());
    let name = String::from_utf16_lossy(&description.Description[..end]);
    let name = name.trim();
    if name != ADAPTER
        || description.VendorId != 0x10de
        || description.Flags & DXGI_ADAPTER_FLAG_SOFTWARE.0 as u32 != 0
    {
        return Err(format!("Expected native {ADAPTER}; found {name}"));
    }
    println!("ADAPTER {name} LUID {:08x}:{:08x}", luid.HighPart as u32, luid.LowPart);
    Ok(())
}

fn run() -> Result<(), String> {
    if std::env::var("PORTBRIDGE_VICTORY_READBACK").as_deref() != Ok("1") {
        return Err("Native readback requires the approved guarded runner".into());
    }
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [arm, width, seeds] = args.as_slice() else {
        return Err("Expected a fixed arm, register count and seed count".into());
    };
    let width: usize = width.parse().map_err(|_| "invalid register count")?;
    let seeds: usize = seeds.parse().map_err(|_| "invalid seed count")?;
    let case = CASES.iter().find(|case| case.arm == arm && case.width == width && case.seeds == seeds)
        .ok_or("input is outside the embedded allowlist")?;

    // The signed fixtures read s0/s1 from cbuffer dword 0/1 and the synthetic
    // table from dword 4. The readback owns the only heap slot, at index 0.
    let mut user_data: Vec<_> = (0..case.seeds as u32)
        .map(|index| UserData { index, slot: 0, root: RootType::Constants, dword: index })
        .collect();
    user_data.push(UserData { index: 4, slot: 1, root: RootType::Table, dword: 0 });
    let shader = HostShader {
        stage: HwStage::Cs,
        dxil: case.dxil.to_vec(),
        user_data,
        samplers: Vec::new(),
        static_samplers: Vec::new(),
        root_cbvs: Vec::new(),
        root_srvs: Vec::new(),
    };
    let mut constants = vec![0; shader.user_data_dwords() as usize];
    constants[..case.seeds].copy_from_slice(&INPUTS[..case.seeds]);
    let host = Host::new(false)?;
    check_adapter(&host)?;
    let (root, pso) = host.compute_pipeline(&shader)?;
    let readback = host.dispatch(&root, &pso, &Dispatch {
        roots: vec![(0, Root::Constants(constants))],
        views: &[View::RawUav(case.width as u32)],
        samplers: &[],
        groups: [1, 1, 1],
    })?;
    let [words] = readback.as_slice() else { return Err("expected exactly one output view".into()) };
    if words.len() != case.width {
        return Err(format!("expected {} words, got {}", case.width, words.len()));
    }
    print!("OUT");
    for word in words {
        print!(" {word:08x}");
    }
    println!();
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
