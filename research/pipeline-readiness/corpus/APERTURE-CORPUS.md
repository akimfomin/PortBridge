# Proved XCL UMA aperture specialization corpus

The probe uses XCL source `6f67464c15f2b660c7a018daf6dc91aa06c4b82a`. For each accepted input, the generic and proved translations use the same raw gfx1030 pixel instructions and the same synthetic XCL signature. The proved translation receives UMA base high dword 4. All comparisons use four memory windows. Independent DXV validates each successful output. The code generator's ignored cases remain visible in the input manifests. All numbers below count shader entries. Byte-identical raw RDNA inputs are identified separately in the data.

| Source cohort, root-4 | Accepted pairs | Changed DXIL | Fewer switches | Total switches | Total basic blocks | Total DXIL bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| MiniEngine plus Naga | 72 | 38 | 25 | 140 → 101 | 1,514 → 1,397 | 560,236 → 552,388 |
| Independent Khronos Vulkan Samples | 122 | 77 | 65 | 823 → 720 | 5,089 → 4,780 | 1,565,776 → 1,545,976 |

In heap-4, the same 38 and 77 entries change. The basic block and switch totals stay equal. Aggregate DXIL sizes fall by 1,984 and 6,076 bytes respectively.

The independent sample takes all 138 `.frag` files in Khronos Vulkan Samples `shaders/`. Fourteen exclusions occur before XCL. Two shader entries fail at XCL in both arms. Each surviving shader entry is compiled from GLSL to SPIR-V, validated, and compiled by AMD LLPC to a standalone gfx1030 PAL ELF. The analysis extracts the ELF fragment entry after rejecting text relocation dependencies. Vulkan bindings are not modeled by the synthetic XCL signature. The results measure structural applicability and do not measure original Vulkan rendering, native D3D12 instructions, or driver timings. [Khronos source and license](https://github.com/KhronosGroup/Vulkan-Samples/tree/979aefaa5f2f4bd30efe035ca5a39444cc24ab9f)

## Evidence files

The `../evidence/` directory contains the complete paired shape metrics, source hashes and tool hashes. The `replay-*/` directories contain local-only DXIL and disassembly outputs.

- `xcl-address-corpus-census.json` reports the prior 72-input static investigation. Of 19 adjacent constant-offset pairs with the same low and high base, zero can be proved to keep the same carry using the conservative interval and known-bits analysis. This is distinct from the new fallback-safe aperture proof.
- `khronos-fragment-prep.json` describes the independently compiled source inputs and includes exclusions.
- `replay-naga-mini-root4-aperture.json` and `replay-khronos-root4-aperture.json` describe the root-window comparisons. The two `*-heap4-aperture.json` files cover the heap-window control.

## Reproduction

Use `address_census.py` against an existing original corpus directory that contains four-window baseline heap and root disassemblies. The existing [PortBridge corpus instructions](https://github.com/akimfomin/PortBridge/blob/3de1234dfd0cc137664ae17caad50ce02bb99bde/research/pipeline-readiness/corpus/README.md) produce it.

For the Khronos inputs, obtain a clean sparse source checkout at `979aefaa5f2f4bd30efe035ca5a39444cc24ab9f`. Run `prepare_khronos.py` with the matching glslang, SPIRV-Tools, AMD LLPC and llvm-readobj builds listed in the input manifest. The prior public corpus package supplies the ELF and PAL metadata helpers imported by this script.

Build `readguard_uma_aperture.rs` in `crates/xcl/examples/` of the pinned XCL source. Run `replay_aperture.py --help` for parameters. Run both `--layout root-4` and `--layout heap-4` against each of the two input manifests, using separate new output paths and the exact XCL source revision. Use DXV independently from the compiler library used by XCL. The proved base defaults to 4.
