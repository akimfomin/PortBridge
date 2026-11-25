// SPDX-License-Identifier: GPL-3.0-or-later
// Real D3D12 bindings for the extracted victory-fork pipeline-library methods.
use std::cell::RefCell;
use std::ffi::c_void;
use std::mem::{size_of, ManuallyDrop};
use std::path::Path;
use std::ptr::{null, null_mut};
#[cfg(pb_candidate)]
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::{self, Sender};
use std::sync::{Arc, Mutex, MutexGuard, OnceLock, RwLock};
#[cfg(pb_candidate)]
use std::sync::{Condvar, LazyLock};
use std::time::Duration;

use windows::core::{Error, HRESULT, HSTRING, Interface, PCWSTR, Result};
use windows::Win32::Foundation::{E_FAIL, E_INVALIDARG};
use windows::Win32::Graphics::Direct3D::D3D_FEATURE_LEVEL_12_0;
use windows::Win32::Graphics::Direct3D12::{
    D3D12CreateDevice, D3D12_COMPUTE_PIPELINE_STATE_DESC, D3D12_SHADER_BYTECODE, ID3D12Device,
    ID3D12Device1, ID3D12PipelineLibrary1 as D3dLibrary, ID3D12PipelineState as D3dState,
    ID3D12RootSignature,
};
use windows::Win32::Graphics::Dxgi::{
    CreateDXGIFactory2, DXGI_ADAPTER_FLAG_SOFTWARE, DXGI_CREATE_FACTORY_FLAGS, DXGI_ERROR_NOT_FOUND,
    IDXGIDevice, IDXGIFactory4,
};
use windows_sys::Win32::System::JobObjects::{
    JobObjectExtendedLimitInformation, QueryInformationJobObject, JOB_OBJECT_LIMIT_JOB_MEMORY,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, JOB_OBJECT_LIMIT_PROCESS_MEMORY,
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
};

const NAME: &str = "portbridge-single-flight-ps-0001";
const LIMIT: usize = 512 * 1024 * 1024;
const WAIT: Duration = Duration::from_millis(750);

struct Device {
    library: D3dLibrary,
    root: ID3D12RootSignature,
    device: ID3D12Device,
    shader: Vec<u8>,
}

impl Device {
    fn with_desc<T>(&self, call: impl FnOnce(&D3D12_COMPUTE_PIPELINE_STATE_DESC) -> T) -> T {
        let mut desc = D3D12_COMPUTE_PIPELINE_STATE_DESC {
            pRootSignature: ManuallyDrop::new(Some(self.root.clone())),
            CS: D3D12_SHADER_BYTECODE { pShaderBytecode: self.shader.as_ptr().cast(), BytecodeLength: self.shader.len() },
            ..Default::default()
        };
        let output = call(&desc);
        // SAFETY: `ManuallyDrop` owns just the temporary COM reference in this descriptor.
        unsafe { ManuallyDrop::drop(&mut desc.pRootSignature) };
        output
    }
}

enum PipelineState {
    Mock,
    D3d(D3dState),
}

type ID3D12PipelineState = PipelineState;
type ID3D12PipelineLibrary1 = NativeLibrary;

enum Backend {
    Mock(Mutex<bool>),
    D3d(Device),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Call {
    Load,
    Create,
    Store,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Event(Call, HRESULT);

struct NativeLibrary {
    backend: Backend,
    calls: Mutex<Vec<Event>>,
}

impl NativeLibrary {
    fn record<T>(&self, operation: Call, result: Result<T>) -> Result<T> {
        let status = result.as_ref().err().map_or(HRESULT(0), Error::code);
        self.calls.lock().unwrap().push(Event(operation, status));
        result
    }

    fn load(&self, name: PCWSTR) -> Result<PipelineState> {
        let result = match &self.backend {
            Backend::Mock(stored) => {
                if *stored.lock().unwrap() { Ok(PipelineState::Mock) } else { Err(E_INVALIDARG.into()) }
            }
            Backend::D3d(dev) => dev.with_desc(|desc| {
                // SAFETY: live COM library, UTF-16 name and the identical live descriptor.
                unsafe { dev.library.LoadComputePipeline::<_, D3dState>(name, desc) }.map(PipelineState::D3d)
            }),
        };
        self.record(Call::Load, result)
    }

    fn create(&self) -> Result<PipelineState> {
        let result = match &self.backend {
            Backend::Mock(_) => Ok(PipelineState::Mock),
            Backend::D3d(dev) => dev.with_desc(|desc| {
                // SAFETY: the owned shader and root signature outlive the call.
                unsafe { dev.device.CreateComputePipelineState::<D3dState>(desc) }.map(PipelineState::D3d)
            }),
        };
        self.record(Call::Create, result)
    }

    #[allow(non_snake_case)]
    unsafe fn StorePipeline(&self, name: PCWSTR, pso: &PipelineState) -> Result<()> {
        let result = match (&self.backend, pso) {
            (Backend::Mock(stored), PipelineState::Mock) => {
                let mut stored = stored.lock().unwrap();
                if *stored { Err(E_INVALIDARG.into()) } else { *stored = true; Ok(()) }
            }
            (Backend::D3d(dev), PipelineState::D3d(pso)) => {
                // SAFETY: the exact load name and a live PSO for its descriptor.
                unsafe { dev.library.StorePipeline(name, pso) }
            }
            _ => Err(E_FAIL.into()),
        };
        self.record(Call::Store, result)
    }
}

struct Library {
    library: NativeLibrary,
    added: AtomicU64,
    saving: RwLock<()>,
}

// The fixture substitutes only the lifetime of the library, never its name admission.
static TEST_LIBRARY: Mutex<Option<Arc<Library>>> = Mutex::new(None);
fn library() -> Option<Arc<Library>> {
    TEST_LIBRARY.lock().unwrap().clone()
}

static MADE: AtomicU64 = AtomicU64::new(0);
static LOADED: AtomicU64 = AtomicU64::new(0);
static LOADED_AT: AtomicU64 = AtomicU64::new(0);
static TRIMMED: AtomicBool = AtomicBool::new(false);

thread_local! {
    static LABEL: RefCell<String> = const { RefCell::new(String::new()) };
    #[cfg(pb_candidate)]
    static WAIT_SIGNAL: RefCell<Option<Sender<Progress>>> = const { RefCell::new(None) };
}

mod host {
    pub fn now_ms() -> u64 { 0 }
    pub fn trail(_: impl FnOnce() -> String) {}
}

struct TraceCall;
fn call(_: &str, _: &str) -> TraceCall { TraceCall }

#[derive(Debug, PartialEq, Eq)]
enum Progress {
    Create,
    #[cfg(pb_candidate)]
    Wait,
}

#[cfg(pb_candidate)]
fn observe_wait() {
    WAIT_SIGNAL.with_borrow_mut(|signal| {
        if let Some(notify) = signal.take() {
            notify.send(Progress::Wait).unwrap();
        }
    });
}

include!(env!("PB_EXTRACTED_SOURCE"));

fn request(create: impl FnOnce() -> Result<PipelineState>) -> Result<PipelineState> {
    pipeline(NAME, |library, name| library.load(name), create)
}

fn held_create(progress: Sender<Progress>, go: mpsc::Receiver<()>, lib: &NativeLibrary) -> Result<PipelineState> {
    progress.send(Progress::Create).expect("create boundary");
    go.recv_timeout(WAIT).expect("release exact request");
    lib.create()
}

fn verify_requests(backend: Backend) {
    let shared = Arc::new(Library {
        library: NativeLibrary { backend, calls: Mutex::new(Vec::new()) },
        added: AtomicU64::new(0),
        saving: RwLock::new(()),
    });
    *TEST_LIBRARY.lock().unwrap() = Some(shared.clone());
    let lib = &shared.library;
    std::thread::scope(|scope| {
        let (first_event, first_progress) = mpsc::channel();
        let (first_release, first_gate) = mpsc::channel();
        let first = scope.spawn(move || request(|| held_create(first_event, first_gate, lib)));
        assert_eq!(first_progress.recv_timeout(WAIT).unwrap(), Progress::Create);

        let (second_event, second_progress) = mpsc::channel();
        let (second_release, second_gate) = mpsc::channel();
        let second = scope.spawn(move || {
            #[cfg(pb_candidate)]
            WAIT_SIGNAL.with_borrow_mut(|signal| *signal = Some(second_event.clone()));
            request(|| held_create(second_event, second_gate, lib))
        });
        #[cfg(pb_candidate)]
        let reached = Progress::Wait;
        #[cfg(not(pb_candidate))]
        let reached = Progress::Create;
        let actual = second_progress.recv_timeout(WAIT).expect("proof of overlapping admission");
        println!("second boundary before first store: {actual:?}");
        assert_eq!(actual, reached);
        first_release.send(()).unwrap();
        let first_result = first.join();
        // The baseline's second real create may start only after the first real store.
        let _ = second_release.send(());
        let second_result = second.join();
        drop(first_result.unwrap().expect("first request"));
        drop(second_result.unwrap().expect("second request"));
    });

    let before_warm = lib.calls.lock().unwrap().clone();
    let ok = HRESULT(0);
    #[cfg(not(pb_candidate))]
    let expected = [
        Event(Call::Load, E_INVALIDARG), Event(Call::Load, E_INVALIDARG),
        Event(Call::Create, ok), Event(Call::Store, ok),
        Event(Call::Create, ok), Event(Call::Store, E_INVALIDARG),
    ];
    #[cfg(pb_candidate)]
    let expected = [
        Event(Call::Load, E_INVALIDARG), Event(Call::Create, ok),
        Event(Call::Store, ok), Event(Call::Load, ok),
    ];
    println!("overlapping request API outcomes: {before_warm:?}");
    assert_eq!(before_warm, expected);
    let warm = request(|| lib.create()).expect("warm library load");
    drop(warm);
    assert_eq!(lib.calls.lock().unwrap()[before_warm.len()..], [Event(Call::Load, ok)]);
    assert_eq!(MADE.load(Ordering::Relaxed), if cfg!(pb_candidate) { 1 } else { 2 });
    assert_eq!(LOADED.load(Ordering::Relaxed), if cfg!(pb_candidate) { 2 } else { 1 });
    assert_eq!(shared.added.load(Ordering::Relaxed), 1);
    #[cfg(pb_candidate)]
    assert!(ACTIVE_NAMES.lock().unwrap().is_empty());
    TEST_LIBRARY.lock().unwrap().take();
    println!("single-flight oracle passed, warm hit verified");
}

fn enforce_guard() {
    let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
    let bytes = size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32;
    // SAFETY: a live output buffer matching the queried Windows structure.
    let ok = unsafe { QueryInformationJobObject(null_mut(), JobObjectExtendedLimitInformation,
        (&mut info as *mut JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(), bytes, null_mut()) };
    let flags = JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    assert!(ok != 0 && info.BasicLimitInformation.LimitFlags & flags == flags &&
            info.ProcessMemoryLimit == LIMIT && info.JobMemoryLimit == LIMIT,
            "native worker requires the fixed Windows job");
}

fn container(path: &Path, max_bytes: u64) -> Vec<u8> {
    let metadata = std::fs::metadata(path).expect("source-generated container metadata");
    assert!(metadata.is_file() && (32..=max_bytes).contains(&metadata.len()));
    let bytes = std::fs::read(path).expect("source-generated container bytes");
    assert!(bytes.len() as u64 == metadata.len() && bytes.starts_with(b"DXBC"));
    bytes
}

fn device(selector: &str, shader: Vec<u8>, rootsig: Vec<u8>) -> Result<Device> {
    // SAFETY: fixed compute descriptors and a unique explicitly matched hardware adapter.
    unsafe {
        let factory: IDXGIFactory4 = CreateDXGIFactory2(DXGI_CREATE_FACTORY_FLAGS(0))?;
        let mut selected = None;
        for index in 0..64 {
            let adapter = match factory.EnumAdapters1(index) {
                Ok(adapter) => adapter,
                Err(e) if e.code() == DXGI_ERROR_NOT_FOUND => break,
                Err(e) => return Err(e),
            };
            let desc = adapter.GetDesc1()?;
            let length = desc.Description.iter().position(|&c| c == 0).unwrap_or(desc.Description.len());
            let name = String::from_utf16_lossy(&desc.Description[..length]);
            if desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE.0 as u32 == 0 && name == selector {
                assert!(selected.is_none(), "hardware adapter selector is not unique");
                selected = Some((adapter, desc));
            }
        }
        let (adapter, desc) = selected.ok_or_else(|| Error::from(E_INVALIDARG))?;
        let driver = adapter.CheckInterfaceSupport(&IDXGIDevice::IID)?;
        let mut raw = None;
        D3D12CreateDevice(&adapter, D3D_FEATURE_LEVEL_12_0, &mut raw)?;
        let device: ID3D12Device = raw.ok_or_else(|| Error::from(E_FAIL))?;
        let root = device.CreateRootSignature(0, &rootsig)?;
        let device1: ID3D12Device1 = device.cast()?;
        let mut ptr: *mut c_void = null_mut();
        (device1.vtable().CreatePipelineLibrary)(device1.as_raw(), null(), 0, &D3dLibrary::IID, &mut ptr).ok()?;
        assert!(!ptr.is_null());
        let library = D3dLibrary::from_raw(ptr);
        println!("native adapter={selector} luid={:08x}:{:08x} driver={driver:016x}",
                 desc.AdapterLuid.HighPart as u32, desc.AdapterLuid.LowPart);
        Ok(Device { library, root, device, shader })
    }
}

fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    match args.as_slice() {
        [action] if action == "mock" => verify_requests(Backend::Mock(Mutex::new(false))),
        [action, adapter, image, root] if action == "native" => {
            enforce_guard();
            let gpu = device(adapter, container(Path::new(image), 4096), container(Path::new(root), 4096))
                .expect("create the bounded D3D12 device and an empty library");
            verify_requests(Backend::D3d(gpu));
        }
        _ => panic!("usage: fixture.exe mock | native ADAPTER SHADER ROOTSIG"),
    }
}
