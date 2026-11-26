# Drawing the Mobile NeRF inference stage through XCL

The two unmodified Khronos fragment programs read four input attachments and select a neural network for each live pixel. This fixture supplies deterministic feature maps and four independently generated weight buffers. The CPU reference evaluates the same 11×16×16×4 network in double precision, applies the view blend and sRGB conversion, and retains the clear color on discarded pixels. [Khronos sources at the measured revision](https://github.com/KhronosGroup/Vulkan-Samples/tree/979aefaa5f2f4bd30efe035ca5a39444cc24ab9f/shaders/mobile_nerf)

The 320×180 target includes 5,095 discarded pixels. All four networks are exercised. Neighboring pixels select different networks over half the target. The two CPU references produce 19,703 and 18,565 distinct RGB8 colors among the 52,505 live pixels. The 16×16 smoke fixture has 236 live pixels. Both captures use an RGBA32F target. These inputs exercise the published inference stage. They do not include scene training, geometric rasterization or a full application frame. [Frame inputs](frame-manifest.json) · [Smoke inputs](smoke-manifest.json)

## Build and verify the inputs

Install Python 3 and NumPy. Keep the public shader corpus and the AMD standalone compiler version specified by the extraction manifest. Enable single-threaded BLAS during the comparison on memory-constrained machines.

```powershell
$env:OPENBLAS_NUM_THREADS = "1"
python prepare_mobilenerf.py --width 16 --height 16 --out smoke
python prepare_mobilenerf.py --width 320 --height 180 --out frame
python pack_mobileroots.py frame
python check_nerf_layout.py --corpus $corpusManifest --llpc $amdllpc --extractors $portbridgeCorpusTools --out pal
```

The layout check recompiles the original SPIR-V with pipeline dumping enabled, verifies byte-identical extracted AMD instructions, checks the PAL user-data register mapping and reads the five descriptor offsets for both shaders. Binding 4 occupies the start of the table. The four input attachments begin at dword offsets 64, 72, 80 and 88. The compiled PAL code reads four words per network descriptor and compares its third word with byte offsets. The D3D12 fixture binds three RGBA32F images, one R32_UINT image and four byte-addressed model buffers. [Verified ABI and fingerprints](bindings.json)

## Reproduce a translated draw

Check out XCL at `e1d84b7d9153f86a97d2ec5d209d196046fc0bea`, apply the standalone draw patch, and build the XCL library tests with `cargo test --locked -j1 -p xcl --lib --no-run`. The draw worker applies to the clean public tree and consumes offline DXIL from either compiler. It includes the descriptor bindings, RGBA32F readback and D3D12 timestamp support used by the original measurements. The original measured worker was built with the same draw test and runner inside the earlier shared fixture. The standalone patch was verified to apply in reverse to its exact clean source tree; the measured receipt records the earlier worker executable hash. The output directory must be new. [Standalone XCL test patch](xcl-mobilenerf-draw.patch) · [Original XCL revision](https://github.com/xcl-dev/xcl/tree/e1d84b7d9153f86a97d2ec5d209d196046fc0bea)

Apply `guard-small-job.patch` in a PortBridge checkout containing the published launcher and build its Windows executable with the documented C++ command. The 512 MiB child-job limit reserves 6 GiB of system commit and 4 GiB of available physical memory. A rejected run produces no timing sample. [512 MiB launcher change](guard-small-job.patch) · [Original launcher and build instructions](https://github.com/akimfomin/PortBridge/blob/64280ea4688f152100360403adb33f527f36c0a9/research/pipeline-readiness/XCL-READ-GUARDS.md)

For `mlp_combo` use guest shader 071. For `mlp_morpheus_combo` use 073. Translate both modes with identical guest bytes and root-4 ABI. Reproduce the independent native Vulkan image before passing it as `--native`. The results file retains image hashes, exact discard and alpha mismatches, maximum absolute RGB error over mutually live pixels, GPU timestamps where requested and the opaque pipeline-cache byte count. The runner records a failed or incomplete trial separately and stops if the translation changes its output or falls outside the source tolerance.

```powershell
& "$dxcDir/dxc.exe" -T vs_6_6 -E main -Fo fullscreen.dxil fullscreen.hlsl
python draw_mobilenerf.py --inputs frame --shader mlp_combo --strict $strict071 --consumer $candidate071 --native $native071 --guard $guard --tests $xclTests --dxc $dxcDir --dxv $dxv --vertex fullscreen.dxil --draws 8 --rounds 3 --out draw071
```

The dedicated D3D worker consumes the two prevalidated stages and records when the device is ready. The CLI invokes DXV in a separate process before entering the memory-limited driver worker. The comparison uses an absolute tolerance of 0.0001 for source color, exact alpha and exact coverage. Passing an original Vulkan image enforces that tolerance against both the CPU and translated results. The two translated variants must agree at every RGBA32F bit. Cache data is opaque. Driver-generated machine-code size requires a separate measurement. [Independent original Vulkan renderer](https://github.com/akimfomin/PortBridge/blob/64280ea4688f152100360403adb33f527f36c0a9/research/pipeline-readiness/structural-suite/night/vulkan/mobile-nerf/README.md)

The Vulkan translation worker can use the same guest resources through buffer device addresses. The SGPR buffer is 512 bytes. The guest allocation occupies 64 KiB, split into four 16 KiB windows. Only the first window carries descriptors and weights. The push constant addresses follow the order u0, u2, u3, u4, u5. Image descriptors occupy array positions 0, 2, 4 and 6. [Smoke allocation fingerprints](smoke-roots.json) · [Full frame allocation fingerprints](frame-roots.json)


On the RTX 4070 Ti SUPER the bounded D3D12 worker rendered 071 at 16 × 16. Both variants produced the same 256 RGBA32F values, including 20 discarded pixels. Maximum live RGB difference from the unchanged source Vulkan draw was 1.79 × 10⁻⁷. A single fresh-worker pair created the D3D12 PSO in 1,516.28 and 1,415.75 ms. Raw cache blob sizes were 322,818 and 296,578 bytes. These are single paired observations. The first 320 × 180 D3D12 attempt was stopped by the workstation memory guard before completing the strict pipeline; that incomplete attempt contributes zero timing samples. The independent Vulkan replay completed both 320 × 180 workloads. [D3D12 smoke receipt](d3d12/071-16x16/results.json) · [Interrupted D3D12 control](d3d12/071-320x180-incomplete/results.json) · [Full-size translated Vulkan measurements](https://github.com/akimfomin/PortBridge/tree/806a4c0dec2364c8881e1efb437964ac4aa42b27/research/pipeline-readiness/structural-suite/night/vulkan/mobile-nerf/translated)
