// SPDX-License-Identifier: GPL-2.0-only
// Research harness for the pinned XCL allocator. The fixture bodies are generated
// from Kalmarv's upstream tests by run.py; the CPU probe adds no DXIL operations.
use std::cell::{Cell, RefCell};
use std::collections::BTreeMap;
use std::path::Path;

use super::{inst, Module, Plan, Shader, Value};
use crate::gpu::dxil::{container::Stage, module::{BinOp, Block, CastOp, Pred}, shader::RawUav};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
enum Access {
    Read,
    Write,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
struct Event {
    piece: usize,
    value: Value,
    access: Access,
    words: u32,
}

thread_local! {
    static PIECE: Cell<usize> = const { Cell::new(0) };
    static EVENTS: RefCell<Vec<Event>> = const { RefCell::new(Vec::new()) };
}

pub(super) fn begin(piece: usize) {
    PIECE.set(piece);
}

fn record(value: Value, words: u32, access: Access) {
    let piece = PIECE.get();
    EVENTS.with_borrow_mut(|events| events.push(Event { piece, value, access, words }));
}

pub(super) fn read(value: Value, words: u32) {
    record(value, words, Access::Read);
}

pub(super) fn write(value: Value, words: u32) {
    record(value, words, Access::Write);
}

// The native Wave32 fixture builds only scalar arithmetic and one raw UAV.
// This shim replaces the test's D3D runtime and unrelated guest-lane setup.
struct Lw {
    s: Shader,
    mems: [RawUav; 1],
}

impl Lw {
    fn new() -> Self {
        let mut s = Shader::new(Stage::Compute, (6, 6));
        let mem = s.raw_uav(0, 0);
        Self { s, mems: [mem] }
    }

    fn c(&mut self, value: u32) -> Value {
        self.s.m.i32c(value)
    }

    fn mul(&mut self, left: Value, right: Value) -> Value {
        self.s.m.bin(BinOp::Mul, left, right)
    }

    fn add(&mut self, left: Value, right: Value) -> Value {
        self.s.m.bin(BinOp::Add, left, right)
    }

    fn addc(&mut self, value: Value, add: u32) -> Value {
        let add = self.c(add);
        self.add(value, add)
    }

    fn andc(&mut self, value: Value, mask: u32) -> Value {
        let mask = self.c(mask);
        self.s.m.bin(BinOp::And, value, mask)
    }

    fn cmp(&mut self, predicate: Pred, left: Value, right: Value) -> Value {
        self.s.m.cmp(predicate, left, right)
    }

    fn cur(&self) -> Block {
        self.s.m.current_block()
    }

    fn xor(&mut self, left: Value, right: Value) -> Value {
        self.s.m.bin(BinOp::Xor, left, right)
    }

    fn shlc(&mut self, value: Value, shift: u32) -> Value {
        let shift = self.c(shift);
        self.s.m.bin(BinOp::Shl, value, shift)
    }
}

#[derive(Clone, Copy, Debug)]
struct Lifetime {
    value: Value,
    first: usize,
    last: usize,
    words: u32,
}

fn ranges(module: &Module, plan: &Plan) -> Vec<Lifetime> {
    let mut stage_of = vec![None; module.blocks.len()];
    for (stage, blocks) in plan.blocks.iter().enumerate() {
        for block in blocks {
            stage_of[block.0 as usize] = Some(stage);
        }
    }

    let mut values = BTreeMap::<Value, Lifetime>::new();
    for edge in &plan.edges {
        let from = stage_of[edge.from.0 as usize].unwrap();
        let to = stage_of[edge.to.0 as usize].unwrap();
        assert!(from < to);
        for &value in &edge.live {
            let words = module.transport_words(value).unwrap();
            if words == 0 {
                continue;
            }
            let defining_block = module.def_block[inst(value).unwrap()];
            let first = stage_of[defining_block.0 as usize].unwrap();
            assert!(first <= from);
            values.entry(value).and_modify(|life| life.last = life.last.max(to))
                .or_insert(Lifetime { value, first, last: to, words });
        }
    }
    values.into_values().collect()
}

type Layout = (u32, BTreeMap<Value, u32>);

fn fixed(lives: &[Lifetime]) -> Layout {
    let mut stride = 1u32; // lane continuation tag
    let mut slots = BTreeMap::new();
    for life in lives {
        slots.insert(life.value, stride);
        stride = stride.checked_add(life.words).unwrap();
    }
    (stride, slots)
}

fn strict(lives: &[Lifetime]) -> Layout {
    let mut ordered = lives.to_vec();
    ordered.sort_by_key(|l| (l.first, l.value));
    let mut occupied = BTreeMap::<u32, (u32, usize)>::new();
    let mut stride = 1;
    let mut slots = BTreeMap::new();

    for life in ordered {
        occupied.retain(|_, (_, last)| *last >= life.first);
        let mut slot = 1u32;
        for (&start, &(end, _)) in &occupied {
            if slot.checked_add(life.words).unwrap() <= start {
                break;
            }
            slot = end;
        }
        let end = slot.checked_add(life.words).unwrap();
        assert!(occupied.insert(slot, (end, life.last)).is_none());
        slots.insert(life.value, slot);
        stride = stride.max(end);
    }
    (stride, slots)
}

fn peak(lives: &[Lifetime], pieces: usize) -> u32 {
    (0..pieces).map(|piece| {
        1 + lives.iter().filter(|l| l.first <= piece && piece <= l.last)
            .map(|l| l.words).sum::<u32>()
    }).max().unwrap()
}

fn check_layout(lives: &[Lifetime], layout: &Layout) {
    for (index, a) in lives.iter().enumerate() {
        let a_start = layout.1[&a.value];
        assert!(a_start > 0 && a_start + a.words <= layout.0);
        for b in &lives[..index] {
            let b_start = layout.1[&b.value];
            let time_overlap = a.first <= b.last && b.first <= a.last;
            let space_overlap = a_start < b_start + b.words && b_start < a_start + a.words;
            assert!(!(time_overlap && space_overlap));
        }
    }
}

fn emitted(name: &str, arm: &str, s: &Shader, plan: &Plan, layout: &Layout, out: &Path) -> Vec<Event> {
    assert!(EVENTS.with_borrow(|events| events.is_empty()));
    for stage in 0..plan.blocks.len() {
        let blob = s.make_piece(plan, stage, layout.0, &layout.1, [32, 1, 1], &[]).unwrap();
        std::fs::write(out.join(format!("{name}-{arm}-{stage}.dxil")), blob).unwrap();
    }
    let mut events = EVENTS.take();
    events.sort();
    events
}

fn replay(events: &[Event], pieces: usize, layout: &Layout, writes_first: bool) -> (usize, usize) {
    let mut checked = 0;
    let mut mismatches = 0;
    let order = if writes_first { [Access::Write, Access::Read] } else { [Access::Read, Access::Write] };
    for lane in 0..32u32 {
        let mut scratch = vec![0xfeed_beef; layout.0 as usize];
        for piece in 0..pieces {
            for access in order {
                for event in events.iter().filter(|e| e.piece == piece && e.access == access) {
                    let value = inst(event.value).unwrap() as u32;
                    let slot = layout.1[&event.value];
                    for word in 0..event.words {
                        let tag = value * 1024 + lane * 2 + word;
                        let memory = &mut scratch[(slot + word) as usize];
                        if access == Access::Write {
                            *memory = tag;
                        } else {
                            checked += 1;
                            mismatches += usize::from(*memory != tag);
                        }
                    }
                }
            }
        }
        assert_eq!(scratch[0], 0xfeed_beef);
    }
    (checked, mismatches)
}

fn compare(name: &str, s: &Shader, plan: &Plan, limit: usize, saved: Option<(Value, Value)>, out: &Path) {
    let lives = ranges(&s.m, plan);
    let fixed = fixed(&lives);
    let strict = strict(&lives);
    let peak = peak(&lives, plan.blocks.len());
    assert!(peak <= strict.0 && strict.0 <= fixed.0);
    check_layout(&lives, &fixed);
    check_layout(&lives, &strict);

    let upstream = s.split_compute([32, 1, 1], None, limit).unwrap();
    assert_eq!(upstream.dwords_per_group, fixed.0 * 32);
    assert_eq!(upstream.pieces.len(), plan.blocks.len());
    let mut upstream_events = EVENTS.take();
    upstream_events.sort();

    let events = emitted(name, "fixed", s, plan, &fixed, out);
    assert_eq!(upstream_events, events);
    for (stage, original) in upstream.pieces.into_iter().enumerate() {
        assert_eq!(original, std::fs::read(out.join(format!("{name}-fixed-{stage}.dxil"))).unwrap());
    }
    assert_eq!(events, emitted(name, "strict", s, plan, &strict, out));
    for event in &events {
        let life = lives.iter().find(|l| l.value == event.value).unwrap();
        assert_eq!(event.words, life.words);
        assert!(life.first <= event.piece && event.piece <= life.last);
        if event.access == Access::Write {
            assert_eq!(event.piece, life.first);
        }
    }

    let baseline = replay(&events, plan.blocks.len(), &fixed, false);
    assert_eq!(baseline.1, 0);
    assert_eq!(baseline, replay(&events, plan.blocks.len(), &strict, false));
    assert_eq!(baseline, replay(&events, plan.blocks.len(), &strict, true));

    let mut negative = 0;
    if let Some((older, newer)) = saved {
        assert_ne!(strict.1[&older], strict.1[&newer]);
        let mut alias = fixed.clone();
        alias.1.insert(newer, alias.1[&older]);
        negative = replay(&events, plan.blocks.len(), &alias, false).1;
        assert!(negative > 0);
    }

    let reads = events.iter().filter(|e| e.access == Access::Read).map(|e| e.words).sum::<u32>();
    let writes = events.iter().filter(|e| e.access == Access::Write).map(|e| e.words).sum::<u32>();
    println!("{name},{},{},{},{},{reads},{writes},{},{negative}", plan.blocks.len(), fixed.0, strict.0, peak, baseline.0);
    for life in lives {
        let id = inst(life.value).unwrap();
        println!("life,{name},{id},{},{},{},{},{}", life.first, life.last, life.words, fixed.1[&life.value], strict.1[&life.value]);
    }
}

// The exact published bodies are inserted here, up to the final GPU calls.
// UPSTREAM_FIXTURE

fn disjoint(out: &Path) {
    let mut lw = Lw::new();
    let tid = lw.s.flattened_thread_id_in_group();
    let offset = lw.shlc(tid, 2);
    let mem = lw.mems[0];

    let read_first = lw.s.raw_load(mem, offset, 1)[0];
    let first = mix(&mut lw, read_first, 10);
    let second = lw.s.m.new_block();
    let third = lw.s.m.new_block();
    let fourth = lw.s.m.new_block();
    lw.s.m.br(second);
    lw.s.m.set_block(second);
    let result = mix(&mut lw, first, 30);
    lw.s.raw_store(mem, offset, &[result]);
    lw.s.m.br(third);

    lw.s.m.set_block(third);
    let read_again = lw.s.raw_load(mem, offset, 1)[0];
    let later = mix(&mut lw, read_again, 50);
    lw.s.m.br(fourth);
    lw.s.m.set_block(fourth);
    let result = mix(&mut lw, later, 70);
    lw.s.raw_store(mem, offset, &[result]);
    lw.s.m.ret();
    lw.s.m.optimize();

    let limit = lw.s.m.blocks.iter().map(Vec::len).max().unwrap();
    let plan = lw.s.m.dispatch_plan(limit).unwrap();
    assert_eq!(plan.blocks.len(), 4);
    let lives = ranges(&lw.s.m, &plan);
    assert!(strict(&lives).0 < fixed(&lives).0);
    assert_eq!(strict(&lives).1[&first], strict(&lives).1[&later]);
    compare("disjoint-control", &lw.s, &plan, limit, None, out);
}

pub(super) fn run(out: &Path) {
    persistent(false, out);
    persistent(true, out);
    wave32_loops(out);
    disjoint(out);
}
