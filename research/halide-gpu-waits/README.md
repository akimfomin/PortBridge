# Callback-driven waits for Halide WebGPU

Halide 22.1.0's legacy browser runtime checks completion with short Emscripten timers. A 512×512 Gaussian preview issued six error-scope waits and a mapped readback for one update. A separate stock trace measured about 29 ms parked in error-scope timer waits and another 4.6 ms parked during mapping. The two warm compute pipeline creations took about 0.05 ms together, and retaining both pipelines saved 0.13 ms in a separate controlled comparison. [Halide error-scope wait](https://github.com/halide/Halide/blob/v22.1.0/src/runtime/webgpu.cpp#L178-L214) · [Halide pipeline cache issue](https://github.com/halide/Halide/issues/9565)

The prototype resumes the serialized WebAssembly call after the corresponding browser callbacks run. The standard WebGPU error scopes, result delivery, and map callbacks still run. The intervention uses the same Halide Wasm binary, dispatches, shaders, GPU submits, and readback as the control. A second factor independently enables bounded reuse of warm pipelines. The implementation adapts an established asynchronous mechanism to diagnose and remove the timer polling in this runtime. [Modern Emdawnwebgpu wait](https://dawn.googlesource.com/dawn.git/+/bf982d6349783f4c176ae6e4cdd78c8d9068fd9d/third_party/emdawnwebgpu/library_webgpu.js) · [WebGPU error scopes](https://www.w3.org/TR/webgpu/#error-scopes)

## Measured application boundary

The preview applies a new filter parameter to a resident photograph and times actual Halide processing through WebAssembly readback and the synchronous canvas bitmap update. Initial image decode and upload, independent validation, browser compositing, and display scanout are outside the window. Each workload used four variants in a balanced order in isolated headless Chrome on an RTX 4070 Ti SUPER. Values below are medians of round averages in milliseconds.

| Workload | Stock GPU | Warm pipeline reuse | Callback-driven GPU | Reuse and callbacks | Best matched CPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| 512×512 NASA astronaut, two-pass Gaussian | 33.69 | 33.08 | 5.70 | 5.51 | 0.885 |
| 1000×872 NASA Hubble, three-pass Laplacian of Gaussian | 45.10 | 43.76 | 9.90 | 9.19 | 6.334 |

The primary runs compare 320 Gaussian and 192 Hubble rendered frames. Every equal-parameter GPU result matched across the four arms at the float bit level. Independent Float64 implementations checked all 251,310,080 values. The GPU variants issued the same operations for each workload, including 12 or 16 error pops, one copy and map, and three or four submits per preview. The Gaussian trace measured zero polling sleeps for the two watched waits with the prototype. The actual-error control used a separate recoverable Halide host. An absent shader entry point produced the same validation message, return code and eight scope pops in both modes. A subsequent valid preview recovered the exact reference hash. [Input provenance and reproduction](REPRODUCTION_INPUTS.md) · [Verified measurements and hashes](evidence)

The best CPU time uses one Wasm SIMD thread for Gaussian and six for Hubble on an i5-13600KF, measured in separate fresh browser sessions with the same image, filter, output boundary and Float64 checks. The single-thread Hubble run took 17.63 ms. The strongest CPU path won both host-visible workflows. Further GPU work needs a representative application whose existing GPU path is required or materially faster than its strongest CPU alternative.

## Integration boundary

`callback_parking.mjs` watches completion after the original generated glue has invoked the C callback. `patch_preview_glue.py` requires the pinned Emscripten bridge shape and emits a separate module. The experiment assumes one serialized Halide caller, one Asyncify instance, and treatment changes between completed calls. An upstream implementation needs explicit wait groups at the exact kernel error and map boundaries so unrelated one-millisecond sleeps retain their established behavior. Device loss, map rejection, out-of-memory recovery, foreground browsers, other hardware, and modern Emdawnwebgpu each require independent confirmation.

The implementation leaves queue completion on its existing path. The measured improvement applies to host-side waiting and application response in the two previews. The results give no estimate for proprietary titles, the published native Dawn CTest, or general GPU kernel throughput. Compute-dependent porting work should measure waits against the original application's correctness and observation requirements.
