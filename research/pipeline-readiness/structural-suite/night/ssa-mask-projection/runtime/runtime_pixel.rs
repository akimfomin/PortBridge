// SPDX-License-Identifier: GPL-2.0-only
use std::{env, fs};
use xcl::gpu::{
    dxil::validate,
    recomp::pso::{console_to_dxil_in, Stage},
};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let arguments: Vec<_> = env::args_os().skip(1).collect();
    let [input, output] = arguments.as_slice() else {
        return Err("expected a synthetic pixel fixture and output DXIL path".into());
    };
    let program = fs::read(input)?;
    let result = console_to_dxil_in(&program, Stage::Pixel, 0, false, 4)?;
    validate::validate(&result.dxil)?;
    fs::write(output, result.dxil)?;
    Ok(())
}
