# Does ordinary shader optimization remove the benefit?

PortBridge's single-bit mask projection retained its effect with three pending XCL changes enabled. On one RTX 4070 Ti SUPER, the complete translated raylib fullscreen draw fell from 5.181 to 4.187 ms and from 5.447 to 4.380 ms for the two camera views. The instrumented fragment executable fell from 221,568 to 197,888 bytes. All 720,000 RGBA32F output pixels matched the independently captured D3D12 views bit for bit. [Eight raw driver captures](vulkan) · [GPU times, intervals and executable sizes](vulkan/summary.json)

Both arms use XCL main `08db8020d323bf478964fcc586152cce54959cfc` and the same guest shader bytes. Decodere's #2501 prefers participating lanes for first-lane and scalar condition operations. ChAlanA's #2503 masks bridged compute comparisons with EXEC. Ramon Victor Cardoso's #2557 propagates known bits through scalar operators and removes redundant masks and shifts in the same direct-DXIL optimizer. PortBridge's rule changes how one consumer obtains its bit from four already-produced ballot results. [XCL main](https://github.com/xcl-dev/xcl/tree/08db8020d323bf478964fcc586152cce54959cfc) · [XCL #2501](https://github.com/xcl-dev/xcl/pull/2501) · [XCL #2503](https://github.com/xcl-dev/xcl/pull/2503) · [XCL #2557](https://github.com/xcl-dev/xcl/pull/2557)

| Open input set | Both variants validated | Smaller DXIL with projection | Identical DXIL |
| --- | ---: | ---: | ---: |
| Khronos Vulkan Samples | 122 | 16 | 106 |
| Naga snapshots | 50 | 4 | 46 |
| Microsoft MiniEngine, historical entries | 22 | 12 | 10 |
| MiniEngine, separate five display fixtures | 5 | 5 | 0 |
| raylib procedural | 3 | 1 | 2 |
| Combined | 202 | 38 | 164 |

There were 222 attempted entries. Eighteen could not be prepared and two failed translation or validation in both arms. Deduplicating successful entries by guest PAL bytes gives 34 changed out of 151 unique programs. No produced shader grew in DXIL or changed its static ballot count under the projection. The historical MiniEngine preparation had resource-binding collisions. A separate corrected replay of all 24 MiniEngine project entries validated 22 and showed 12 smaller, 10 unchanged. The corrected replay and the extra display fixtures overlap the main set and provide no additional independent sample count. [Paired full census](paired-2501-2503-2557.json.gz) · [Corrected MiniEngine census](fixed-mini-2501-2503-2557.json.gz) · [Shader-level comparisons](coverage.json)

The current-main stack with #2501 and #2503 produced different whole-mask DXIL from the earlier clean-main study on 95 of 202 entries. Adding #2557 changed five whole-mask entries and the same five projected entries. In Naga's binding-array texture shader the whole/projected pair measured 47,880/47,224 bytes before #2557 and 47,876/47,220 bytes afterward. The other four entries only changed under the known-bit simplifier. The benchmark thus exercised both optimizers, with one concrete example of additive reductions. #2557 produced byte-identical output on raylib raymarching and both heavy NeRF entries, in each arm. [Earlier draft stack](paired-2501-2503.json.gz) · [Per-entry positive controls](coverage.json)

### CPU cost of translating the full guest shader

| Guest pixel shader | Whole, ms | Projected, ms |
| --- | ---: | ---: |
| raylib raymarching | 59.34 | 52.85 |
| Mobile NeRF 71 | 75.97 | 65.50 |
| Mobile NeRF 73 | 75.14 | 66.89 |
| MiniEngine bicubic gamma | 11.15 | 10.79 |
| raylib Julia, unchanged DXIL control | 4.20 | 4.10 |

On the i5-13600KF, each worker timed seven complete XCL translations after an untimed warmup. Four counterbalanced process pairs provided independent block medians. The reported number is the median of those four medians. Each process verified that all its outputs were deterministic, and the runner matched both output hashes against the corpus receipt. The timer ends before explicit DXV validation, disassembly and disk writes. The retained compilation-time improvements on the three more expensive inputs are around 11–14%. The byte-identical Julia control varied by about 2.4% on this shared desktop, which limits interpretation of the smaller differences. This is guest-to-DXIL CPU time. Driver PSO creation and GPU execution are measured separately. [Individual timings, process order and output identities](translation.json)

### Vulkan execution and stage size

| Strong stack, actual Vulkan FS stage | Whole bytes | Projected bytes | Execution |
| --- | ---: | ---: | --- |
| raylib raymarching | 221,568 | 197,888 | Two 800 × 450 camera views |
| Mobile NeRF 71 | 457,984 | 411,392 | Pipeline creation and stage query |
| Mobile NeRF 73 | 457,216 | 412,288 | Pipeline creation and stage query |

Guest Wave64 ran on a physical NVIDIA subgroup of 32. Each camera/variant ran in a separate worker. After warmup, each worker issued five groups of eight draw calls. Whole/projected order was reversed between cameras. The percentage reductions of the median group average were 19.19% and 19.59%. The per-group ranges were 5.106–5.246 versus 4.140–4.221 ms, and 5.391–5.459 versus 4.369–4.441 ms. Background activity on this machine and a single physical card limit generalization. The original native-source Vulkan control in the earlier campaign measured 0.662/0.627 ms. The 128-byte increase in the two projected NeRF executables relative to the earlier clean-main stack illustrates that exact driver binary size depends on the baseline. These measurements establish neither D3D12 driver memory savings nor title-level frame time. [Input hashes](vulkan/inputs.json) · [Raw driver queries](vulkan/physical) · [Original source control](../../README.md#independent-process-and-same-pipeline-controls)

The NeRF 71/73 query processes peaked at 202.57/202.51 MiB of process commit for whole masks and 178.82/178.94 MiB for projection. These are single-process host observations with one captured pipeline per run. Hidden cache state had a substantial effect on pipeline construction. For the exact same projected ray fragment, creation took 905.36 ms in the primary camera process and 1.23 ms in the secondary process. The GPU execution timestamps were recorded after pipeline creation and warmup. A native cold-compile claim needs an independently controlled cache protocol. [Primary process](vulkan/draws/primary-project.json) · [Secondary process](vulkan/draws/secondary-project.json) · [NeRF process metrics](vulkan/physical)

## Reproducing the stack

1. Check out XCL main at `08db8020d323bf478964fcc586152cce54959cfc`. Cherry-pick `de915b5adb519c9aa342107fb05fbe56540541ff` and `10514822001f2302cd102b9431a9d8613e45cf3a`. The expected tree is `a4afdc436542c4f4f2f49a4b607bd5a7af8e6003`.
2. Apply the separate PortBridge SSA projection patch from XCL `ed8baf5de7bfe73208974d08a570acc95f978437`. This yields tree `b911f0a1a504347e798cd5c7abddf4b7b54c704c`. The ordinary and opt-in translator entry points select whole and projected arms in the same binary. Build the observer and run the four licensed manifests listed in the two full census files. Validate each emitted module with DXV. The corrected MiniEngine manifest was replayed separately. The experiment used Rust 1.100.0 gnullvm, release with opt-level 1. Its inputs and binary digests are in the compressed JSON. [XCL projection, observer and CPU corpus](../../../ssa-mask-projection/README.md) · [Corrected open inputs](../../../open-scenes/README.md)
3. Cherry-pick #2557 `2a1fadcf8eb4c67079e0b1646528a8603c804be7`. The complete tree is `a1d3e80dc4f7bbea5cee6bff1893763ecc306a2e`. Rebuild the observer and replay the same two modes. Each resulting census reports the source tree, observer, compiler, validator and input digests.
4. Convert the complete-stack raymarching and two NeRF DXIL pairs using the recorded five root-descriptor flags and dxil-spirv `b540c8a2484eecc7c2155994c806bbd8a8706f41`. Check each SPIR-V digest, validate against Vulkan 1.3 and use the existing `run_ray.py` / `run_probe.py` protocol. These comparisons added no new GPU data path. [Worker and conversion instructions](../../README.md#reproduce-from-source) · [Complete conversion identities](vulkan/inputs.json)

Rebuild the aggregate output on CPU with `python -B compare.py . <clean-main-census.json.gz> coverage.json`. From the parent Vulkan directory, regenerate the hardware join with `python -B summarize_projection.py strict-ssa/draft-overlap/vulkan <camera-reference-directory> strict-ssa/draft-overlap/vulkan/summary.json`.

For the translation timings, build the shared `observe_pixel_timed.rs` example against the three-draft stack and run `measure_translation.py` with four blocks, the matched census, the Khronos and raylib preparation directories, the corrected five-shader `--miniengine-display` directory, and `--compiler 2c4fe6f020fbe67cca6b41becb92e90f825fba60`. [Timing protocol](../../../ssa-mask-projection/measure_translation.py) · [Timed observer](../../../ssa-mask-projection/observe_pixel_timed.rs)
