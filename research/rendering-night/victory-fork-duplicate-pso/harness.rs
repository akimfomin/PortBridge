// SPDX-License-Identifier: GPL-3.0-or-later
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::{Cell, RefCell};
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::mpsc::{self, Sender};
use std::sync::{LazyLock, Mutex, MutexGuard, OnceLock};
#[cfg(pb_candidate)]
use std::sync::{Arc, Condvar};
use std::time::Duration;

mod windows {
    pub mod core {
        pub type Result<T> = std::result::Result<T, &'static str>;
    }
}

mod host {
    pub fn now_ms() -> u64 {
        0
    }
    pub fn trail(_: impl FnOnce() -> String) {}
}

#[allow(clippy::upper_case_acronyms)]
struct HSTRING(String);
impl HSTRING {
    fn from(name: &str) -> Self {
        Self(name.into())
    }
    fn as_ptr(&self) -> &str {
        &self.0
    }
}
#[allow(clippy::upper_case_acronyms)]
struct PCWSTR<'a>(&'a str);

type ID3D12PipelineState = u32;
type ID3D12PipelineLibrary1 = NativeLibrary;

struct NativeLibrary(Mutex<HashMap<String, ID3D12PipelineState>>);

impl NativeLibrary {
    fn load(&self, name: PCWSTR<'_>, description: u32) -> windows::core::Result<ID3D12PipelineState> {
        self.0.lock().unwrap().get(name.0).copied().filter(|pso| *pso == description).ok_or("miss")
    }

    #[allow(non_snake_case)]
    unsafe fn StorePipeline(&self, name: PCWSTR<'_>, pso: &u32) -> windows::core::Result<()> {
        use std::collections::hash_map::Entry;
        if name.0.starts_with("refused-store-") {
            return Err("store unavailable");
        }
        match self.0.lock().unwrap().entry(name.0.into()) {
            Entry::Vacant(entry) => {
                entry.insert(*pso);
                Ok(())
            }
            Entry::Occupied(_) => Err("already stored"),
        }
    }
}

struct Library {
    library: NativeLibrary,
    added: AtomicU64,
    saving: std::sync::RwLock<()>,
}

thread_local! {
    static HAS_LIBRARY: Cell<bool> = const { Cell::new(true) };
    static LABEL: RefCell<String> = const { RefCell::new(String::new()) };
    static WAIT_SIGNAL: RefCell<Option<Sender<Progress>>> = const { RefCell::new(None) };
    static ALLOCATIONS: Cell<Option<(usize, usize)>> = const { Cell::new(None) };
}

struct CountingAllocator;

// SAFETY: allocation and deallocation use the system allocator with their
// original arguments. The thread-local accounting uses no dynamic storage.
unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            let _ = ALLOCATIONS.try_with(|state| {
                if let Some((count, bytes)) = state.get() {
                    state.set(Some((count + 1, bytes + layout.size())));
                }
            });
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }
}

#[global_allocator]
static ALLOCATOR: CountingAllocator = CountingAllocator;

fn library() -> Option<&'static Library> {
    static LIBRARY: LazyLock<Library> = LazyLock::new(|| Library {
        library: NativeLibrary(Mutex::new(HashMap::new())),
        added: AtomicU64::new(0),
        saving: std::sync::RwLock::new(()),
    });
    HAS_LIBRARY.get().then(|| &*LIBRARY)
}

static MADE: AtomicU64 = AtomicU64::new(0);
static LOADED: AtomicU64 = AtomicU64::new(0);
static LOADED_AT: AtomicU64 = AtomicU64::new(0);
static TRIMMED: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

struct TraceCall;
fn call(_: &str, _: &str) -> TraceCall {
    TraceCall
}

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

include!("extracted.rs");

fn use_pipeline(name: &str, description: u32, create: impl FnOnce() -> windows::core::Result<u32>) -> windows::core::Result<u32> {
    pipeline(name, |library, wide| library.load(wide, description), create)
}

fn no_active_names() {
    #[cfg(pb_candidate)]
    assert!(ACTIVE_NAMES.lock().unwrap().is_empty());
}

#[test]
fn separate_cold_callers_compile_once_when_the_store_succeeds() {
    // The final bytes differ by 64, so both names share a shard in the original design.
    const SHARED: &str = "cold-a";
    const INDEPENDENT: &str = "cold-!";
    const CONTROL_TIMEOUT: Duration = Duration::from_secs(5);
    let creates = AtomicUsize::new(0);
    let loaded_before = LOADED.load(Ordering::Relaxed);
    let stored_before = library().unwrap().added.load(Ordering::Relaxed);

    std::thread::scope(|threads| {
        let (first_in_create, first_progress) = mpsc::channel();
        let (let_first_store, resume_first) = mpsc::channel();
        let first_count = &creates;
        let first = threads.spawn(move || {
            use_pipeline(SHARED, 7, || {
                first_count.fetch_add(1, Ordering::Relaxed);
                first_in_create.send(()).unwrap();
                resume_first.recv_timeout(CONTROL_TIMEOUT).unwrap();
                Ok(7)
            })
        });
        first_progress.recv_timeout(CONTROL_TIMEOUT).unwrap();

        let mut same_name = Vec::new();
        let mut release_later_creates = Vec::new();
        for _ in 0..3 {
            let (notify, progress) = mpsc::channel();
            let (release, later_create) = mpsc::channel();
            release_later_creates.push(release);
            let next_count = &creates;
            same_name.push(threads.spawn(move || {
                WAIT_SIGNAL.with_borrow_mut(|signal| *signal = Some(notify.clone()));
                use_pipeline(SHARED, 7, || {
                    next_count.fetch_add(1, Ordering::Relaxed);
                    notify.send(Progress::Create).unwrap();
                    // Keep all baseline creates apart from their stores until each misses.
                    later_create.recv_timeout(CONTROL_TIMEOUT).unwrap();
                    Ok(7)
                })
            }));
            #[cfg(pb_candidate)]
            let expected = Progress::Wait;
            #[cfg(not(pb_candidate))]
            let expected = Progress::Create;
            assert_eq!(progress.recv_timeout(CONTROL_TIMEOUT).unwrap(), expected);
        }

        let (independent_done, control) = mpsc::channel();
        let other = threads.spawn(move || {
            independent_done.send(use_pipeline(INDEPENDENT, 23, || Ok(23))).unwrap();
        });
        assert_eq!(control.recv_timeout(CONTROL_TIMEOUT).unwrap(), Ok(23));
        let_first_store.send(()).unwrap();
        for release in release_later_creates {
            let _ = release.send(());
        }
        assert_eq!(first.join().unwrap(), Ok(7));
        for pipeline in same_name {
            assert_eq!(pipeline.join().unwrap(), Ok(7));
        }
        other.join().unwrap();
    });

    let create_count = creates.load(Ordering::Relaxed);
    let load_count = LOADED.load(Ordering::Relaxed) - loaded_before;
    let store_count = library().unwrap().added.load(Ordering::Relaxed) - stored_before;
    assert_eq!((create_count, load_count), if cfg!(pb_candidate) { (1, 3) } else { (4, 0) });
    assert_eq!(store_count, 2);
    println!("same_name_creates={create_count} same_name_hits={load_count} stores_including_control={store_count} independent_before_release=true");
    no_active_names();
}

#[test]
fn warm_lookup_and_same_name_descriptor_mismatch_follow_original_policy() {
    const KEY: &str = "warm-descriptor";
    assert_eq!(use_pipeline(KEY, 31, || Ok(31)), Ok(31));
    assert_eq!(use_pipeline(KEY, 31, || panic!("warm cache recreated the PSO")), Ok(31));
    assert_eq!(use_pipeline(KEY, 32, || Ok(32)), Ok(32));
    assert_eq!(use_pipeline(KEY, 31, || panic!("other descriptor replaced the old PSO")), Ok(31));
    no_active_names();
}

#[test]
fn warm_cache_counts_admission_allocations_without_timing() {
    const KEY: &str = "000102030405060708090a0b0c0d0e0f";
    const LOOKUPS: usize = 12;
    assert_eq!(use_pipeline(KEY, 63, || Ok(63)), Ok(63));
    assert_eq!(use_pipeline(KEY, 63, || panic!("unexpected create")), Ok(63));
    ALLOCATIONS.set(Some((0, 0)));
    for _ in 0..LOOKUPS {
        let hit = use_pipeline(std::hint::black_box(KEY), 63, || panic!("unexpected create"));
        assert_eq!(hit, Ok(63));
    }
    let (calls, bytes) = ALLOCATIONS.replace(None).unwrap();
    let expected = LOOKUPS * if cfg!(pb_candidate) { 2 } else { 1 };
    assert_eq!((calls, bytes), (expected, expected * KEY.len()));
    println!("warm_hits={LOOKUPS} allocator_calls={calls} requested_bytes={bytes}");
    no_active_names();
}

#[test]
fn normal_create_error_allows_same_name_retry() {
    const KEY: &str = "create-retry";
    const CONTROL_TIMEOUT: Duration = Duration::from_secs(5);
    std::thread::scope(|threads| {
        let (create_started, started) = mpsc::channel();
        let (fail_create, resume) = mpsc::channel();
        let first = threads.spawn(move || use_pipeline(KEY, 9, || {
            create_started.send(()).unwrap();
            resume.recv_timeout(CONTROL_TIMEOUT).unwrap();
            Err("create unavailable")
        }));
        started.recv_timeout(CONTROL_TIMEOUT).unwrap();

        let (notify, progress) = mpsc::channel();
        let retry = threads.spawn(move || {
            WAIT_SIGNAL.with_borrow_mut(|signal| *signal = Some(notify.clone()));
            use_pipeline(KEY, 9, || {
                #[cfg(not(pb_candidate))]
                notify.send(Progress::Create).unwrap();
                Ok(9)
            })
        });
        #[cfg(pb_candidate)]
        let expected = Progress::Wait;
        #[cfg(not(pb_candidate))]
        let expected = Progress::Create;
        assert_eq!(progress.recv_timeout(CONTROL_TIMEOUT).unwrap(), expected);
        fail_create.send(()).unwrap();
        assert_eq!(first.join().unwrap(), Err("create unavailable"));
        assert_eq!(retry.join().unwrap(), Ok(9));
    });
    assert_eq!(use_pipeline(KEY, 9, || panic!("retry did not publish")), Ok(9));
    no_active_names();
}

#[test]
fn store_failure_returns_the_created_pso_and_retries_next_time() {
    const KEY: &str = "refused-store-a";
    let mut creations = 0;
    for _ in 0..2 {
        assert_eq!(use_pipeline(KEY, 19, || { creations += 1; Ok(19) }), Ok(19));
    }
    assert_eq!(creations, 2);
    no_active_names();
}

#[test]
fn absent_library_retains_per_call_creation() {
    HAS_LIBRARY.set(false);
    let mut creations = 0;
    for _ in 0..2 {
        assert_eq!(use_pipeline("no-library", 3, || { creations += 1; Ok(3) }), Ok(3));
    }
    assert_eq!(creations, 2);
    no_active_names();
}
