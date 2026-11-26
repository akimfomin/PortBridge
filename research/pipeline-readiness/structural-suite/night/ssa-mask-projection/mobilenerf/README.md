# Drawing the Mobile NeRF inference stage through XCL

The two unmodified Khronos fragment programs read four input attachments and select a neural network for each live pixel. This fixture supplies deterministic feature maps and four independently generated weight buffers. The CPU reference evaluates the same 11×16×16×4 network in double precision, applies the view blend and sRGB conversion, and retains the clear color on discarded pixels. [Khronos sources at the measured revision](https://github.com/KhronosGroup/Vulkan-Samples/tree/979aefaa5f2f4bd30efe035ca5a39444cc24ab9f/shaders/mobile_nerf)

The 320×180 target includes 5,095 discarded pixels. All four networks are exercised. Neighboring pixels select different networks over half the target. The two CPU references produce 19,703 and 18,565 distinct RGB8 colors among the 52,505 live pixels. The 16×16 smoke fixture has 236 live pixels. Both captures use an RGBA32F target. These inputs exercise the published inference stage. They do not include scene training, geometric rasterization or a full application frame. [Frame inputs](frame-manifest.json) · [Smoke inputs](smoke-manifest.json)

## Build and verify the inputs

Install Python 3 and NumPy. Keep the public shader corpus and the AMD standalone compiler version specified by the extraction manifest. Enable single-threaded BLAS during the comparison on memory-constrained machines.

```powershell
$env:OPENBLAS_NUM_THREADS = "1"
python prepare_mobilenerf.py --width 16 --height 16 --out smoke
python prepare_mobilenerf.py --width 320 --height 180 --out frame
python check_nerf_layout.py --corpus $corpusManifest --llpc $amdllpc --extractors $portbridgeCorpusTools --out pal
```

The layout check recompiles the original SPIR-V with pipeline dumping enabled, verifies byte-identical extracted AMD instructions, checks the PAL user-data register mapping and reads the five descriptor offsets for both shaders. Binding 4 occupies the start of the table. The four input attachments begin at dword offsets 64, 72, 80 and 88. The compiled PAL code reads four words per network descriptor and compares its third word with byte offsets. The D3D12 fixture binds three RGBA32F images, one R32_UINT image and four byte-addressed model buffers. [Verified ABI and fingerprints](bindings.json)

## Reproduce a translated draw

Apply the two published draw fixture patches in their documented order, then apply `xcl-mobilenerf-draw.patch` to the same XCL measurement checkout. Build the XCL library tests with `cargo test --locked -j1 -p xcl --lib --no-run`. Keep the resulting test executable and the published guarded Windows launcher. The physical test checks a fresh pipeline, full-target readback and contiguous image size. The shared runner inserts one untimed warmup before timestamping the requested draws. [Existing D3D12 fixture](../../open-scenes/README.md) · [MLP additions](xcl-mobilenerf-draw.patch)

For `mlp_combo` use guest shader 071. For `mlp_morpheus_combo` use 073. Translate both modes with identical guest bytes and root-4 ABI. Reproduce the independent native Vulkan image before passing it as `--native`. The results file retains image hashes, exact discard and alpha mismatches, maximum absolute RGB error over mutually live pixels, GPU timestamps where requested and the opaque pipeline-cache byte count. The runner records a failed or incomplete trial separately and stops if the translation changes its output or falls outside the source tolerance.

```powershell
python draw_mobilenerf.py --inputs frame --shader mlp_combo --strict $strict071 --consumer $candidate071 --native $native071 --guard $guard --tests $xclTests --dxc $dxcDir --draws 8 --rounds 3 --out draw071
```

The comparison uses an absolute tolerance of 0.0001 for the source color, exact alpha and exact coverage. The two translated variants must agree at every RGBA32F bit. Cache data is opaque. Driver-generated machine-code size requires a separate measurement. [Independent original Vulkan renderer](../../vulkan/mobile-nerf/README.md)
