# Projecting pixel mask observations on both sides of a ballot

A translated pixel comparison often constructs four individual predicates, packs them into one integer and immediately extracts the same four bits for four wave ballots. These operations survive direct DXIL generation on open shaders. PortBridge tested forwarding the predicates to the original ballots, a shared four-bit EXEC window, and a separate projection at the consumer of a full mask.

This is an offline compiler experiment. The independent upstream correctness contribution is the [ordinary HLSL Wave32 carry fix](https://github.com/xcl-dev/xcl/issues/2584#issuecomment-7178879816). The earlier aggressive Lane-local Masks experiment was withdrawn.

## Executing the same inference work

The expanded projection follows the two words of a mask through verified unions and through matching SSA predecessors. A full scalar observation retains the full value. A consumer that needs only the current quad can instead receive its four-bit window. The ballot still executes with its original participants. Sealed loop headers cache the projected PHI before visiting the return edge. Unknown input pairs and long expressions fall back to extracting from the original words. A physical loop regression checks both guest widths, two different starting masks and the full-word reference. All 8,192 pixel readbacks agreed with the independently computed answer. [Loop regression and compiler bundle](loop-control/README.md)

The inference pass from each of two licensed Khronos Mobile NeRF shaders ran on an RTX 4070 Ti SUPER with four generated feature/index textures and four independently populated networks. Each 320×180 image uses 52,505 live pixels. All 5,095 discarded pixels and every RGBA bit matched across the three translated compiler modes. The maximum channel discrepancy against the independently compiled original Vulkan shader was 2.39×10⁻⁷. The native reference and a separate CPU evaluation agree within 4.18×10⁻⁷ on these inputs. [Original Khronos shaders](https://github.com/KhronosGroup/Vulkan-Samples/tree/979aefaa5f2f4bd30efe035ca5a39444cc24ab9f/shaders/mobile_nerf)

| Warm GPU time for one inference draw | XCL full masks, upstream optimizer stack | Prior strict projection | Expanded projection | Original Vulkan |
| --- | ---: | ---: | ---: | ---: |
| Mobile NeRF 071 | 297 µs | 193–195 µs | 163–170 µs | about 14 µs |
| Mobile NeRF 073 | 265 µs | 178–184 µs | 156–157 µs | about 14 µs |

The GPU executed SPIR-V converted from actual XCL DXIL. The translated Vulkan harness supplies typed descriptor arrays and bounded addressable windows. These operations were identical in all translated arms. Ranges are fresh-run medians for the same scene. NVIDIA's fragment executable-size statistic for full, strict and expanded projection was 475,776 / 428,800 / 409,600 bytes for 071, and 475,136 / 429,696 / 409,728 for 073. All translated arms used 128 registers. The original Vulkan shaders used 56. These measurements cover the complete inference draw with controlled inputs. Whole-application frame time, AMD and Intel performance and the NVIDIA driver memory ceiling remain open. [Complete renderer and reproduction](https://github.com/akimfomin/PortBridge/tree/806a4c0dec2364c8881e1efb437964ac4aa42b27/research/pipeline-readiness/structural-suite/night/vulkan/mobile-nerf/translated) · [Per-run GPU times, register statistics and image hashes](https://github.com/akimfomin/PortBridge/blob/806a4c0dec2364c8881e1efb437964ac4aa42b27/research/pipeline-readiness/structural-suite/night/vulkan/mobile-nerf/translated/measurements.json)

An independent experiment removed ballots with no observable result. Two Mobile NeRF variants accounted for roughly 95% of the DXIL bytes saved across the corpus. On 071, removing 534 ballots and 399 quad operations reduced DXIL by 26,312 bytes. A separate Vulkan capture showed only a 256-byte fragment executable reduction on this workload, and no change in byte length on raylib. We retain this as a control on how poorly bytecode counts can predict native results. [Source, controls and raw results](unused-collectives/README.md)

The hardened comparison attempted 440 shader/guest-width configurations from the open corpus. Both compilers produced valid DXIL for 397. The new transformation changed 58 of those pairs, shrinking 34 and growing 24. The largest increase was 2,316 bytes. All 440 records, including unsupported inputs, were repeated on the final checked tree. Major warm execution savings have so far been demonstrated on two related heavy programs. For a normal XCL checkout the [separate opt-in runtime branch](https://github.com/akimfomin/xcl/commit/5d04cc10fa11654179d4bde0c1fcdc1d7ffb2cbc) sets a new pixel translation-cache identity. Enable `XCL_DIRECT_PIXEL_MASK_PROJECTION=1` before starting a new process in the direct pixel path.

The [compiler patches, licensed guest inputs and six-module reproduction](../structural-suite/night/ssa-mask-projection/consumer-demand/README.md) allow review against the same strong XCL source stack. The [D3D12 draw fixture](../structural-suite/night/ssa-mask-projection/mobilenerf/README.md) also completed the 16×16 comparison on a real RTX. The 320×180 D3D12 attempt stopped at the system commit reserve before producing a readback. The complete 320×180 results in this report use Vulkan.

## What changes

The compiler preserves the scalar mask value, the instructions performing the votes, their operands' producer block and their participation. For a defined predicate in a plain pixel VOPC comparison, `bit(p, sum_i(zext(predicate[i]) << i)) = predicate[p]`. A second arm computes the aligned EXEC word once. An aligned four-lane group cannot cross the boundary between the low and high 32-bit words. Lanes outside the quad cannot contribute to its four local bits. Scalar consumers still receive the complete original mask. [Implementation patch](quad-inputs.patch) · [Independent code and measurement review](critical-review.md) · [Definitions for helper and active lanes](https://github.com/microsoft/DirectXShaderCompiler/wiki/Wave-Intrinsics)

The separate expanded consumer remembers the exact originating pair of SSA values. It can project an individual lane bit after an intervening mask write when that original pair is still the operand. The experiment combines both transformations in a separate commit. This distinction permits measuring compiler cost and GPU output for each marginal change. [Composition patch](consumer-composition.patch)

## Measurements

Measurements used Windows 11, RTX 4070 Ti SUPER and NVIDIA driver 617.14. XCL's direct DXIL path included the merged #174 and four candidate changes. Their contributions were Decodere's participating-lane correction, ChAlanA's EXEC guard, Ramon Victor Cardoso's known-bit folding and Emu Synths' graphics scalar reload elimination. The same guest bytes, resource layout and shader profile were used in each comparison. [XCL main](https://github.com/xcl-dev/xcl/tree/08db8020d323bf478964fcc586152cce54959cfc) · [#2501](https://github.com/xcl-dev/xcl/pull/2501) · [#2503](https://github.com/xcl-dev/xcl/pull/2503) · [#2557](https://github.com/xcl-dev/xcl/pull/2557) · [#2446](https://github.com/xcl-dev/xcl/pull/2446)

Of 222 entries from raylib, Microsoft MiniEngine, Khronos Vulkan-Samples and Naga, 18 had no prepared guest and two failed in all three compiler modes. Of the remaining 202, 58 produced smaller validated DXIL with the producer-side transformation, including 54 distinct guest byte streams out of 151. The other 144 had unchanged module size. None grew in this producer experiment. The expanded consumer has its own coverage and regressions.

Four counterbalanced D3D12 blocks measured one native pipeline creation in each fresh, bounded process. The two Khronos Mobile NeRF variants share substantial shader code.

| Open workload | Prior SSA | Direct predicates | Predicates and shared EXEC window |
| --- | ---: | ---: | ---: |
| Mobile NeRF 071 | 1,577 ms | 1,476 ms | 1,479 ms |
| Mobile NeRF 073 | 1,533 ms | 1,533 ms | 1,468 ms |
| raylib raymarching | 799 ms | 723 ms | 721 ms |

A second four-block series measured the same four combinations together. Each entry is the median of four guarded processes, and both compiler arms emit the same DXIL in their shared control. The interacting stages gave the clearest improvement on 073. Their individual gains did not add on raylib.

| Open workload | Prior SSA | Producer only | Expanded consumer only | Both |
| --- | ---: | ---: | ---: | ---: |
| Mobile NeRF 071 | 1,502 ms | 1,434 ms | 1,451 ms | 1,419 ms |
| Mobile NeRF 073 | 1,535 ms | 1,461 ms | 1,445 ms | 1,378 ms |
| raylib raymarching | 764 ms | 734 ms | 779 ms | 738 ms |

One earlier incomplete run stopped when free system commit fell below the configured reserve. Its receipt is retained separately. Reported medians use complete blocks. For the earlier ablation, the shared window reduced median peak process commit by about 1.6–3.4 MiB. Reported local DXGI usage had a zero median delta between the start and end of pipeline creation on each measured arm. These counters have different scopes.

Direct predicates alone produced the same Vulkan fragment executable **byte length** and the same D3D12 cache blob **byte length** on all three shaders. Adding the shared EXEC window reduced the driver's reported Vulkan fragment executable by 4,224, 3,840 and 768 bytes respectively. Register counts remained 128, 128 and 168. The captures do not disclose the D3D12 instruction stream.

Each translated variant of the raylib scene produced the same 360,000 RGBA32F pixels per view on Vulkan. Two cameras were timed in opposite order. The native source drew in about 0.6–0.7 ms, the translated shaders in about 4.2–4.5 ms. The native and translated outputs differed slightly in floating-point arithmetic. The hash checks compare translated variants to one another, and raw error metrics against the original OpenGL source are retained for each. The incremental producer change did not demonstrate a clear warm draw-time advantage. Measurements of NeRF PSO creation concern the compilation step. Driver heap exhaustion and whole-title speed are unmeasured.

## Correctness and scope

A CPU truth-table covers 393,216 bit observations across both guest widths, all possible quad predicates, every lane, active masks and four background patterns. A separate physical test compares derivatives and coverage and bounds the waterfall count at triangle edges. A Wave32/Wave64 guest CMPX program also exports the complete updated EXEC words as exact 16-bit halves. Across nine 32×32 draws, all 9,216 words matched a CPU oracle. Active physical lane 32 requires a native Wave64 adapter. The original Windows test suite and these new experimental tests have distinct revisions. [CMPX instructions and readbacks](cmpx-control/README.md) · [CPU model](check_quad_projection.py) · [Complete suites on the two published revisions](https://github.com/akimfomin/PortBridge/tree/929c53bddb836f7cea1483f3658f96c319662545/research/pipeline-readiness/structural-suite/night/full-workspace)

A cross-quad operation can return an unspecified value for a helper invocation. The identity applies to defined contributing values. It introduces no new memory access or collective and makes no guarantee about equality of arbitrary unspecified helper values. It leaves filtered or non-pixel opcode paths on the original lowering. No part of this prototype is enabled in ordinary XCL.

## Reproduce

Download [the source bundle](xcl-experiment.bundle) next to a checkout of XCL that contains `08db8020d323bf478964fcc586152cce54959cfc`. The bundle preserves the GPL-2.0-only source, author credits, individual commits and experiment parents. From the checkout, run the following commands. The last command requires Windows, DXC and a real D3D12 adapter.

```sh
git bundle verify ../xcl-experiment.bundle
git fetch ../xcl-experiment.bundle 'refs/heads/*:refs/remotes/portbridge-study/*'
git switch --detach ba83447cd9ce59035cead63bc340135b5e46bc1b
cargo build --locked --release -p xcl --example morning_mask
git switch --detach a764afcfd076a052ad8937e37f168c4863b301e6
cargo test --locked -p xcl --lib gpu_pixel_cmpx_preserves_partial_exec_words -- --test-threads=1 --show-output
```

The strongest control is `051bdda602796c47c107419ae5afff8272d5ca2d`. At `ba83447` the observer's `project` arm emits the strict control, `inputs` also forwards the four i1 values, and `window` additionally shares the aligned EXEC read. At `6fe8a22189c763f73ac44e09f109b10c5fbfee93` all three named arms also use the expanded consumer. The `whole` arm preserves the original complete mask path. The CLI runs DXC validation and disassembly for every output.

Run `python verify.py` to recheck the counts, identical readbacks and counterbalanced samples from the [raw receipts](measurements.json.gz). For a new hardware run, use [generate_arms.py](generate_arms.py) and [corpus_coverage.py](corpus_coverage.py). They require the four licensed shader source groups and check the SHA-256 of every prepared guest before invoking XCL. The two scripts accept a decompressed [pinned manifest](https://github.com/akimfomin/PortBridge/blob/929c53bddb836f7cea1483f3658f96c319662545/research/pipeline-readiness/structural-suite/night/vulkan/strict-ssa/draft-overlap/paired-2501-2503-2557.json.gz). The pinned source revisions and licenses are in its `input_manifests`. [Guest preparation and cameras](https://github.com/akimfomin/PortBridge/tree/929c53bddb836f7cea1483f3658f96c319662545/research/pipeline-readiness/structural-suite/night/open-scenes) · [Guarded D3D12 worker](https://github.com/akimfomin/PortBridge/tree/929c53bddb836f7cea1483f3658f96c319662545/research/pipeline-readiness/structural-suite/night/ssa-mask-projection/d3d12) · [Vulkan workers, conversion and checker](https://github.com/akimfomin/PortBridge/tree/929c53bddb836f7cea1483f3658f96c319662545/research/pipeline-readiness/structural-suite/night/vulkan)
