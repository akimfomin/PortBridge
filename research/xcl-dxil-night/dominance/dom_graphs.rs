// SPDX-License-Identifier: GPL-2.0-only
#[cfg_attr(not(feature = "compact_dominators"), path = "../portbridge-night-xcl/crates/xcl/src/gpu/dxil/dom.rs")]
#[cfg_attr(feature = "compact_dominators", path = "dom_compact.rs")]
mod candidate;
#[cfg(feature = "track_allocations")]
mod dom_alloc;
#[cfg(feature = "track_allocations")]
#[global_allocator]
static ALLOCATOR: dom_alloc::CountingAllocator = dom_alloc::CountingAllocator;

use std::hint::black_box;
#[cfg(not(feature = "track_allocations"))]
use std::time::Instant;

const NONE: usize = usize::MAX;
type Graph = Vec<Vec<usize>>;

// Iterative RPO followed by the same CHK intersection order as the original
// XCL Module::idoms. Graph construction and equality checks are outside timing.
fn baseline(g: &Graph) -> Vec<Option<usize>> {
    let mut pending = vec![(0, false)];
    let mut seen = vec![false; g.len()];
    let mut order = Vec::new();
    while let Some((b, finished)) = pending.pop() {
        if finished {
            order.push(b);
        } else if !std::mem::replace(&mut seen[b], true) {
            pending.push((b, true));
            pending.extend(g[b].iter().rev().map(|&s| (s, false)));
        }
    }
    order.reverse();
    let mut ranks = vec![NONE; g.len()];
    let mut incoming = vec![Vec::new(); g.len()];
    for (rank, &b) in order.iter().enumerate() {
        ranks[b] = rank;
        for &s in &g[b] {
            incoming[s].push(b);
        }
    }
    let mut idom: Vec<Option<usize>> = vec![None; g.len()];
    idom[0] = Some(0);
    let mut changed = true;
    while changed {
        changed = false;
        for &b in order.iter().skip(1) {
            let mut new: Option<usize> = None;
            for &p in &incoming[b] {
                if idom[p].is_none() {
                    continue;
                }
                new = Some(match new {
                    None => p,
                    Some(mut x) => {
                        let mut y = p;
                        while x != y {
                            while ranks[x] > ranks[y] {
                                x = idom[x].unwrap();
                            }
                            while ranks[y] > ranks[x] {
                                y = idom[y].unwrap();
                            }
                        }
                        x
                    }
                });
            }
            if new.is_some() && idom[b] != new {
                idom[b] = new;
                changed = true;
            }
        }
    }
    idom
}

fn actual(g: &Graph) -> Vec<Option<usize>> {
    #[cfg(feature = "compact_dominators")]
    return candidate::immediate_dominators(g.len(), 0, g.len(), |i| g[i].iter().copied());
    #[cfg(not(feature = "compact_dominators"))]
    candidate::immediate_dominators(g.len(), 0, |i| g[i].iter().copied())
}

fn reachable(g: &Graph, excluded: usize) -> u64 {
    let mut seen = 0u64;
    let mut pending = vec![0];
    while let Some(node) = pending.pop() {
        let bit = 1 << node;
        if excluded == node || seen & bit != 0 {
            continue;
        }
        seen |= bit;
        pending.extend_from_slice(&g[node]);
    }
    seen
}

fn by_removing_vertices(g: &Graph) -> Vec<Option<usize>> {
    assert!(g.len() <= 64);
    let bits = reachable(g, NONE);
    let reachable_without: Vec<_> = (0..g.len()).map(|n| reachable(g, n)).collect();
    let dominates = |a: usize, b: usize| reachable_without[a] & (1 << b) == 0;
    let depth = |b| (0..g.len()).filter(|&a| dominates(a, b)).count();
    (0..g.len()).map(|b| {
        if bits & (1 << b) == 0 {
            None
        } else if b == 0 {
            Some(0)
        } else {
            (0..g.len()).filter(|&a| a != b && dominates(a, b)).max_by_key(|&a| depth(a))
        }
    }).collect()
}

fn compare(g: &Graph) {
    let expect = by_removing_vertices(g);
    assert_eq!(baseline(g), expect, "{g:?}");
    let candidate = actual(g);
    assert_eq!(candidate, expect, "{g:?}");
    let intervals = candidate::subtree_intervals(&candidate, 0);
    for (a, interval) in intervals.iter().enumerate() {
        let remaining = reachable(g, a);
        for (b, reach) in candidate.iter().enumerate() {
            if reach.is_some() {
                assert_eq!(interval.contains(&intervals[b].start), remaining & (1 << b) == 0);
            }
        }
    }
}

fn verify() {
    for mask in 0..(1 << 16) {
        let g = (0..4).map(|i| (0..4).filter(|&j| mask & (1 << (4 * i + j)) != 0).collect()).collect();
        compare(&g);
    }
    let mut rng = 0x768e_cdb5_b9ca_e965u64;
    let mut next = || {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        rng as usize
    };
    for _ in 0..10_000 {
        let size = 2 + next() % 40;
        let g = (0..size).map(|_| (0..next() % 5).map(|_| next() % size).collect()).collect();
        compare(&g);
    }
    let mut cycle: Graph = (1..=60_000).map(|i| vec![i]).collect();
    cycle.push(vec![1]);
    let d = actual(&cycle);
    assert!((1..d.len()).all(|i| d[i] == Some(i - 1)));
    println!("passed 65,536 exhaustive, 10,000 seeded, 1 deep cyclic graph");
}

fn graph(shape: &str, n: usize) -> Graph {
    match shape {
        "comb" => {
            let mut g = vec![Vec::new(); 3 * n + 1];
            g[0] = vec![1, n + 1];
            for i in 0..n {
                let sink = 2 * n + i + 1;
                for spine in [1, n + 1] {
                    if i + 1 < n {
                        g[spine + i].push(spine + i + 1);
                    }
                    g[spine + i].push(sink);
                }
            }
            g
        }
        "diamonds" => {
            let mut g = vec![Vec::new(); 3 * n + 1];
            for i in 0..n {
                let start = 3 * i;
                g[start] = vec![start + 1, start + 2];
                g[start + 1].push(start + 3);
                g[start + 2].push(start + 3);
            }
            g
        }
        "loop-chain" => {
            let mut g = vec![Vec::new(); 2 * n + 1];
            for i in 0..n {
                let start = 2 * i;
                g[start] = vec![start + 1, start + 2];
                g[start + 1].push(start);
            }
            g
        }
        _ => panic!("unknown shape"),
    }
}

fn main() {
    let args: Vec<_> = std::env::args().collect();
    if args.len() == 1 {
        return verify();
    }
    let g = graph(&args[1], args[2].parse().unwrap());
    #[cfg(feature = "track_allocations")]
    {
        let base = dom_alloc::measure(|| drop(black_box(baseline(black_box(&g)))));
        let tested = dom_alloc::measure(|| drop(black_box(actual(black_box(&g)))));
        println!("{} {} nodes: baseline {:?} candidate {:?} (peak bytes, allocation calls)",
                 args[1], g.len(), base, tested);
    }
    #[cfg(not(feature = "track_allocations"))]
    run_timing(&args[1], &g);
}

#[cfg(not(feature = "track_allocations"))]
fn run_timing(shape: &str, g: &Graph) {
    let mut times: [Vec<f64>; 2] = [Vec::new(), Vec::new()];
    for pair in 0..7 {
        let mut before = None;
        for arm in [pair % 2, 1 - pair % 2] {
            let start = Instant::now();
            let tree = if arm == 0 { baseline(black_box(g)) } else { actual(black_box(g)) };
            times[arm].push(start.elapsed().as_secs_f64() * 1e3);
            if let Some(check) = before.take() {
                assert_eq!(tree, check);
            } else {
                before = Some(tree);
            }
        }
    }
    println!("{} {} nodes baseline_ms={:?} candidate_ms={:?}", shape, g.len(), times[0], times[1]);
}
