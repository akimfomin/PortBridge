"""Compile the actual texture view-policy functions against a CPU-only D3D12 mock."""
import argparse
import os
from pathlib import Path
import re
import subprocess


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--repo", type=Path, required=True)
parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
parser.add_argument("--rustc", default="rustc")
parser.add_argument("--linker", type=Path)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=True)
repo = args.repo.resolve()
host = (repo / "crates/victory-gpu/src/descriptor/host.rs").read_text(encoding="utf-8")
resource = (repo / "crates/victory-gpu/src/resource.rs").read_text(encoding="utf-8")


def function(source, name):
    start = re.search(rf"(?m)^(?:pub\(crate\) )?fn {name}\(", source).start()
    left = source.index("{", start)
    nesting = 1
    for i in range(left + 1, len(source)):
        if source[i] == "{":
            nesting += 1
        elif source[i] == "}":
            nesting -= 1
            if nesting == 0:
                return source[start:i + 1]
    raise AssertionError(name)


stub = r'''
#![allow(non_snake_case, non_camel_case_types)]
use std::ffi::c_void;
use std::mem::size_of_val;
use std::sync::atomic::{AtomicU32, Ordering};
macro_rules! once { ($($anything:tt)*) => {} }

#[derive(Clone, Copy)]
struct DXGI_FORMAT(i32);
#[derive(Clone, Copy)]
struct Flags(i32);
const D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS: Flags = Flags(4);
const D3D12_RESOURCE_FLAG_DENY_SHADER_RESOURCE: Flags = Flags(8);
const D3D12_FEATURE_D3D12_OPTIONS3: u32 = 21;
struct ID3D12Device { report: bool, supported: bool }
static QUERIES: AtomicU32 = AtomicU32::new(0);
#[derive(Default)]
struct Bool(bool);
impl Bool { fn as_bool(&self) -> bool { self.0 } }
#[derive(Default)]
struct D3D12_FEATURE_DATA_D3D12_OPTIONS3 { CastingFullyTypedFormatSupported: Bool }
impl ID3D12Device {
    unsafe fn CheckFeatureSupport(&self, feature: u32, data: *mut c_void, size: u32) -> Result<(), ()> {
        assert_eq!(feature, D3D12_FEATURE_D3D12_OPTIONS3);
        assert_eq!(size, std::mem::size_of::<D3D12_FEATURE_DATA_D3D12_OPTIONS3>() as u32);
        QUERIES.fetch_add(1, Ordering::Relaxed);
        if self.report {
            unsafe { (*data.cast::<D3D12_FEATURE_DATA_D3D12_OPTIONS3>()).CastingFullyTypedFormatSupported.0 = self.supported; }
            Ok(())
        } else { Err(()) }
    }
}
#[derive(Clone, Copy)]
struct ID3D12Resource { Format: DXGI_FORMAT, Flags: Flags }
impl ID3D12Resource {
    unsafe fn GetDesc(&self) -> Self { *self }
}
'''
stub += "mod resource {\n"
stub += function(resource, "family")
for constant in ("DEPTH_FORMATS", "SRGB"):
    stub += "\n" + re.search(rf"(?m)^pub\(crate\) const {constant}:.*;$", resource)[0]
stub += """
    use std::sync::atomic::AtomicU64;
    pub(crate) static DEPTH_UNORDERED: [AtomicU64; 4] = [const { AtomicU64::new(0) }; 4];
    pub(crate) fn target_format(value: u32) -> u32 { value }
}
"""
fits = function(host, "fits")
for name in ("is_rgba8_gamma_cast", "supports_typed_format_casting"):
    if re.search(rf"(?m)^fn {name}\(", host):
        stub += function(host, name) + "\n"
stub += fits + "\n"
call = "fits(device, &texture, requested.as_mut(), unordered)" if "device: &ID3D12Device" in fits else (
    "fits(&texture, requested.as_mut(), unordered)"
)
stub += r'''
fn select(device: &ID3D12Device, own: i32, view: Option<i32>, flags: i32, unordered: bool) -> Option<i32> {
    let texture = ID3D12Resource { Format: DXGI_FORMAT(own), Flags: Flags(flags) };
    let mut requested = view.map(DXGI_FORMAT);
    if SELECT_IMPL { Some(requested.map_or(own, |f| f.0)) } else { None }
}

fn sampled_channel(value: u8, srgb: bool) -> f64 {
    let x = f64::from(value) / 255.0;
    if !srgb { x }
    else if x <= 0.04045 { x / 12.92 }
    else { ((x + 0.055) / 1.055).powf(2.4) }
}

fn main() {
    let mode = std::env::args().nth(1).unwrap();
    let device = ID3D12Device { report: mode != "query-failed", supported: mode != "unsupported" };
    let actual = mode == "supported";
    let unorm = 28;
    let srgb = 29;
    assert_eq!(select(&device, unorm, Some(30), 0, false), Some(unorm), "outside this color pair");
    assert_eq!(select(&device, unorm, Some(91), 0, false), None, "other format family");
    assert_eq!(select(&device, unorm, None, 0, false), Some(unorm), "implicit read view");
    assert_eq!(select(&device, unorm, Some(srgb), 8, false), None, "deny SRV");
    assert_eq!(select(&device, unorm, Some(srgb), 4, true), Some(unorm), "UAV stays linear");
    assert_eq!(select(&device, 27, Some(srgb), 0, false), Some(srgb), "typeless SRV");
    assert_eq!(QUERIES.load(Ordering::Relaxed), 0, "unrelated paths query no adapter features");
    let sampled = select(&device, unorm, Some(srgb), 0, false).unwrap();
    println!("{mode}: view={sampled}, sampled RGB at byte 0x80={:.8}, alpha={:.8}",
             sampled_channel(0x80, sampled == srgb), sampled_channel(0x80, false));
    assert_eq!(sampled, if actual { srgb } else { unorm }, "UNORM resource with an sRGB SRV");
    assert_eq!(select(&device, srgb, Some(unorm), 0, false), Some(if actual { unorm } else { srgb }),
               "sRGB resource with a linear SRV");
    assert_eq!(QUERIES.load(Ordering::Relaxed), 1, "one query per host device");
}
'''.replace("SELECT_IMPL", call)
src, exe = out / "extracted-policy.rs", out / "extracted-policy.exe"
src.write_text(stub, encoding="utf-8")
env = os.environ.copy()
arguments = [args.rustc, "--edition", "2024", "-A", "unused"]
if args.linker:
    arguments += ["-C", f"linker={args.linker.resolve()}"]
    env["PATH"] = str(args.linker.resolve().parent) + os.pathsep + env["PATH"]
subprocess.run([*arguments, "-o", exe, src], env=env, check=True, timeout=12)
for mode in ("supported", "unsupported", "query-failed"):
    subprocess.run([exe, mode], check=True, timeout=3)
