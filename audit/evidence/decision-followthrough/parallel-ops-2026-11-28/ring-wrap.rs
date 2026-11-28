use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Barrier;
use std::thread;

const RING_BYTES: usize = 4 << 20;
const STEP: usize = 256;

fn concurrent_wrap(initial: usize) -> [usize; 2] {
    let at = AtomicUsize::new(initial);
    let after_fetch = Barrier::new(2);
    thread::scope(|scope| {
        let reserve = || {
            let start = at.fetch_add(STEP, Ordering::Relaxed);
            // Test hook isolates a legal interleaving between two operations.
            after_fetch.wait();
            if start + STEP > RING_BYTES {
                at.store(STEP, Ordering::Relaxed);
                0
            } else {
                start
            }
        };
        let worker_a = scope.spawn(reserve);
        let worker_b = scope.spawn(reserve);
        let mut offsets = [worker_a.join().unwrap(), worker_b.join().unwrap()];
        offsets.sort_unstable();
        offsets
    })
}

fn main() {
    let normal = concurrent_wrap(0);
    let before_wrap = concurrent_wrap(RING_BYTES - STEP);
    let double_wrap = concurrent_wrap(RING_BYTES);
    assert_eq!(normal, [0, STEP]);
    assert_eq!(before_wrap, [0, RING_BYTES - STEP]);
    assert_eq!(double_wrap, [0, 0]);
    println!("away from wrap: {normal:?}; one wrapper: {before_wrap:?}; two wrappers: {double_wrap:?}");
}
