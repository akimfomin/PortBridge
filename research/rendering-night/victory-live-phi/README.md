# PortBridge · VIctory #1716 research handoff

The optional optimizer folds a narrow class of live i32 PHI cycles in loop headers. It follows the existing PHI inputs and replaces each member only when the group has one available entry value, the types match, and the header has exactly the entry edge and self-latch. The two-seed cases keep their two values. This is an independent GPL-3.0-or-later implementation of a restricted case from Braun et al. [VIctory PR #1716](https://github.com/Marvisak/VIctory/pull/1716) · [Algorithm reference, §3.2](https://pp.ipd.kit.edu/uploads/publikationen/braun13cc.pdf)

The patch targets PR head `758bf7fbc6a35403028c4410ec94a5738b96bc29`. The local checkpoint containing the same optimizer is `718574ed12a2294eca0489891015a8c6a086cde9`. The patch uses #1716’s value rewrite and DCE. Stock VIctory’s writer has a different entry point, so the patch requires the PR base. [Exact baseline](https://github.com/Marvisak/VIctory/commit/758bf7fbc6a35403028c4410ec94a5738b96bc29)

PortBridge generated the scalar rotations and oracles. The resource setup adapts alessiodeia’s GPL-3.0-or-later `valu_tests.rs` fixture. The native readback reused VIctory’s upstream compute harness. The sources in this handoff use the same project license. [Original VALU fixture](https://github.com/Marvisak/VIctory/commit/2e5001cf9d11c7210c5f1409b7418e49c17e8ff3) · [Exact upstream host harness](https://github.com/Marvisak/VIctory/blob/758bf7fbc6a35403028c4410ec94a5738b96bc29/crates/victory-shader/src/emit/host.rs#L944) · [License](LICENSE)

## Verification

| Registers | Incoming values | PHIs before → after | DXIL bytes before → after | Native RTX readback |
| ---: | ---: | ---: | ---: | --- |
| 2 | 1 | 4 → 2 | 2132 → 2120 | 2/2 |
| 2 | 2 | 4 → 4 | 2152 → 2152 | 2/2 |
| 16 | 1 | 18 → 2 | 2596 → 2500 | 2/2 |
| 16 | 2 | 18 → 18 | 2616 → 2616 | 2/2 |
| 64 | 1 | 66 → 2 | 4168 → 3724 | CPU/DXV |
| 64 | 2 | 66 → 66 | 4184 → 4184 | CPU/DXV |

Microsoft DXV accepted all 12 containers. A bounded CPU evaluator matched every output store with three different input pairs per container. The two-seed controls were byte-identical. The native RTX 4070 Ti SUPER runs matched all 72 words across eight cases on one physical adapter. The first session stopped after two cases on low system commit and the later session completed the remaining six. GPU coverage is one adapter and stops at 16 registers. Runtime, game-corpus prevalence and driver performance are unmeasured. [CPU results](evidence/cpu-paired.json) · [Native results](evidence/native-summary.json)

## Reproduce the CPU comparison

From a checkout at the exact PR head, apply the two patches. `fixture-only.patch` adds an opt-in Cargo example and can be applied independently for baseline work. Copy or reference this directory as `$handoff`, then use the repo’s Windows x64 Rust toolchain and the `bin/x64` directory from Microsoft’s DXC `v1.9.2602` release. The runner creates a new evidence directory. [Microsoft DXC v1.9.2602](https://github.com/microsoft/DirectXShaderCompiler/releases/tag/v1.9.2602)

```powershell
$handoff = (Resolve-Path '..\transfer-victory-1716-source').Path
$dxc = (Resolve-Path 'C:\path\to\dxc\bin\x64').Path
git apply --check (Join-Path $handoff 'victory-1716-entry-phi-rings.patch')
git apply (Join-Path $handoff 'victory-1716-entry-phi-rings.patch')
git apply (Join-Path $handoff 'fixture-only.patch')
cargo build --locked -j1 -p victory-shader --example portbridge_phi_emit
python -I (Join-Path $handoff 'compare_emit.py') --exe .\target\debug\examples\portbridge_phi_emit.exe --dxc-dir $dxc --output .\phi-results
```

The comparison uses one executable. The control sets `VICTORY_PHI_RINGS_OFF=1`, and the candidate leaves it unset. The validated fixture body linked against Rust 1.100 gnullvm and LLVM-MinGW. The example patch wraps that body in a Windows entry point. The native worker and its generator are preserved under `native-source/` as a source record. They reference the exact regenerated and verified containers and require compatible VIctory and `windows` 0.62.2 rlibs to link. This bundle contains source, license, patches and text evidence.
