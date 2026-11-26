# Original Mobile NeRF fragment pass on Vulkan

The unmodified Khronos `mlp_combo.frag` and `mlp_morpheus_combo.frag` rendered the same generated scene inputs supplied to the XCL comparisons. The shaders use two feature attachments, a ray-direction attachment, a per-pixel unsigned model index and an array of four uniform buffers. Each buffer contains 532 float32 network parameters in the layout declared by the source. These fixtures use generated weights, features and directions. The workload covers the complete MLP fragment pass. It omits mesh rasterization into the feature buffers, model streaming and presentation. [Khronos shader sources and licenses](https://github.com/KhronosGroup/Vulkan-Samples/tree/979aefaa5f2f4bd30efe035ca5a39444cc24ab9f/shaders/mobile_nerf)

| Shader at 320 × 180 | CPU/GPU maximum live RGB error | Exact alpha / checked | Exact discarded RGBA | Per-worker median GPU ms per draw |
| --- | ---: | ---: | ---: | ---: |
| Mobile NeRF | 4.18 × 10⁻⁷ or less | 57,600 / 57,600 | 5,095 / 5,095 | 0.013440, 0.013696 |
| Morpheus | 4.18 × 10⁻⁷ or less | 57,600 / 57,600 | 5,095 / 5,095 | 0.013568, 0.014080 |

The two workers for each shader returned byte-identical RGBA32F frames. Each 16 × 16 smoke captured the 20 expected discarded pixels and matched the CPU result within 2.99 × 10⁻⁷. Full-image hashes, per-interval timestamps, the observed GPU/driver, memory peaks and all input hashes are in the receipts. These native-source numbers can serve as an application-side baseline when interpreting any XCL speedup. [Measurements](measurements.json)

The same input images now run through the full translated XCL fragment path on Vulkan. The three translated variants produced bit-identical frames in both models. [Translated passes, exact baselines and per-stage costs](translated/README.md)

## Reproduce

Build `pipeline_stats.cpp` using the existing Vulkan worker instructions. Supply the exact `mobile_nerf` source directory from the pinned Khronos checkout, the original four generated input images, the weights and CPU reference from the shared input manifest. The `--inputs` directory is the output of the shared `prepare_mobilenerf.py` generator. [Worker build](../README.md) · [Source runner](run_source.py)

```powershell
python run_source.py --worker ./pipeline_stats.exe --sources ./Vulkan-Samples/shaders/mobile_nerf --inputs ./frame --out ./native-combo --model mlp_combo --device "NVIDIA GeForce RTX 4070 Ti SUPER"
python run_source.py --worker ./pipeline_stats.exe --sources ./Vulkan-Samples/shaders/mobile_nerf --inputs ./frame --out ./native-morpheus --model mlp_morpheus_combo --device "NVIDIA GeForce RTX 4070 Ti SUPER"
```

The runner verifies source and fixture hashes, compiles the original fullscreen vertex and fragment shaders, validates SPIR-V and checks the fragment interface before drawing. Vulkan binds four read-only input attachments in set zero and four fully populated UBO descriptors at binding four. The worker checks the index bound before submitting, clears the output to –3, times five groups of eight warm draws using device timestamps, then reads back every RGBA32F pixel and checks its guard bytes. Reported group means exclude host setup, upload, attachment clear, pipeline creation, presentation and readback. A CPU build was permitted elsewhere on the same host during this run. Both worker processes used the same adapter. A fresh worker does not imply a cleared driver cache.
