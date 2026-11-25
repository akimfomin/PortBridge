# Cold pipeline readiness

The first complete frame waits for every required pipeline. Speculative startup compilation can use all worker capacity, all available compiler memory, or both before the actual drawing code requests a pipeline. Existing cache, first-use warming and demand priority can each hide part of the delay. [Active research decision](../../docs/decisions/013-pipeline-readiness.md)

## Documented workloads

- An XCL contributor reported individual compiles of 36–61 seconds during a contested cold run. The same four programs compiled together in 19 seconds in a quieter configuration. This was an observational comparison with a different background load. A separate 16 GB configuration reported no successful presents before memory exhaustion. [Compile report](https://github.com/xcl-dev/xcl/issues/2088#issuecomment-7170625467) · [Memory report](https://github.com/xcl-dev/xcl/issues/2088#issuecomment-7171049981)
- XBVK reports 700–1,000+ ms world-entry stalls and still tracks RAM-bounded worker scaling after shipping parallel mapped-library reads and other changes. [XBVK #3](https://github.com/0x0007b/XBVK/issues/3#issuecomment-7156836842)
- A VIctory Fork report describes a single compile whose driver heap exceeded 30 GB on one configuration. Estimated charges can govern concurrent work. An individual native build needs a separate safety boundary. [VIctory Fork #458](https://github.com/fxceless/victory-fork/pull/458)

The PortBridge preflight snapshot indexed XCL #2088 and XBVK #3. Exact source inspection established that XCL's worker reservations, size-class limits and express demand path already cover part of the design. The first experiments tested admission under **one cumulative compiler memory estimate** across demand and speculative work, with room reserved for the former before the first frame. [XCL source](https://github.com/xcl-dev/xcl/blob/7292dca0c25edfc5e8c8b3e581d0e3f8ef196762/crates/xcl/src/hle/d3d12x/real.rs#L3882-L3915)

The current [heavy graphics investigation](HEAVY-GRAPHICS.md) follows a measured 162-second semaphore wait to a graphics recorder. It prioritizes identifying the expensive phase for previously unseen required pipelines before testing a scheduling or compilation change. The earlier experiments below establish measurement and output controls at smaller scale.

The [ordered graphics implementation](ORDERED-GRAPHICS.md) starts exact native builds as their draw packets are discovered and keeps playback in order. It runs in the full open-scene renderer and is compared with blocking first use and eager compilation of exact known keys.

The [XCL compiler experiment](XCL-READ-GUARDS.md) tests whether merging identical read guards shrinks the work submitted to the native compiler. The [follow-up](XCL-READ-GUARD-VALIDATION.md) measures warm GPU execution and checks where the pass applies.

## Deterministic replay

`readiness.py` takes full opaque pipeline keys, integer compile durations and memory estimates, plus the timestamp of each warmup request and first-frame use. Equal keys share one compilation. A demanded queued pipeline moves to the tail of the demand queue, ahead of speculation. A running compile can finish without duplication and keeps its original charge until completion. A failed required compile records a terminal result, releases its budget and never reports a ready frame.

Four policies use the same priorities and global bounds. Demand-first uses all capacity. A second policy sets aside a worker. A third also sets aside estimated memory. The fourth applies that same reservation when an application phase signal arrives. The signal governs future admissions and cannot preempt an already running compile.

| Synthetic case | Demand-first | Reserve one worker | Reserve worker and memory | Arm at phase signal |
| --- | ---: | ---: | ---: | ---: |
| Worker contention | 88 ms | 13 ms | 13 ms | 13 ms |
| Combined memory pressure | 92 ms | 92 ms | 20 ms | 20 ms |
| Accurate early warmup | 100 ms | 100 ms | 124 ms | 100 ms |
| Phase signal arrives after long warmup admission | 132 ms | 132 ms | 52 ms | 132 ms |

The numbers are absolute times to all required pipeline handles in four constructed scenarios. The model exposes when a worker reserve is insufficient and when an early reservation prevents useful warming. It records every admitted compile, required wait, completion of all work, peak worker count and peak estimated charge. Full completion can precede frame readiness when the trace uses a prepared pipeline later. The estimates, durations, and use timestamps are fixed inputs. Driver memory and elapsed time under contention require native measurement.

```powershell
python -B -m unittest discover -s research/pipeline-readiness -v
python -B research/pipeline-readiness/replay_cases.py
```

## Physical Vulkan baseline

The Windows fixture creates compute pipelines and verifies actual GPU output on an RTX 4070 Ti SUPER, driver 617.14. The three contended arms each finish the same five background creations and one demanded creation. Two shared workers use FIFO or demand-first dispatch. The reserved arm keeps one of the two execution slots available for the demanded pipeline. It uses the caller for that slot, so the measured treatment includes its host-notification behavior. Both shared workers were in native calls when demand arrived in every contended block. One background call was active in every reserved block.

| Treatment | Request to verified output | Total work in timed window |
| --- | ---: | ---: |
| Cold, no background | 14.744 ms | 14.746 ms |
| Warm application cache, no background | 0.637 ms | 0.640 ms |
| Shared FIFO | 16.992 ms | 18.419 ms |
| Shared demand-first | 14.220 ms | 19.824 ms |
| One reserved slot | 11.067 ms | 22.701 ms |

Medians use four blocks with forward and reverse order and separate equal-shape shader recipes. The reserve improved demanded output in four of four pairs against demand-first. The paired median improvement was 2.89 ms. The entire contended batch took longer in three of four pairs. The demanded driver call itself often took longer with the reserve. The measured advantage is latency through the queue, the driver and observation together. The timed window excludes initialization, shader-module loading, compile-required probes, warm-cache priming and teardown.

All 20 runs verified 512 output words and two sentinel guards after a real compute dispatch, a host-read barrier and a fence. The 76 cold calls passed the compile-required preflight and showed no reported application-cache hit. Four warmed calls reported an application-cache hit. Partial driver-managed cache reuse remains possible. This tiny fixture bounds shader size and worker time. It does not measure real peak memory or the proposed memory reservation. [Raw timings](evidence/native-results.jsonl) · [Input manifest](evidence/manifest.json) · [Summary](evidence/native-summary.json) · [Vulkan host readback](https://docs.vulkan.org/guide/latest/synchronization_examples.html#cpu-read-back-of-data-written-by-a-compute-shader)

### Reproduce

From this folder on Windows use an x64 LLVM-MinGW C++20 compiler, `llvm-dlltool`, Khronos Vulkan-Headers and the installed Vulkan driver. The measured build used LLVM-MinGW 20261117, Vulkan-Headers `6802bb4733b63ed5efd3adb308a6c885ef180ea1`, DXC 1.9.2602 and SPIRV-Tools. Set the paths to your local tools. Select a fresh output directory and unused campaign number for each run. An implicit cache hit can otherwise invalidate the cold preflight.

```powershell
$toolPath = 'C:/tools'
python -B native_experiment.py build build-821 --clang "$toolPath/llvm-mingw/bin/clang++.exe" --headers "$toolPath/Vulkan-Headers/include" --dlltool "$toolPath/llvm-mingw/bin/llvm-dlltool.exe"
python -B native_experiment.py prepare inputs-821 --dxc "$toolPath/dxc/bin/x64/dxc.exe" --validator "$toolPath/spirv-tools/bin/spirv-val.exe" --campaign 821 --blocks 4
python -B native_experiment.py run inputs-821 build-821/native_probe.exe timing-821.jsonl --adapter 'NVIDIA GeForce RTX 4070 Ti SUPER'
```

## Acceptance boundary

The [full open-scene replay](full-scene/README.md) extends this fixture to 49 real indexed draws and a measured process-memory boundary. It includes stronger comparators with both the first-frame requirements known and an application cache already populated.

Use the same cache state, workers, key identities and resource envelope across comparisons. Confirm every required dispatch or draw by observing its output. Keep first-use latency, compile-queue time, pipeline creation and GPU completion separate. Record peak measured process commit separately from the estimate accounting. Vulkan pipeline creation feedback can attest an application-cache hit when its valid bit is present. The driver may have additional internal caches. [Khronos creation feedback](https://docs.vulkan.org/refpages/latest/refpages/source/VkPipelineCreationFeedbackCreateInfo.html) · [Khronos cache sample](https://docs.vulkan.org/samples/latest/samples/performance/pipeline_cache/README.html)

Use the [phase audit](HEAVY-GRAPHICS.md) to determine whether scheduling or the native build dominates the heavy path. Hold a candidate at research stage until its output matches, the first-output tail improves, and warmup and completion costs are recorded on the same workload.
