# Unobserved pixel subgroup results

On a corpus of 202 validated pixel shader entries, 94 emitted different DXIL with this optional XCL pass. They represent 79 of the 151 distinct guest instruction streams. Two related Khronos Mobile NeRF shaders account for 52,968 of the 55,636 bytes saved across all entries. The largest saving on any other entry was 404 bytes. The numbers describe the direct DXIL path with four root windows and strict pixel-mask SSA projection. [Complete per-entry measurements](corpus.json.gz) · [Six-way ablation on five inputs](structure.json)

| Pixel shader | Prior SSA DXIL | With unused ballots removed | Also remove unused integer quad reads | Ballots removed | Additional quad reads removed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Khronos Mobile NeRF 071 | 229,892 B | 212,252 B | 203,580 B | 534 | 399 |
| Khronos Mobile NeRF 073 | 230,636 B | 212,960 B | 203,980 B | 534 | 399 |
| raylib raymarching | 152,076 B | 151,968 B | 151,968 B | 8 | 0 |
| Microsoft MiniEngine Display | 51,300 B | 51,300 B | 51,300 B | 0 | 0 |
| raylib Julia | 12,764 B | 12,676 B | 12,676 B | 6 | 0 |

## What the pass preserves

XCL's normal optimizer conservatively retains wave operations because their feature flags are collected as the module is built. The new offline entry runs after the stock optimizer and recognizes only the exact DXIL signatures for `waveActiveBallot` and, in a separate mode, integer `quadReadLaneAt` and the three integer `quadOp` directions. The mark-and-sweep visits operands including loop PHIs. It traces from other calls, memory operations, terminators, metadata references and instructions outside a narrow allowlist. One reachable ballot with a retained use must remain as a witness for WaveOps. A metadata use contributes to this static condition. Modules without a witness or removable subgroup operation retain their original instructions. Where enabled, the sweep can also delete unused narrow integer computations. No claim assigns the entire byte saving to the calls alone. The regular graphics entry and the runtime cache use the original compiler. [Source patch](xcl-unused-collectives.patch) · [Microsoft ballot specification](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/waveballot) · [Microsoft quad operation](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/quadreadlaneat) · [DXIL specification](https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/DXIL.rst) · [Related shader-flag discussion in XCL #1894](https://github.com/xcl-dev/xcl/issues/1894)

Each of 606 matched modules passed the real DXIL validator. All 202 reference hashes matched the archived comparison. Every arm kept the original SFI0 features, branch count and PHI count. The independent reader compared the complete SSA dependencies of ordered observable instructions, including branches, switches and PHI predecessors under label renumbering. Across one comparison per entry it checked 6,923 blocks, 29,802 root operations and 235,680 reachable value definitions. The ballot-only and ballot-plus-quad modes each passed. The reader accepts the DXC numeric-ID assembly format produced by this corpus. This check covers these emitted modules and leaves cross-vendor runtime testing open. [Checker](check_observables.py) · [Per-module controls](corpus.json.gz)

A static census found 1,228 individual ballot results with no direct SSA uses in the prior 202 modules. The guarded implementation removed 1,220. Its optional quad mode removed a further 816 integer quad operations over six entries, including 798 in the two NeRF shaders. DXIL size stayed equal or fell for every entry. The 18 representative conversions validated under Vulkan 1.3. Their SPIR-V still contained the measured ballot and quad reductions. SPIR-V and DXIL sizes describe intermediate code. [Static census](census-existing.csv) · [Validated SPIR-V sizes and identities](validated-spirv.json)

## Physical Vulkan result

On one RTX 4070 Ti SUPER, the driver reported 411,392 bytes for the Mobile NeRF 071 reference fragment executable and 411,136 bytes after the full sweep. The 0.062% reduction was much smaller than the 26,312-byte reduction in DXIL or the 94,300-byte reduction in SPIR-V. Both captures used the same physical adapter, driver, worker, vertex shader and resource layout. The candidate ran in a new bounded process. The existing reference capture was matched to the freshly produced SPIR-V by SHA-256. The measurement covers one fragment stage. [Raw driver results](native-evidence.json.gz)

The raylib fragment executable measured 197,888 bytes in both forms. The current sweep reproduced the exact SPIR-V already drawn in an earlier physical experiment. The exact before and after modules rendered two 800 × 450 RGBA32F images with matching output hashes, vertex shader, worker, driver, camera buffers and reference scene. The two historical sessions did not constitute a paired runtime timing experiment for this change. [Joined camera and module identities](matched-raylib.json) · [Identity checker](reuse_raylib.py)

We also ran the actual NeRF 071 inference fragment on the physical RTX with frozen image attachments, weights and draw parameters. The checked Vulkan fixture bounded the 552 memory-window additions, the four private lookups and all twelve image-index accesses. The 16 × 16 smoke and 320 × 180 frames matched the earlier strict SSA output bit-for-bit. The full frame preserved all 5,095 discarded pixels. The largest absolute channel differences were 2.39 × 10⁻⁷ against the unmodified source Vulkan fragment and 3.58 × 10⁻⁷ against the CPU implementation. All exported alpha values passed the diagnostic. The instrumentation cannot report an unexported fault from a discarded or helper lane. The executable-size capture above used the original translation, while these color comparisons used the instrumented rendering fixture. [Complete draw and preparation receipts](nerf-draws.json.gz) · [Reproduce the exact bounded shader](prepare_nerf_draw.py)

Two attempted D3D12 comparisons stopped during the first reference worker under the configured system reserve. Neither produced an admitted before/after pair. Cold D3D12 compilation and a system-level speedup for this sweep remain unmeasured. The Vulkan size and image measurements support retaining the offline pass for evaluation. [Stop receipts and exact inputs](cold-controls.json)

## Comparison with the Khronos optimizer

We ran both aggressive dead-code elimination and the complete performance pipeline from SPIRV-Tools v2026.4 on each original and swept SPIR-V pair. All 12 results passed validation. Both Khronos modes retained all 1,739 baseline ballots and 1,298 quad reads on NeRF 071. The same pipelines retained the 1,205 ballots and 899 quad reads in the XCL-swept module. On 071, complete optimization produced 919,644 bytes from the baseline and 820,576 bytes from the swept module. On 073 it produced 921,108 and 822,040 bytes. These SPIR-V savings coexist with the small driver-reported executable change above. [Raw comparator results](spirvtools.json) · [Comparator script](compare_spirv_tools.py) · [Official release](https://github.com/KhronosGroup/SPIRV-Tools/releases/tag/v2026.4)

A [standalone constant-color fragment](unused-subgroup.frag.spvasm) isolates the same behavior without XCL, a physical address or a shader extension. Both optimizers retain its unused ballot and quad read. The optimizer seeds liveness for operations outside its safe-to-delete set. Deleting a result whose value cannot be observed requires a different proof from moving two subgroup operations across changes in lane participation. [Khronos liveness roots](https://github.com/KhronosGroup/SPIRV-Tools/blob/ef96ed763b43b59b33b31b362f09a02b729fa1c9/source/opt/aggressive_dead_code_elim_pass.cpp#L668-L678) · [Delete classification](https://github.com/KhronosGroup/SPIRV-Tools/blob/ef96ed763b43b59b33b31b362f09a02b729fa1c9/source/opt/instruction.cpp#L1060-L1090)

```sh
spirv-as --target-env vulkan1.3 unused-subgroup.frag.spvasm -o minimal.spv
spirv-opt --target-env=vulkan1.3 --eliminate-dead-code-aggressive --strip-debug --compact-ids minimal.spv -o result.spv
spirv-val --target-env vulkan1.3 result.spv
spirv-dis result.spv
```

## Reproduce

Start with the [parent experiment and pinned shader preparation](../README.md#reproduce). Its Git source bundle supplies XCL commit `051bdda602796c47c107419ae5afff8272d5ca2d`, with the exact baseline set of upstream drafts. The [incremental bundle](xcl-unused-collectives.bundle) preserves experimental XCL commit `0944a17fda62bd201dd1dd76892ee4a03dca20a7` and its GPL-2.0-only sources. In that XCL checkout run:

```sh
git bundle verify /path/to/xcl-unused-collectives.bundle
git fetch /path/to/xcl-unused-collectives.bundle refs/heads/codex/pixel-unused-ballot-retention
git switch --detach 0944a17fda62bd201dd1dd76892ee4a03dca20a7
cargo build --locked --release -p xcl --example morning_prune
cargo test --locked --release -p xcl --lib pixel_sweep_ -- --test-threads=1
```

Both narrow regression tests passed on the pinned Windows build. They checked an observed ballot together with a derivative, a barrier and an unknown call, plus the exact fallback with only dead or unreachable ballots. The corpus observer used DXC 1.9.2609.5. Use `python verify.py` to check the raw receipts. To regenerate the corpus, run `python validate_corpus.py --help` for the prepared-input directories. Pass the [pinned corpus manifest](https://github.com/akimfomin/PortBridge/blob/929c53bddb836f7cea1483f3658f96c319662545/research/pipeline-readiness/structural-suite/night/vulkan/strict-ssa/draft-overlap/paired-2501-2503-2557.json.gz) to `--manifest` and [the parent measurements](../measurements.json.gz) to `--accepted`. Input hashes and compiler acceptance are checked before comparison. For the shorter six-arm run, use the [parent generator](../generate_arms.py) with the new observer and `--modes whole project ballot ballot-quad project-ballot project-ballot-quad`. The [SPIR-V preparation script](prepare_spirv.py) uses dxil-spirv revision `b540c8a2484eecc7c2155994c806bbd8a8706f41` with the established five root UAV bindings.

To reproduce the NeRF rendering fixture, use the [translated renderer and input recipe](https://github.com/akimfomin/PortBridge/tree/806a4c0dec2364c8881e1efb437964ac4aa42b27/research/pipeline-readiness/structural-suite/night/vulkan/mobile-nerf/translated). Apply the [single fixture addition](nerf-worker-fixture.patch) to that PortBridge checkout, keeping its existing worker checks. Build the worker with the public Vulkan headers using the renderer recipe. Call `python prepare_nerf_draw.py PATH/prepare_translated.py nerf71-project-ballot-quad.spv swept-bounded.spv --tools SPIRV_TOOLS_DIR`. Pass `swept-bounded.spv` to the existing `run_translated.py` with `--model mlp_combo`, first the 16 × 16 smoke and then the 320 × 180 fixture. The raw results preserve the worker identity used here. The later fixture-gated worker also checks the exact vertex and bounded fragment hashes before pipeline creation.

