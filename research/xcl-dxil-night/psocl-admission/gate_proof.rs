// SPDX-License-Identifier: GPL-2.0-only
mod driver_gate;
mod legacy;
mod patch_gate;
mod wanted_legacy;

use driver_gate::{Gate, Lane, MIB, Request, Running};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering::SeqCst};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

const HUGE: usize = 1024 * 1024;
const GIANT: usize = 4 * HUGE;
const LARGE_GIANT: usize = 14 * HUGE;
const ACTIVE_TEST: Duration = Duration::from_millis(150);
const EXIT_TEST: Duration = Duration::from_secs(2);

fn after(mut predicate: impl FnMut() -> bool) -> bool {
    let deadline = Instant::now() + EXIT_TEST;
    while !predicate() && Instant::now() < deadline {
        thread::sleep(Duration::from_millis(2));
    }
    predicate()
}

fn cross_lane_legacy() -> bool {
    let available = || 3328 * MIB;
    let first = legacy::attempt(0, HUGE, available, || false).unwrap();
    let (entered, check) = mpsc::channel();
    let thread = thread::spawn(move || {
        let _second = legacy::attempt(1, GIANT, available, || false).unwrap();
        entered.send(()).unwrap();
    });
    let simultaneous = check.recv_timeout(EXIT_TEST).is_ok();
    drop(first);
    thread.join().unwrap();
    simultaneous
}

fn cross_lane_candidate(wanted_cap: bool) -> (bool, bool) {
    let gate = Gate::new();
    let first_request = Request::cold_background(Lane::Huge, 1, HUGE);
    let first_request = if wanted_cap { first_request.with_wanted_limit(2) } else { first_request };
    let second_request = Request::cold_background(Lane::Giant, 1, GIANT);
    let second_request = if wanted_cap { second_request.with_wanted_limit(1) } else { second_request };
    let first = gate.enter(first_request, || Some(3328 * MIB), || false).unwrap();
    let (entered, check) = mpsc::channel();
    let query = AtomicBool::new(false);
    thread::scope(|scope| {
        let g = &gate;
        let q = &query;
        scope.spawn(move || {
            let _second = g.enter(second_request,
                                  || { q.store(true, SeqCst); Some(3328 * MIB) }, || false).unwrap();
            entered.send(()).unwrap();
        });
        let ready = after(|| query.load(SeqCst));
        let premature = check.recv_timeout(ACTIVE_TEST).is_ok();
        let active = gate.snapshot();
        drop(first);
        let resumed = premature || check.recv_timeout(EXIT_TEST).is_ok();
        assert!(ready && resumed);
        assert_eq!(active, Running { any_lane_bytes: 1536 * MIB, slots: [1, 0] });
        (premature, resumed)
    })
}

fn legacy_oversized_holds_lane() -> bool {
    let free = AtomicU64::new(5 * 1024 * MIB);
    let started = AtomicBool::new(false);
    let (small_go, observe) = mpsc::channel();
    thread::scope(|scope| {
        scope.spawn(|| {
            let _large = legacy::attempt(1, LARGE_GIANT,
                || { started.store(true, SeqCst); free.load(SeqCst) }, || false).unwrap();
        });
        let checked = after(|| started.load(SeqCst));
        let free_signal = &free;
        scope.spawn(move || {
            let _small = legacy::attempt(1, GIANT, || free_signal.load(SeqCst), || false).unwrap();
            small_go.send(()).unwrap();
        });
        let blocked = observe.recv_timeout(ACTIVE_TEST).is_err();
        free.store(8 * 1024 * MIB, SeqCst);
        assert!(checked);
        blocked
    })
}

fn candidate_oversized_leaves_lane_free() -> bool {
    let gate = Gate::new();
    let free = AtomicU64::new(5 * 1024 * MIB);
    let checked = AtomicBool::new(false);
    let (small_go, observe) = mpsc::channel();
    thread::scope(|scope| {
        scope.spawn(|| {
            let _large = gate.enter(Request::cold_background(Lane::Giant, 1, LARGE_GIANT),
                || { checked.store(true, SeqCst); Some(free.load(SeqCst)) }, || false).unwrap();
        });
        let ready = after(|| checked.load(SeqCst));
        let g = &gate;
        let current = &free;
        scope.spawn(move || {
            let _small = g.enter(Request::cold_background(Lane::Giant, 1, GIANT),
                                 || Some(current.load(SeqCst)), || false).unwrap();
            small_go.send(()).unwrap();
        });
        let ran = observe.recv_timeout(EXIT_TEST).is_ok();
        free.store(8 * 1024 * MIB, SeqCst);
        assert!(ready);
        ran
    })
}

fn current_pr_cross_lane() {
    let available = || 3328 * MIB;
    let first = wanted_legacy::attempt(0, HUGE, available, || false);
    let (entered, check) = mpsc::channel();
    let thread = thread::spawn(move || {
        let _second = wanted_legacy::attempt(1, GIANT, available, || false);
        entered.send(()).unwrap();
    });
    let simultaneous = check.recv_timeout(EXIT_TEST).is_ok();
    drop(first);
    thread.join().unwrap();
    assert!(simultaneous);
    let (premature, resumed) = cross_lane_candidate(true);
    assert!(!premature && resumed);
    assert_eq!(wanted_legacy::held(0), 0);
    assert_eq!(wanted_legacy::held(1), 0);
    println!("#1996 wanted-cap branch: the same cross-lane over-admission remains; shared reservation closes it");
}

fn wanted_cap_control() {
    let gate = Gate::new();
    let huge = Request::cold_background(Lane::Huge, 1, HUGE).with_wanted_limit(2);
    let first = gate.enter(huge, || Some(0), || true).unwrap();
    let second = gate.enter(huge, || Some(0), || true).unwrap();
    let (entered, check) = mpsc::channel();
    thread::scope(|scope| {
        let g = &gate;
        scope.spawn(move || {
            let _third = g.enter(huge, || Some(0), || true).unwrap();
            entered.send(()).unwrap();
        });
        let capped = check.recv_timeout(ACTIVE_TEST).is_err();
        let snapshot = gate.snapshot();
        drop(second);
        let resumed = check.recv_timeout(EXIT_TEST).is_ok();
        assert!(capped && resumed);
        assert_eq!(snapshot, Running { any_lane_bytes: 3072 * MIB, slots: [2, 0] });
    });
    drop(first);
    assert_eq!(gate.snapshot(), Running::default());
    println!("#1996-style wanted bypass and its two-work cap remain intact");
}

fn checked_patch_accounting() {
    let available = || 3328 * MIB;
    let first = patch_gate::attempt(0, HUGE, available, || false);
    let probe = AtomicBool::new(false);
    let (entered, observe) = mpsc::channel();
    thread::scope(|scope| {
        let requested = &probe;
        scope.spawn(move || {
            let _second = patch_gate::attempt(1, GIANT, || {
                requested.store(true, SeqCst);
                available()
            }, || false);
            entered.send(()).unwrap();
        });
        let checked = after(|| probe.load(SeqCst));
        let held = patch_gate::reserved();
        let waited = observe.recv_timeout(ACTIVE_TEST).is_err();
        drop(first);
        let proceeded = !waited || observe.recv_timeout(EXIT_TEST).is_ok();
        assert!(checked && waited && proceeded);
        assert_eq!(held, 1536 * MIB);
    });
    assert_eq!(patch_gate::reserved(), 0);

    let a = patch_gate::attempt(0, HUGE, || 0, || true);
    let b = patch_gate::attempt(0, HUGE, || 0, || true);
    let (entered, observe) = mpsc::channel();
    let c = thread::spawn(move || {
        let _third = patch_gate::attempt(0, HUGE, || 0, || true);
        entered.send(()).unwrap();
    });
    let waited = observe.recv_timeout(ACTIVE_TEST).is_err();
    let held = patch_gate::reserved();
    drop(b);
    let proceeded = !waited || observe.recv_timeout(EXIT_TEST).is_ok();
    c.join().unwrap();
    drop(a);
    assert!(waited && proceeded);
    assert_eq!(held, 3072 * MIB);
    assert_eq!(patch_gate::reserved(), 0);
    println!("exact #1996 patch preserves wanted capacity and closes the cross-lane admission window");
}

fn controls() {
    let gate = Gate::new();
    let large = Request::cold_background(Lane::Giant, 1, GIANT);
    let small = Request::cold_background(Lane::Huge, 4, HUGE);
    let open = || Some(6 * 1024 * MIB);
    let a = gate.enter(large, open, || false).unwrap();
    let b = gate.enter(small, open, || false).unwrap();
    let c = gate.enter(small, open, || false).unwrap();
    assert_eq!(gate.snapshot(), Running { any_lane_bytes: 5120 * MIB, slots: [2, 1] });
    assert!(gate.enter(large, || Some(0), || true).is_none());
    assert_eq!(gate.snapshot(), Running { any_lane_bytes: 5120 * MIB, slots: [2, 1] });
    drop((a, b, c));
    assert_eq!(gate.snapshot(), Running::default());

    let attempt = std::panic::catch_unwind(|| {
        let _a = gate.enter(small, || None, || false).unwrap();
        panic!("synthetic compile failure");
    });
    assert!(attempt.is_err());
    assert_eq!(gate.snapshot(), Running::default());
    assert_eq!(legacy::held(0), 0);
    assert_eq!(legacy::held(1), 0);
}

fn main() {
    std::panic::set_hook(Box::new(|_| {}));
    let old = cross_lane_legacy();
    let (new, resumed) = cross_lane_candidate(false);
    assert!(old && !new && resumed);
    println!("3328 MiB cross-lane window: legacy admitted both (1536 + 2048 MiB); candidate waited for release");
    let blocked = legacy_oversized_holds_lane();
    let passed = candidate_oversized_leaves_lane_free();
    assert!(blocked && passed);
    println!("5120 MiB same-lane window: legacy held slot for 7168 MiB job; candidate admitted 2048 MiB job");
    current_pr_cross_lane();
    wanted_cap_control();
    checked_patch_accounting();
    controls();
    println!("ample budget overlap, wanted bypass, unknown monitor, and panic-release controls passed");
}
