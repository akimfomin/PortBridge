# Same-block SSA projection of pixel mask bits

PortBridge's direct-DXIL experiment preserves every original quad read and every wave ballot. It changes the arithmetic used by an instruction that reads just its own lane's bit. In an 800 × 450 procedural raylib draw on the RTX 4070 Ti SUPER, the matched Vulkan measurement improved from 5.177 to 4.210 ms for one camera and 5.446 to 4.404 ms for a second. Each resulting image matched its baseline across all 360,000 RGBA32F pixels. These are medians of warmed groups of eight fullscreen draws on one host, with no presentation cost.

## What changes

XCL's direct pixel backend collects four wave ballots to reconstruct two words of a guest scalar mask. For a mask producer's own-bit consumer in the same basic block, most of this reconstruction can be removed. Each original word contains four hardware carrier bits for each quad. For physical lane `i` within the selected 32-bit word, the baseline spreads the four carrier bits into guest position `i` when any carrier in the corresponding nibble voted for member `i & 3`. Exactly the same bit follows from this expression:

```text
((vote[i & 3] >> (i & 28)) & 15) != 0
```

The guest-width rules select the same word of each ballot that the original implementation would select. The lowering recognizes the exact mask SSA pair in the producing block. Scalar observations of that pair still read the full reconstruction. A mixed register pair, a new phi value or an unmatched consumer takes the ordinary path. When no other reader needs the reconstructed mask, XCL's existing dead code elimination removes the unused arithmetic.

This equivalence holds for any *concrete returned ballot words*. Helper-lane results that the API leaves undefined remain dependent on the underlying API. The transformation neither moves a cross-lane call nor replaces it with a local predicate. The earlier [Wave32 register-width counterexample](../wave32-carry/README.md) therefore remains a useful negative control. Runtime support for a particular guest wave size or subgroup mapping still inherits XCL's restrictions.

## Scope and measurements

The compiler revision is `ed8baf5de7bfe73208974d08a570acc95f978437` over public XCL `e1d84b7d9153f86a97d2ec5d209d196046fc0bea`. The corpus uses root-4 generic memory windows and XCL's current upstream optimizer. Its direct-DXIL sources are identical at subsequent main `08db8020d323bf478964fcc586152cce54959cfc`. The patch applies to either revision. [Compiler and regression patch](xcl-ssa-mask-projection.patch)

Of 222 prepared shader configurations, 18 lacked an eligible input and two failed XCL translation or validation. Among 202 validated pairs, 38 changed. All 38 containers shrank. No pair changed its static ballot count. The 202 pairs include multiple configurations of some sources, notably MiniEngine shaders; they represent five preparation groups. Their combined DXIL size fell from 2,423,908 to 2,260,876 bytes. The 71/73 Mobile NeRF variants share a source family. [Per-configuration data, revisions and input hashes](corpus.json.gz)

| Shader | Whole / projected DXIL bytes | Whole / projected IR instructions | Static ballots |
| --- | ---: | ---: | ---: |
| Mobile NeRF MLP combo | 283,496 / 229,864 | 44,349 / 34,694 | 1,737 / 1,737 |
| Mobile NeRF Morpheus combo | 283,988 / 230,608 | 44,374 / 34,765 | 1,737 / 1,737 |
| raylib raymarching | 177,584 / 151,968 | 28,300 / 23,107 | 538 / 538 |

On the raylib draw the NVIDIA Vulkan driver reported a fragment-stage executable size of 221,568 bytes before and 197,888 bytes after the transformation. Both timed pipelines returned their own statistics using `VK_KHR_pipeline_executable_properties`. Their SPIR-V graphs had 65 blocks and 538 ballot instructions in both versions. The Mobile NeRF fragment executable sizes changed from 457,984 to 411,264 and from 457,216 to 412,160 bytes. Those two comparisons created pipelines without rendering the NeRF scene. These measurements describe a Vulkan backend on this GPU and driver. They provide no measurement of D3D12 machine-code size, driver-wide memory pressure or another vendor.

A second comparison included the proposed XCL #2501, #2503 and #2557 together on main `08db802`. The corpus effect persisted on 38 of 202 configurations (34 of 151 distinct matched guest binaries). On this baseline, raylib fell from 5.181 to 4.187 ms and 5.447 to 4.380 ms, with all pixels equal. #2557 changed five baseline outputs, including a shader also improved by this projection. [Matched strong-baseline inputs, counters and raw Vulkan readings](../vulkan/strict-ssa/draft-overlap/README.md)

Microsoft MiniEngine provides a counterexample to uniform performance gains. Its BicubicUpsampleGammaPS frame stayed bit-identical at 800 × 450 and agreed with the original HLSL to less than 2.4 × 10⁻⁷ in RGB. DXIL shrank from 54,628 to 51,300 bytes and the D3D12 opaque PSO cache blob grew from 59,010 to 61,986 bytes. Two paired warmed GPU measurements changed from 0.228 to 0.256 ms and 0.241 to 0.211 ms. They establish no consistent draw-time improvement for this shader. [Open-scene comparison](../open-scenes/README.md)

On the i5-13600KF, translation from prepared guest ISA to serialized DXIL also became cheaper for the three large programs studied. Four counterbalanced blocks each used seven in-process samples after warm-up. The median of within-block medians was 68.56 → 59.95 ms and 68.43 → 59.86 ms for the two NeRF variants, and 53.83 → 48.43 ms for raylib. The unchanged raylib Julia control was 3.66 → 3.75 ms (overlapping block ranges). This timer ends before driver PSO creation. Each process validated its output against the separately recorded DXIL hash. [Samples and ranges](translation.json) · [Measurement driver](measure_translation.py) · [Timed compiler observer](observe_pixel_timed.rs)

On D3D12 with all three candidate upstream optimizations, the two Mobile NeRF programs reduced median cold native creation from 1,613 to 1,448 ms and from 1,603 to 1,434 ms. Raylib fell from 855 to 757 ms, while its two warmed views improved from 7.306 to 6.068 ms and 7.697 to 6.346 ms. The images matched across both configurations. [D3D12 timing, memory counters and full receipts](d3d12/README.md)

The ordinary XCL runtime API, followed by one guarded D3D12 draw of the raylib scene, saved 99–120 ms through the first verified CPU image in three fresh-process pairs. The six 800 × 450 readbacks were bit-identical. Median native graphics PSO creation fell from 855 to 751 ms. [Input, first-frame timings and replay](first-frame/README.md)

## Reproduction

Use the XCL root with its Windows Rust and DXC requirements. Apply the compiler patch. Run `cargo test --release --locked -p xcl --lib projected_mask_ -- --test-threads=1 --nocapture`. Run `gpu_direct_ps_masks_hold_helper_lanes_on_triangle_edges` separately for a GPU check of derivatives, helper lanes, WQM and a waterfall loop. The loop iteration count can vary with physical packing; the test checks the valid range and compares the deterministic derivative and coverage channels.

Run `python prove_projection.py` for the independent CPU algebra model and compare its output to [the recorded result](algebra.json). To replay a corpus input, copy [the observer](observe_pixel.rs) to `crates/xcl/examples/observe_pixel.rs`, build the example in release mode, and pass an authorized guest program and its PAL ABI fields. Use the `whole` and `project` modes with the same inputs. The source inside each included extraction manifest is identified by revision, license and shader hash.

The first patch provides an explicit offline entry point. A second [opt-in runtime patch](runtime/xcl-opt-in-runtime.patch) applies immediately after it on XCL main `08db8020d323bf478964fcc586152cce54959cfc` (final XCL commit `0c8a01c7fe0e7364803262bbcd700f869776362b`). In a new process set `XCL_DIRECT_DXIL=all` and `XCL_DIRECT_PIXEL_MASK_PROJECTION=1` to try it. The default stays with full reconstruction. Remove the second setting or set it to zero for a matched baseline.

The ordinary public `console_to_dxil_in` route compiled the licensed raylib guest stream in an independently generated synthetic container. Both explicit offline entry points retained their distinct reference results with the runtime opt-in set to one. [Reference check](runtime/offline-reference.json)

Four separate processes in off/on/off/on order returned byte-identical results to the corresponding offline outputs. The first two created separate translated cache entries, the second two preserved both files and timestamps. To reproduce, place [runtime_pixel.rs](runtime/runtime_pixel.rs) in the XCL examples directory and build it in release mode. Use [wrap_fixture.py](runtime/wrap_fixture.py) with the prepared guest ISA and whole DXIL signatures (raylib wave 64, SPI_PS_INPUT_ENA 769). Run [verify_cache.py](runtime/verify_cache.py) with the example, synthetic container, both offline DXIL paths and a fresh output directory. [Cache keys and complete output hashes](runtime/cache-evidence.json)

 The project has not received independent AMD, Intel or original guest-hardware measurements for this implementation. The direct compiler and the Vulkan driver measurements were taken on the same physical NVIDIA host.
