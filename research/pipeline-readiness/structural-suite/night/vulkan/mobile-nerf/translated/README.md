# Executing translated Mobile NeRF fragment programs on Vulkan

On an RTX 4070 Ti SUPER, the PortBridge consumer and join transformation shortened the warm translated Mobile NeRF fragment pass from 297 to 163–170 µs in one model and from 265 to 156–157 µs in its Morpheus variant. Both candidates rendered all 57,600 pixels identically to both XCL controls. The original Khronos Vulkan pipeline took 13–14 µs. The inputs are deterministic generated features, directions, four distinct weight sets and per-pixel network selection. Both shaders come from one application family. [Original-source experiment](../README.md) · [Inputs and PAL bindings](../../../ssa-mask-projection/mobilenerf/README.md)

| 320 × 180, one fragment pass | Whole | Strict | Consumer + joins | Original GLSL |
| --- | ---: | ---: | ---: | ---: |
| Mobile NeRF, warm GPU µs | 297.344 | 195.072, 193.280 | 170.240, 163.456 | 13.440, 13.696 |
| Morpheus, warm GPU µs | 265.216 | 178.048, 184.320 | 156.288, 157.312 | 13.568, 14.080 |
| Mobile NeRF, Vulkan FS Binary Size in bytes | 475,776 | 428,800 | 409,600 | 45,184 |
| Morpheus, Vulkan FS Binary Size in bytes | 475,136 | 429,696 | 409,728 | 45,312 |
| FS Register Count for both models | 128 | 128 | 128 | 56 |

Each time is one worker's median of five means of eight full-screen draws, following one warmup. The two strict/consumer rounds used opposite orders. Whole had one ordinary worker per model. Separate captured pipelines supplied driver-reported fragment-stage statistics and rendered the same complete image as their ordinary counterparts. The statistic describes the captured executable for this driver. The ordinary workers' peak process commitment ranged from 60 to 198 MiB. Prior cache state varied. Whole-system driver memory and cold compilation costs were outside this comparison. [Raw timestamps, captures and hashes](measurements.json) · [Offline result check](check_results.py) · [Vulkan executable statistics](https://docs.vulkan.org/refpages/latest/refpages/source/VkPipelineExecutableStatisticKHR.html)

## Inputs and correctness

All three translated variants passed on 16 × 16 and 320 × 180. The full frame has 5,095 discarded pixels. Their clear RGBA and every pixel's alpha matched the independent CPU computation and the original Vulkan shaders exactly. Maximum live RGB error against the CPU was 3.58 × 10⁻⁷ and 4.18 × 10⁻⁷, respectively. Against the original GPU program the maximum was 2.39 × 10⁻⁷ on both. The final executable also reran all six typed diagnostic smoke draws after adding an in-process vertex/fragment SHA-256 check.

The strongest whole control uses XCL tree history at commit **051bdda602796c47c107419ae5afff8272d5ca2d**, stacking four upstream optimization proposals on merged main. Whole uses the ordinary mask path. Strict enables PortBridge's same-block SSA projection. The last column for a translated algorithm, “Consumer + joins”, enables commit **072b1f25bed8ef69d976f547d05fcc35f37db101** (tree **8f6b60c4401157edab802872381970c89962850b**). Rebuilding the two consumer inputs reproduced both recorded DXIL hashes. The guest Wave64 programs ran on a physical subgroup of 32. [Compiler baseline background](../../strict-ssa/draft-overlap/README.md) · [Per-artifact DXIL and SPIR-V hashes](modules.json)

## The Vulkan fixture

The six archived SPIR-V inputs came from the same DXIL variants used for D3D12, converted by dxil-spirv at **b540c8a2484eecc7c2155994c806bbd8a8706f41** with root UAVs 0, 2, 3, 4 and 5 in space zero. Guest SGPRs occupy 512 bytes and guest memory uses four independently addressed 16 KiB windows. The receiver binds four uploaded 2D textures and packs the native PAL image and weight descriptors. The original GLSL instead binds four subpass input attachments and four uniform buffers. Both receive the same texels and weights. The pass includes indexing, discard, network evaluation and writing the floating-point render target. Feature generation, upload, the host, pipeline creation, presentation and readback are outside the timing interval. This experiment covers the MLP inference pass on this GPU.

Before creating a graphics pipeline, the preparation step checks the source checksum, validates the interface, splits three numeric image aliases into typed, fully populated descriptor arrays and bounds device-address accesses. Each module has two constant-index SGPR loads, 552 vector loads constructed from independently traced, matching window address words, 12 image accesses and four private table lookups. Each vector load accepts aligned offsets through 16,368 bytes in one 16 KiB window. The ordinary profile retains bounds handling. The diagnostic profile additionally accumulates range, alignment and typed image-slot violations in a shader-private flag and reports them through output alpha. No exported pixel reported a violation. Diagnostics cannot observe an error that occurs solely in a discarded or helper invocation. The C++ worker independently verifies SHA-256 for the exact prepared fragment and fullscreen vertex before every bounded draw. It also verifies the root bytes and readback guards after drawing. [SPIR-V preparation](../prepare_translated.py) · [Worker implementation](../../ray_draw.inl) · [Vulkan image robustness](https://docs.vulkan.org/refpages/latest/refpages/source/VkPhysicalDeviceImageRobustnessFeatures.html)

The Vulkan receiver changes resource representation and adds bounds handling to all translated arms. Treat these measurements as translated Vulkan fixture results. Native Khronos remains roughly 12 times faster than the transformed translated path. The evidence establishes neither a production XCL runtime speedup nor end-to-end application performance. Hardware data here are PortBridge's own measurements on one RTX.

## Reproduce

Run the CPU-only receipt check from this directory with Python 3. On the measurement system the shader assembler/disassembler/validator were SPIRV-Tools **3c8fd352** (v2026.4), and the worker was compiled using the llvm-mingw and Vulkan-Headers versions in the parent instructions. The replay uses a Windows device with the program's required Vulkan 1.3 features. Python and NumPy produce synthetic inputs. Use a clean output directory for each draw. [Build the worker](../../README.md) · [Original reference build and render](../README.md)

~~~powershell
python check_results.py
$device = 'NVIDIA GeForce RTX 4070 Ti SUPER'
$worker = (Resolve-Path '../../pipeline_stats.exe').Path
$shaderTools = (Split-Path (Get-Command spirv-as.exe).Source)
$fixtures = '../../../ssa-mask-projection/mobilenerf'
$khronos = 'C:/src/Vulkan-Samples/shaders/mobile_nerf'
$env:OPENBLAS_NUM_THREADS = '1'

python "$fixtures/prepare_mobilenerf.py" --width 16 --height 16 --out smoke
python "$fixtures/prepare_mobilenerf.py" --width 320 --height 180 --out frame
python pack_mobileroots.py smoke
python pack_mobileroots.py frame
python -c "import gzip,pathlib; p=pathlib.Path('modules'); [(p/f.stem).write_bytes(gzip.decompress(f.read_bytes())) for f in p.glob('*.spv.gz')]"

foreach ($size in 'smoke','frame') {
    foreach ($n in '71','73') {
        $model = if ($n -eq '71') {'mlp_combo'} else {'mlp_morpheus_combo'}
        $native = "native-$n-$size"
        python ../run_source.py --worker $worker --sources $khronos --inputs $size --out $native --model $model --device $device
        if ($LASTEXITCODE) { throw 'Original render failed' }
        foreach ($mode in 'whole','strict','gamma') {
            $id = "nerf$n-$mode"
            foreach ($variant in 'bounded','typed') {
                $diagnostic = if ($variant -eq 'typed') { @('--diagnostics') } else { @() }
                python ../prepare_translated.py "modules/$id.spv" "$id-$variant.spv" --tools $shaderTools @diagnostic
                if ($LASTEXITCODE) { throw 'SPIR-V validation failed' }
                python ../run_translated.py --worker $worker --vertex "$native/quad.vert.spv" --fragment "$id-$variant.spv" --inputs $size --native "$native/frame.rgba32f" --out "$id-$variant-$size" --model $model --device $device
                if ($LASTEXITCODE) { throw 'Translated render or numerical comparison failed' }
            }
        }
    }
}
~~~

For the separate executable capture, append the final **capture** argument to the worker command below using the same prepared module and input. The worker creates a new output file. Keep ordinary timing and captured pipeline statistics separate.

~~~powershell
& $worker native-71-frame/quad.vert.spv nerf71-gamma-bounded.spv $device bounded-nerf frame capture-71-gamma.rgba32f 320x180 capture
~~~

The fragment source files and their compiled derivative modules retain the Apache-2.0 notices. The six bundled files contain first-stage converted SPIR-V only. [Sources, modifications and license](modules/SOURCES.md)

