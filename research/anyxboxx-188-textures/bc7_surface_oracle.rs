// SPDX-License-Identifier: GPL-3.0-or-later
use anyxboxx_texture::decode_surface;
use std::env;
use std::fs;
use std::io::{self, Write};

fn main() -> io::Result<()> {
    let inputs = fs::read(env::args_os().nth(1).expect("corpus path"))?;
    let mut remaining = inputs.as_slice();
    let mut output = io::stdout().lock();
    while !remaining.is_empty() {
        let (header, rest) = remaining.split_at(12);
        let fields: Vec<_> = header
            .chunks_exact(4)
            .map(|field| u32::from_le_bytes(field.try_into().expect("u32 field")) as usize)
            .collect();
        let (blocks, next) = rest.split_at(fields[2]);
        let pixels = decode_surface(blocks, fields[0], fields[1]).expect("valid synthetic BC7");
        output.write_all(&pixels)?;
        remaining = next;
    }
    Ok(())
}
