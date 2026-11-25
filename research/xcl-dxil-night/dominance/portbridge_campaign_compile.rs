// SPDX-License-Identifier: GPL-2.0-only
// The source generator is from BetterJdue's XCL #1763 at e3806688e4d9.
#[path = "portbridge_night/campaign_gen.rs"]
mod campaign;

use std::env;
use std::time::Instant;

use xcl::gpu::dxil::{kernel, validate};
use xcl::gpu::recomp::HEAP_WINDOWS;

struct Shape {
    name: &'static str,
    ops: usize,
    if_depth: u32,
    divergent_pct: u32,
    loops: u32,
    loop_depth: u32,
    vgprs: u32,
    lds_pct: u32,
    mem_pct: u32,
}

#[test]
fn campaign_compile_corpus() {
    let shapes = [
        Shape { name: "small", ops: 200, if_depth: 2, divergent_pct: 10, loops: 0, loop_depth: 1, vgprs: 16, lds_pct: 5, mem_pct: 10 },
        Shape { name: "divergent", ops: 850, if_depth: 4, divergent_pct: 35, loops: 3, loop_depth: 2, vgprs: 32, lds_pct: 3, mem_pct: 8 },
        Shape { name: "memory", ops: 1200, if_depth: 2, divergent_pct: 12, loops: 6, loop_depth: 1, vgprs: 48, lds_pct: 12, mem_pct: 33 },
        Shape { name: "mixed", ops: 2200, if_depth: 3, divergent_pct: 15, loops: 8, loop_depth: 3, vgprs: 64, lds_pct: 6, mem_pct: 20 },
    ];
    let mut output = Vec::new();
    for shape in shapes {
        for seed in [3, 41, 826] {
            for (mode, wave64, split, mem_windows) in [
                ("switch", false, false, 4),
                ("heap_split", true, true, 4 | HEAP_WINDOWS),
            ] {
                let knobs = campaign::Knobs {
                    seed,
                    ops: shape.ops,
                    if_depth: shape.if_depth,
                    divergent_pct: shape.divergent_pct,
                    loops: shape.loops,
                    loop_depth: shape.loop_depth,
                    vgprs: shape.vgprs,
                    lds_pct: shape.lds_pct,
                    mem_pct: shape.mem_pct,
                    wave64,
                    ..campaign::Knobs::default()
                };
                let input = campaign::program(&knobs);
                let opts = kernel::KernelOptions { wave64, split, mem_windows, sampler_base: 0 };
                let first = kernel::translate(&input, opts).unwrap_or_else(|e| panic!("{}/{seed}/{mode}: {e}", shape.name));
                if env::var_os("PB_CFG_VALIDATE").is_some() {
                    validate::validate(&first).unwrap_or_else(|e| panic!("{}/{seed}/{mode}: {e}", shape.name));
                }
                let mut times = [0.0; 3];
                for time in &mut times {
                    let start = Instant::now();
                    let dxil = kernel::translate(&input, opts).unwrap();
                    *time = start.elapsed().as_secs_f64() * 1e3;
                    assert_eq!(dxil, first);
                }
                times.sort_by(f64::total_cmp);
                println!("{}/{seed}/{mode}: {} source bytes, {} DXIL bytes, median_ms={:.6}",
                         shape.name, input.len(), first.len(), times[1]);
                output.extend((first.len() as u32).to_le_bytes());
                output.extend(first);
            }
        }
    }
    std::fs::write(env::var_os("PB_CFG_OUTPUT").expect("PB_CFG_OUTPUT"), output).unwrap();
}
