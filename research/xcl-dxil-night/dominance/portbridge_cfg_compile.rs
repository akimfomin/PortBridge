// SPDX-License-Identifier: GPL-2.0-only
use std::env;
use std::time::Instant;

use xcl::gpu::dxil::{kernel, validate};
use xcl::gpu::rdna2::encode;

#[derive(Clone, Copy)]
enum Node {
    Branch(usize, usize),
    Jump(usize),
    End,
}

fn print_instruction(output: &mut Vec<u8>, name: &str, encoding: &str, fields: &[(&str, u64)]) {
    let words = encode(name, encoding, fields, None).unwrap();
    assert_eq!(words.len(), 4);
    output.extend(words);
}

fn shader(nodes: &[Node]) -> Vec<u8> {
    let mut next = 0usize;
    let pc: Vec<_> = nodes.iter().map(|node| {
        let current = next;
        next += if matches!(node, Node::Branch(_, _)) { 3 } else { 1 };
        current
    }).collect();
    let mut output = Vec::with_capacity(next * 4);
    fn branch_code(source: usize, target: usize) -> u64 {
        let offset = target as isize - source as isize - 1;
        i16::try_from(offset).expect("branch displacement") as u16 as u64
    }
    for (n, node) in nodes.iter().enumerate() {
        match *node {
            Node::Branch(taken, other) => {
                let register = 4 + n as u64 % 8;
                let compare_with = 128 + n as u64 % 32;
                print_instruction(&mut output, "S_CMP_LG_U32", "ENC_SOPC",
                    &[("SSRC0", register), ("SSRC1", compare_with)]);
                print_instruction(&mut output, "S_CBRANCH_SCC1", "ENC_SOPP",
                    &[("SIMM16", branch_code(pc[n] + 1, pc[taken]))]);
                print_instruction(&mut output, "S_BRANCH", "ENC_SOPP",
                    &[("SIMM16", branch_code(pc[n] + 2, pc[other]))]);
            }
            Node::Jump(target) => print_instruction(&mut output, "S_BRANCH", "ENC_SOPP",
                &[("SIMM16", branch_code(pc[n], pc[target]))]),
            Node::End => print_instruction(&mut output, "S_ENDPGM", "ENC_SOPP", &[]),
        }
    }
    output
}

fn nodes(shape: &str, count: usize) -> Vec<Node> {
    match shape {
        "joins" => {
            let mut graph = vec![Node::End; 3 * count + 1];
            graph[0] = Node::Branch(1, count + 1);
            for i in 0..count {
                let join = 2 * count + i + 1;
                for spine in [1, count + 1] {
                    graph[spine + i] = if i + 1 == count {
                        Node::Jump(join)
                    } else {
                        Node::Branch(spine + i + 1, join)
                    };
                }
            }
            graph
        }
        "diamonds" => {
            let mut graph = vec![Node::End; 3 * count + 1];
            for i in 0..count {
                let start = 3 * i;
                graph[start] = Node::Branch(start + 1, start + 2);
                graph[start + 1] = Node::Jump(start + 3);
                graph[start + 2] = Node::Jump(start + 3);
            }
            graph
        }
        "loops" => {
            let mut graph = vec![Node::End; 2 * count + 1];
            for i in 0..count {
                let header = 2 * i;
                graph[header] = Node::Branch(header + 1, header + 2);
                graph[header + 1] = Node::Jump(header);
            }
            graph
        }
        _ => panic!("unknown fixture"),
    }
}

#[test]
fn cfg_compile_corpus() {
    let options = kernel::KernelOptions { wave64: false, split: false, mem_windows: 4, sampler_base: 0 };
    let mut outputs = Vec::new();
    for shape in ["joins", "diamonds", "loops"] {
        for count in [32, 256, 1024] {
            let input = shader(&nodes(shape, count));
            let dxil = kernel::translate(&input, options).unwrap_or_else(|e| panic!("{shape}/{count}: {e}"));
            if env::var_os("PB_CFG_VALIDATE").is_some() {
                validate::validate(&dxil).unwrap_or_else(|e| panic!("{shape}/{count}: {e}"));
            }
            let mut samples = [0.0; 3];
            for sample in &mut samples {
                let start = Instant::now();
                let actual = kernel::translate(&input, options).unwrap();
                *sample = start.elapsed().as_secs_f64() * 1e3;
                assert_eq!(dxil, actual);
            }
            samples.sort_by(f64::total_cmp);
            println!("{shape}/{count}: {} source instructions, {} DXIL bytes, median_ms={:.6}",
                     input.len() / 4, dxil.len(), samples[1]);
            outputs.extend((dxil.len() as u32).to_le_bytes());
            outputs.extend(dxil);
        }
    }
    std::fs::write(env::var_os("PB_CFG_OUTPUT").expect("PB_CFG_OUTPUT"), outputs).unwrap();
}
