// SPDX-License-Identifier: GPL-2.0-only
use std::{env, error::Error, fs, time::Instant};
use xcl::gpu::{
    dxil::validate,
    recomp::{dxc::cache_stats, pso::{console_to_dxil_in, Stage}},
};

fn main() -> Result<(), Box<dyn Error>> {
    let paths: Vec<_> = env::args_os().skip(1).collect();
    let [input, output] = paths.as_slice() else {
        return Err("expected two paths: permitted synthetic guest container, output DXIL".into());
    };
    let guest = fs::read(input)?;
    let start = Instant::now();
    let result = console_to_dxil_in(&guest, Stage::Pixel, 0, false, 4)?;
    let api_ms = start.elapsed().as_secs_f64() * 1000.0;
    let stats = cache_stats();
    validate::validate(&result.dxil)?;
    fs::write(output, result.dxil)?;
    println!("runtime_api_ms={api_ms:.6} cache_hits={} cache_misses={} compilations={}", stats.hits, stats.misses, stats.compilations);
    Ok(())
}
