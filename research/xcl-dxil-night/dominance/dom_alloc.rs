// SPDX-License-Identifier: GPL-2.0-only
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering::Relaxed};

pub struct CountingAllocator;
static ENABLED: AtomicBool = AtomicBool::new(false);
static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);
static CALLS: AtomicUsize = AtomicUsize::new(0);

impl CountingAllocator {
    fn add(size: usize) {
        let live = LIVE.fetch_add(size, Relaxed) + size;
        PEAK.fetch_max(live, Relaxed);
    }
}

unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() && ENABLED.load(Relaxed) {
            CALLS.fetch_add(1, Relaxed);
            Self::add(layout.size());
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        if ENABLED.load(Relaxed) {
            LIVE.fetch_sub(layout.size(), Relaxed);
        }
        unsafe { System.dealloc(ptr, layout) };
    }

    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let next = unsafe { System.realloc(ptr, layout, size) };
        if !next.is_null() && ENABLED.load(Relaxed) {
            CALLS.fetch_add(1, Relaxed);
            if size >= layout.size() {
                Self::add(size - layout.size());
            } else {
                LIVE.fetch_sub(layout.size() - size, Relaxed);
            }
        }
        next
    }
}

pub fn measure(f: impl FnOnce()) -> (usize, usize) {
    for counter in [&LIVE, &PEAK, &CALLS] {
        counter.store(0, Relaxed);
    }
    ENABLED.store(true, Relaxed);
    f();
    ENABLED.store(false, Relaxed);
    assert_eq!(LIVE.load(Relaxed), 0, "all measured allocations must be freed");
    (PEAK.load(Relaxed), CALLS.load(Relaxed))
}
