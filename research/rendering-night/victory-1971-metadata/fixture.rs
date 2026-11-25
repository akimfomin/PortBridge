// SPDX-License-Identifier: GPL-3.0-or-later
//! Bounded integration probe for the actual #1971 metadata producer.
#![allow(dead_code)]

use std::ffi::c_void;
use std::mem::{ManuallyDrop, size_of};
use std::path::Path;
use std::ptr::null_mut;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};
use windows::Win32::Graphics::Direct3D::D3D_FEATURE_LEVEL_12_0;
use windows::Win32::Graphics::Direct3D12::*;
use windows::Win32::Graphics::Dxgi::{Common::*, *};
use windows::core::{HSTRING, Interface, Result};
use windows_sys::Win32::System::JobObjects::*;

const ADAPTER: &str = "NVIDIA GeForce RTX 4070 Ti SUPER";
const JOB_BYTES: usize = 512 * 1024 * 1024;
const HEAP_SLOTS: u32 = 4;
const OUTPUT_BYTES: u64 = 5 * 16;
type Row = [u32; 4];
type Readback = [Row; 5];
const ZERO: Row = [0; 4];
const HEADER: Row = [HEAP_SLOTS, 0, 0, 0];
// Hand-encoded from the fixture dimensions after applying MostDetailedMip.
const ARRAY_FIRST: Row = [0, 0xc000_0000, 0x0005_4008, 0xd001_0000]; // 36x22, 2 mips
const ARRAY_REWRITE: Row = [0, 0x4000_0000, 0x0002_8004, 0xd000_0000]; // 18x11, 1 mip
const OTHER_FIRST: Row = [0, 0xc000_0000, 0x0001_c002, 0x9000_0000]; // 12x8, 1 mip
const OTHER_SECOND: Row = [0, 0xc000_0000, 0x0000_c003, 0x9001_0000]; // 16x4, 2 mips

extern crate self as tracing;
#[macro_export]
macro_rules! warn {
    (error = %$error:ident, $size:ident, $message:literal) => {
        eprintln!("{}: {} ({} bytes)", $message, $error, $size)
    };
    ($index:ident, count = $count:expr, $draw:ident, $message:literal) => {
        eprintln!("{}: index={} count={} draw={}", $message, $index, $count, $draw)
    };
}

mod object {
    pub type This = usize;
}

mod resource {
    use super::*;
    pub fn pc_format(format: u32) -> u32 {
        format
    }
    pub fn buffer_bytes(_: object::This) -> Option<(usize, u64)> {
        unreachable!("object-backed buffer views are outside this fixture")
    }
    pub fn host_resource(_: object::This) -> Option<ID3D12Resource> {
        unreachable!("object-backed resource views are outside this fixture")
    }
    pub fn element(_: u32) -> Option<(u64, u32)> {
        unreachable!("typed buffer views are outside this fixture")
    }
}

struct Host {
    device: ID3D12Device,
}
static HOST: OnceLock<Host> = OnceLock::new();

mod host {
    use super::*;
    pub fn name(buffer: &ID3D12Resource, text: impl FnOnce() -> String) {
        // SAFETY: a live upload buffer owned by the metadata table.
        let _ = unsafe { buffer.SetName(&HSTRING::from(text())) };
    }
}

fn host() -> Option<&'static Host> {
    HOST.get()
}

// The isolated test calls the exact HostHeap::mirror on a chosen heap and slot.
// The global title-CPU-address-to-heap lookup is outside the fixture.
fn mirror(_: u64) {}

struct ViewTracking;
impl ViewTracking {
    fn set(&self, _: u32, view: Option<&View>, materialized: bool) {
        assert!(!materialized && view.is_some_and(is_placed_texture));
    }
}

struct HostHeap {
    native: Option<(ID3D12DescriptorHeap, u32)>,
    count: u32,
    sampler: bool,
    records: Mutex<SlotRecords>,
    addresses: OnceLock<Option<(ID3D12Resource, usize, u64)>>,
    viewed: ViewTracking,
}

impl HostHeap {
    fn fixture() -> Result<Self> {
        let native = match host() {
            None => None,
            Some(host) => {
                let desc = D3D12_DESCRIPTOR_HEAP_DESC {
                    Type: D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV,
                    NumDescriptors: HEAP_SLOTS,
                    Flags: D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE,
                    NodeMask: 0,
                };
                // SAFETY: a valid four-slot test heap on the selected device.
                let heap: ID3D12DescriptorHeap = unsafe { host.device.CreateDescriptorHeap(&desc)? };
                let step = unsafe { host.device.GetDescriptorHandleIncrementSize(desc.Type) };
                Some((heap, step))
            }
        };
        Ok(Self {
            native, count: HEAP_SLOTS, sampler: false, viewed: ViewTracking,
            records: Mutex::new(SlotRecords {
                made: vec![0; HEAP_SLOTS as usize], deferred_metadata: Default::default(),
            }),
            addresses: OnceLock::new(),
        })
    }

    fn cpu(&self, index: u32) -> D3D12_CPU_DESCRIPTOR_HANDLE {
        assert!(index < self.count);
        let ptr = self.native.as_ref().map_or(0, |(heap, step)| {
            // SAFETY: index is inside the live heap.
            unsafe { heap.GetCPUDescriptorHandleForHeapStart() }.ptr + (index * step) as usize
        });
        D3D12_CPU_DESCRIPTOR_HANDLE { ptr }
    }

    fn make_null(&self, _: u32) {
        unreachable!("these placed texture views are always deferred")
    }
    fn set_stride(&self, _: u32, view: Option<&View>) {
        assert!(view.is_some_and(is_placed_texture));
    }
    fn set_mark(&self, _: u32, mark: Option<u32>) {
        assert!(mark.is_none());
    }
    fn keep(&self, _: u32, kept: Option<ID3D12Resource>) {
        assert!(kept.is_none());
    }
}

fn make_marked(_: &View, _: D3D12_CPU_DESCRIPTOR_HANDLE)
    -> (Option<Option<ID3D12Resource>>, Option<u32>)
{
    unreachable!("the test only reads metadata for deferred placed textures")
}

fn null_for(view: &View, at: D3D12_CPU_DESCRIPTOR_HANDLE) {
    let Some(h) = host() else { return };
    let View::Placed(false, _, words) = *view else { unreachable!() };
    let mut desc = D3D12_SHADER_RESOURCE_VIEW_DESC {
        Format: DXGI_FORMAT_R8G8B8A8_UNORM,
        Shader4ComponentMapping: D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING,
        ..Default::default()
    };
    if words[1] == D3D12_SRV_DIMENSION_TEXTURE2DARRAY.0 as u32 {
        desc.ViewDimension = D3D12_SRV_DIMENSION_TEXTURE2DARRAY;
        desc.Anonymous.Texture2DArray = D3D12_TEX2D_ARRAY_SRV {
            ArraySize: 1, MipLevels: 1, ..Default::default()
        };
    } else {
        assert_eq!(words[1], D3D12_SRV_DIMENSION_TEXTURE2D.0 as u32);
        desc.ViewDimension = D3D12_SRV_DIMENSION_TEXTURE2D;
        desc.Anonymous.Texture2D = D3D12_TEX2D_SRV { MipLevels: 1, ..Default::default() };
    }
    // SAFETY: a live fixture heap slot and a supported typed null descriptor.
    unsafe { h.device.CreateShaderResourceView(None::<&ID3D12Resource>, Some(&desc), at) };
}

include!(env!("PB_METADATA_SOURCE"));

fn texture(width: u32, height: u32, layers: u32, mips: u32, mip: u32, levels: u32) -> View {
    let mut res = [0; 14];
    res[0] = D3D12_RESOURCE_DIMENSION_TEXTURE2D.0 as u32;
    res[4] = width;
    res[6] = height;
    res[7] = (mips << 16) | layers;
    res[9] = 1;
    let mut desc = [0; 16];
    desc[0] = DXGI_FORMAT_R8G8B8A8_UNORM.0 as u32;
    desc[1] = if layers > 1 { D3D12_SRV_DIMENSION_TEXTURE2DARRAY } else { D3D12_SRV_DIMENSION_TEXTURE2D }.0 as u32;
    desc[2] = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
    desc[4] = mip;
    desc[5] = levels;
    if layers > 1 {
        desc[7] = layers;
    }
    View::Placed(false, res, desc)
}

fn write_slot(heap: &HostHeap, index: u32, slot: &mut Row, view: View) {
    let handle = slot.as_mut_ptr() as u64;
    record(handle, view.clone());
    assert_eq!(heap.mirror(index, handle, false), Some(view));
}

fn expect_encoded(view: &View, expected: Row) {
    let mut words = [[0x7777_7777; 4]; 6];
    write_address(words.as_mut_ptr() as usize, 1, Some(view));
    assert_eq!(words[3], expected);
    assert_eq!(words[2], [0x7777_7777; 4]);
    assert_eq!(words[4], [0x7777_7777; 4]);
}

fn mock() -> Result<()> {
    let heap = HostHeap::fixture()?;
    let first = texture(72, 44, 2, 4, 1, 2);
    let rewritten = texture(72, 44, 2, 4, 2, 1);
    expect_encoded(&first, ARRAY_FIRST);
    expect_encoded(&rewritten, ARRAY_REWRITE);
    expect_encoded(&texture(12, 8, 1, 1, 0, 1), OTHER_FIRST);
    expect_encoded(&texture(16, 4, 1, 2, 0, 2), OTHER_SECOND);
    let mut slot = ZERO;
    write_slot(&heap, 1, &mut slot, first);
    let old = heap.records.lock().unwrap().deferred_metadata[&1];
    write_slot(&heap, 1, &mut slot, rewritten.clone());
    let new = heap.records.lock().unwrap().deferred_metadata[&1];
    assert_ne!(old, new);
    assert_eq!(view_at(new as u32, (new >> 32) as u32), Some(rewritten));
    slot.fill(0);
    assert_eq!(heap.mirror(1, slot.as_ptr() as u64, false), None);
    assert!(heap.records.lock().unwrap().deferred_metadata.is_empty());
    println!("exact metadata encoding and deferred registry passed");
    Ok(())
}

fn enforce_guard() {
    let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
    // SAFETY: a live output buffer matching the queried Windows structure.
    let ok = unsafe {
        QueryInformationJobObject(null_mut(), JobObjectExtendedLimitInformation,
            (&mut info as *mut JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
            size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32, null_mut())
    };
    let flags = JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    assert!(ok != 0 && info.BasicLimitInformation.LimitFlags & flags == flags &&
            info.ProcessMemoryLimit == JOB_BYTES && info.JobMemoryLimit == JOB_BYTES);
}

fn container(path: &str) -> Vec<u8> {
    let metadata = std::fs::metadata(Path::new(path)).expect("source-generated container metadata");
    assert!(metadata.is_file() && (32..=4096).contains(&metadata.len()));
    let bytes = std::fs::read(path).expect("source-generated container");
    assert!(bytes.len() as u64 == metadata.len() && bytes.starts_with(b"DXBC"));
    bytes
}

fn open_device(adapter_name: &str) -> Result<ID3D12Device> {
    assert_eq!(adapter_name, ADAPTER);
    // SAFETY: find one explicitly named native hardware adapter before opening a device.
    unsafe {
        let factory: IDXGIFactory4 = CreateDXGIFactory2(DXGI_CREATE_FACTORY_FLAGS(0))?;
        let mut selected = None;
        for index in 0..64 {
            let adapter = match factory.EnumAdapters1(index) {
                Ok(adapter) => adapter,
                Err(err) if err.code() == DXGI_ERROR_NOT_FOUND => break,
                Err(err) => return Err(err),
            };
            let desc = adapter.GetDesc1()?;
            let end = desc.Description.iter().position(|&c| c == 0).unwrap_or(desc.Description.len());
            if desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE.0 as u32 == 0 && desc.VendorId == 0x10de &&
                String::from_utf16_lossy(&desc.Description[..end]) == adapter_name
            {
                assert!(selected.replace((adapter, desc)).is_none());
            }
        }
        let (adapter, desc) = selected.expect("unique RTX adapter");
        let driver = adapter.CheckInterfaceSupport(&IDXGIDevice::IID)?;
        let mut device = None;
        D3D12CreateDevice(&adapter, D3D_FEATURE_LEVEL_12_0, &mut device)?;
        println!("adapter={adapter_name} luid={:08x}:{:08x} driver={driver:016x}",
                 desc.AdapterLuid.HighPart as u32, desc.AdapterLuid.LowPart);
        Ok(device.expect("D3D12 device"))
    }
}

fn buffer(device: &ID3D12Device, kind: D3D12_HEAP_TYPE, state: D3D12_RESOURCE_STATES,
          flags: D3D12_RESOURCE_FLAGS) -> Result<ID3D12Resource> {
    let heap = D3D12_HEAP_PROPERTIES { Type: kind, ..Default::default() };
    let desc = D3D12_RESOURCE_DESC {
        Dimension: D3D12_RESOURCE_DIMENSION_BUFFER, Width: OUTPUT_BYTES, Height: 1,
        DepthOrArraySize: 1, MipLevels: 1, SampleDesc: DXGI_SAMPLE_DESC { Count: 1, Quality: 0 },
        Layout: D3D12_TEXTURE_LAYOUT_ROW_MAJOR, Flags: flags, ..Default::default()
    };
    let mut out = None;
    // SAFETY: a valid buffer descriptor with the corresponding initial heap state.
    unsafe { device.CreateCommittedResource(&heap, D3D12_HEAP_FLAG_NONE, &desc, state, None, &mut out)? };
    Ok(out.expect("output buffer"))
}

struct Dispatch {
    device: ID3D12Device,
    queue: ID3D12CommandQueue,
    root: ID3D12RootSignature,
    pipeline: ID3D12PipelineState,
}

impl Dispatch {
    fn new(device: ID3D12Device, shader: &[u8], signature: &[u8]) -> Result<Self> {
        // SAFETY: the source-generated shader and root signature remain live for PSO creation.
        unsafe {
            let queue = device.CreateCommandQueue(&D3D12_COMMAND_QUEUE_DESC {
                Type: D3D12_COMMAND_LIST_TYPE_COMPUTE, ..Default::default()
            })?;
            let root: ID3D12RootSignature = device.CreateRootSignature(0, signature)?;
            let mut desc = D3D12_COMPUTE_PIPELINE_STATE_DESC {
                pRootSignature: ManuallyDrop::new(Some(root.clone())),
                CS: D3D12_SHADER_BYTECODE { pShaderBytecode: shader.as_ptr().cast(), BytecodeLength: shader.len() },
                ..Default::default()
            };
            let made = device.CreateComputePipelineState(&desc);
            ManuallyDrop::drop(&mut desc.pRootSignature);
            let pipeline = made?;
            Ok(Self { device, queue, root, pipeline })
        }
    }

    fn read(&self, heap: &HostHeap) -> Result<Readback> {
        let address = heap.view_addresses().expect("production GPU metadata table");
        let (metadata, cpu, _) = heap.addresses.get().and_then(Option::as_ref).unwrap();
        assert_ne!(address, 0);
        // SAFETY: metadata is a live 96-byte upload buffer, with no outstanding prior dispatch.
        unsafe {
            assert_eq!(metadata.GetDesc().Width, (u64::from(HEAP_SLOTS) + 2) * 16);
            assert_eq!((*cpu as *const Row).read_unaligned(), HEADER);
            assert_eq!(((*cpu + 16) as *const Row).read_unaligned(), ZERO);
        }
        let output = buffer(&self.device, D3D12_HEAP_TYPE_DEFAULT, D3D12_RESOURCE_STATE_UNORDERED_ACCESS,
                            D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS)?;
        let readback = buffer(&self.device, D3D12_HEAP_TYPE_READBACK, D3D12_RESOURCE_STATE_COPY_DEST,
                              D3D12_RESOURCE_FLAG_NONE)?;
        // SAFETY: fresh local command objects, compatible roots and fenced readback per dispatch.
        unsafe {
            let allocator: ID3D12CommandAllocator = self.device.CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_COMPUTE)?;
            let list: ID3D12GraphicsCommandList = self.device.CreateCommandList(
                0, D3D12_COMMAND_LIST_TYPE_COMPUTE, &allocator, &self.pipeline)?;
            let fence: ID3D12Fence = self.device.CreateFence(0, D3D12_FENCE_FLAG_NONE)?;
            list.SetComputeRootSignature(&self.root);
            list.SetComputeRootShaderResourceView(0, address);
            list.SetComputeRootUnorderedAccessView(1, output.GetGPUVirtualAddress());
            list.Dispatch(1, 1, 1);
            let mut transition = ManuallyDrop::new(D3D12_RESOURCE_TRANSITION_BARRIER {
                pResource: ManuallyDrop::new(Some(output.clone())),
                Subresource: D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,
                StateBefore: D3D12_RESOURCE_STATE_UNORDERED_ACCESS,
                StateAfter: D3D12_RESOURCE_STATE_COPY_SOURCE,
            });
            list.ResourceBarrier(&[D3D12_RESOURCE_BARRIER {
                Type: D3D12_RESOURCE_BARRIER_TYPE_TRANSITION,
                Flags: D3D12_RESOURCE_BARRIER_FLAG_NONE,
                Anonymous: D3D12_RESOURCE_BARRIER_0 {
                    Transition: std::mem::transmute_copy(&transition),
                },
            }]);
            ManuallyDrop::drop(&mut transition.pResource);
            list.CopyBufferRegion(&readback, 0, &output, 0, OUTPUT_BYTES);
            list.Close()?;
            self.queue.ExecuteCommandLists(&[Some(list.cast()?)]);
            if let Err(e) = self.queue.Signal(&fence, 1) {
                eprintln!("could not fence submitted work: {e}");
                std::process::exit(123);
            }
            let deadline = Instant::now() + Duration::from_millis(500);
            while fence.GetCompletedValue() == 0 {
                if Instant::now() >= deadline {
                    eprintln!("metadata readback exceeded its bounded fence deadline");
                    std::process::exit(124);
                }
                std::thread::sleep(Duration::from_millis(1));
            }
            self.device.GetDeviceRemovedReason()?;
            let range = D3D12_RANGE { Begin: 0, End: OUTPUT_BYTES as usize };
            let mut mapped: *mut c_void = null_mut();
            readback.Map(0, Some(&range), Some(&mut mapped))?;
            assert!(!mapped.is_null());
            let result = mapped.cast::<Readback>().read_unaligned();
            readback.Unmap(0, Some(&D3D12_RANGE { Begin: 0, End: 0 }));
            Ok(result)
        }
    }
}

fn native(adapter: &str, shader: &str, rootsig: &str) -> Result<()> {
    enforce_guard();
    let (shader, root) = (container(shader), container(rootsig));
    let device = open_device(adapter)?;
    assert!(HOST.set(Host { device: device.clone() }).is_ok());
    let dispatch = Dispatch::new(device, &shader, &root)?;
    let (a, b) = (HostHeap::fixture()?, HostHeap::fixture()?);
    let (mut a1, mut b1, mut b2) = (ZERO, ZERO, ZERO);
    write_slot(&a, 1, &mut a1, texture(72, 44, 2, 4, 1, 2));
    write_slot(&b, 1, &mut b1, texture(12, 8, 1, 1, 0, 1));
    write_slot(&b, 2, &mut b2, texture(16, 4, 1, 2, 0, 2));
    assert!(a.addresses.get().is_none() && b.addresses.get().is_none());
    let verify = |label, heap, first, second| -> Result<()> {
        let got = dispatch.read(heap)?;
        println!("{label}: {got:08x?}");
        assert_eq!(got, [HEADER, first, second, ZERO, ZERO], "{label}");
        Ok(())
    };
    verify("initial deferred A", &a, ARRAY_FIRST, ZERO)?;
    let address = a.view_addresses().unwrap();
    write_slot(&a, 1, &mut a1, texture(72, 44, 2, 4, 2, 1));
    verify("rewritten A", &a, ARRAY_REWRITE, ZERO)?;
    assert_eq!(a.view_addresses().unwrap(), address);
    verify("alternate B", &b, OTHER_FIRST, OTHER_SECOND)?;
    assert_ne!(b.view_addresses().unwrap(), address);
    a1.fill(0);
    assert!(a.mirror(1, a1.as_ptr() as u64, false).is_none());
    verify("returned A after clear", &a, ZERO, ZERO)?;
    println!("four exact metadata readbacks passed");
    Ok(())
}

fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let result = match args.as_slice() {
        [action] if action == "mock" => mock(),
        [action, adapter, shader, root] if action == "native" => native(adapter, shader, root),
        _ => panic!("expected mock or a guarded native run"),
    };
    if let Err(error) = result {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
