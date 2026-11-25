# Native D3D12 mixed render target check

This separate fixture asks whether native D3D12 accepts the exact blend expressions extracted from AnyXboxX's `130bf10` and the attributed lot 9 adaptation. `mixed.hlsl` is original synthetic code. Its pixel shader writes an unsigned scalar to `R8_UINT` and a four-component float to `R16G16B16A16_FLOAT`. The same binary, shader bytecode, device and formats are used by both arms. The only changed input is the output of the original or adapted blend expression. [Lot 9 descriptor report](../REPORT.md)

The job launcher starts each worker independently under a shared 512 MiB process/job limit and a 3-second deadline. Host admission requires 4 GiB of available commit and 6 GiB of physical RAM before each arm and again before its suspended worker resumes. Each worker selects the named RTX 4070 Ti SUPER hardware adapter, checks both target capabilities and calls `CreateGraphicsPipelineState` once with an empty root signature. The baseline result can be `S_OK` or `E_INVALIDARG`. The candidate must return `S_OK`. Both check the device's removed status before reporting. This check creates no runtime textures, command list or draw. [D3D12 PSO API](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device-creategraphicspipelinestate) · [Format capability query](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device-checkfeaturesupport)

`build.ps1` prepares the source-extracted descriptors and compiles synthetic Shader Model 6.0 DXIL with Microsoft DXC, the worker with Rust and the launcher with LLVM-MinGW. `run.ps1` takes `-ApprovedNative` and a new output directory. It preserves each job and worker log and stops on unexpected output, status or adapter identity changes. [DXC release](https://github.com/microsoft/DirectXShaderCompiler/releases/tag/v1.9.2602)

## Verification status

The build completed with 4314 MiB available host commit and 10653 MiB free physical RAM. DXC's output signature lists `SV_Target0` as `uint x` and `SV_Target1` as `float xyzw`. One preflight stopped before launching at 3659 MiB available commit. The later allocated run passed after three consecutive PSAPI samples of 4563, 4564 and 4560 MiB available commit, with over 10 GiB physical RAM free in each sample.

| Exact blend expression | Integer blending | Float blending | RTX 4070 Ti SUPER `CreateGraphicsPipelineState` |
| --- | ---: | ---: | --- |
| Lot 9 baseline | On | On | `E_INVALIDARG` (`0x80070057`) |
| Attributed adaptation | Off | On | `S_OK` (`0x00000000`) |

Both workers used adapter LUID `[matched adapter identifier]`, reported identical format capabilities, passed the device-removed check and exited cleanly. Peak Windows Job memory was 79,937,536 and 81,698,816 bytes respectively. This run covers ordinary graphics PSO creation with synthetic shaders and the extracted expressions. The typed CPU A/B separately covers the depth-bounds and mesh descriptor expressions. [Baseline](rtx-4070tis-guarded/baseline-native.log) · [Adaptation](rtx-4070tis-guarded/candidate-native.log) · [Baseline guard](rtx-4070tis-guarded/baseline-guard.log) · [Adaptation guard](rtx-4070tis-guarded/candidate-guard.log) · [CPU report](../REPORT.md)

| Built artifact | SHA-256 |
| --- | --- |
| Vertex DXIL | `1d9c8fca75f87eb5fa05444788b3d65e75104d4e3fa290a2667849365dd44b49` |
| Pixel DXIL | `ac6e7b223d614e4b2a6552ca125f948e90104292b33e424a3f189cf41356c1e0` |
| Native worker | `65cd5692d9f9b1d0f83f760bd9276a5496ea1df297970fed115eb5919df51ab2` |
| Windows Job launcher | `23efc3f55344992a8aa7760e77f997324c073b4664bdc150c422d0a7f56b6b26` |

## Source and license

- The GPL-3.0-or-later transformation comes from **pablogonz12** and **FrancescoGelosoEterea**. The descriptor extraction checks both published helper texts for equality and verifies the exact receiving source revision. The worktree carries the receiving project's GPL license. [VIctory #1152](https://github.com/Marvisak/VIctory/pull/1152) · [Attributed victory-fork #51](https://github.com/fxceless/victory-fork/pull/51)
- `worker.rs` and `mixed.hlsl` are GPL-3.0-or-later. Their inputs consist of those extracted source expressions and the independently written shader. `job_launcher.cpp` is MIT and uses PortBridge's existing MIT `guard.h` and DXIL launcher pattern. The audited `guard.h` SHA-256 was `f07e7302b85bdcdd66745f283768e60a2e266b6a16847e3234f92d95606c161f`.
