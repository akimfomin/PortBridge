# Halide WebGPU interactive preview reproduction

The measured Windows run uses Python 3.12.14, Halide 22.1.0, Emscripten 4.0.17, Node 24.22.1 and Chrome 158.0.8127.37 in a separate headless profile. Chrome acquired a nonfallback NVIDIA Lovelace adapter. The machine reported one NVIDIA card, an RTX 4070 Ti SUPER, PCI device `0x2705`, driver `617.14`.

## Inputs and tools

- [Halide 22.1.0 package](https://pypi.org/project/halide/22.1.0/) `halide-22.1.0-cp312-abi3-win_amd64.whl`, SHA-256 `ed79e211241f22628d6c2cb1a23ba0b92d8878a6255532dbb0b2dd43403c3839`.
- [Halide runtime 22.1.0](https://pypi.org/project/halide-runtime/22.1.0/) `halide_runtime-22.1.0-cp312-abi3-win_amd64.whl`, SHA-256 `06e0ffef13b298383fc1bb753d611382f9586f5817f5991e1cb886731fe06951`.
- [Halide binary 22.1.0](https://pypi.org/project/halide-bin/22.1.0/) `halide_bin-22.1.0-py3-none-win_amd64.whl`, SHA-256 `246e645193293b1b33ffc8659b2049a97299e5c36e1a2db9384791158105f31d`.
- [Emscripten 4.0.17 Windows SDK](https://storage.googleapis.com/webassembly/emscripten-releases-builds/win/41d2106c68c28e101e6252a48e22c78b07722508/wasm-binaries.zip), 636,832,767 bytes, published GCS MD5 `e2258e79beb1b63427153d757da97c32`, Emscripten compiler revision `bb11bae`. Halide's pinned WebGPU instructions use its legacy C ABI. Emscripten 4.0.18 and later replaced the legacy flag. [Halide WebGPU build instructions](https://github.com/halide/Halide/blob/e9485e16333fd5cd8457d63a0827ee15fdf35e0e/doc/WebGPU.md)
- [Astronaut RGB PNG](https://raw.githubusercontent.com/scikit-image/scikit-image/v0.26.0/src/skimage/data/astronaut.png), 512×512 NASA photograph with no known copyright restrictions, SHA-256 `88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5`. [Provenance](https://scikit-image.org/docs/0.26.x/api/skimage.data.html#skimage.data.astronaut)
- [Hubble eXtreme Deep Field JPEG](https://raw.githubusercontent.com/scikit-image/scikit-image/v0.26.0/src/skimage/data/hubble_deep_field.jpg), 1000×872 public-domain NASA photograph, SHA-256 `3a19c5dd8a927a9334bb1229a6d63711b1c0c767fb27e2286e7c84a3e2c2f5f4`. [Provenance](https://scikit-image.org/docs/0.26.x/api/skimage.data.html#skimage.data.hubble_deep_field)

## Isolated build used for the measurements

Install the three verified Halide wheels into `../packages`. Download the two images to this folder under the pinned filenames. Extract the verified Emscripten zip into `sdk` so the package has `sdk/install/bin` and `sdk/install/emscripten`. Write `emscripten.local` with Python-style assignments for `LLVM_ROOT` (absolute `sdk/install/bin`), `BINARYEN_ROOT` (absolute `sdk/install`) and `NODE_JS` (one-element list with the actual Node executable path). Use a fresh copy of the folder to preserve the measured evidence and to build the glue files with exclusive creation. The runner opens its own Chrome profile.

```powershell
$env:PYTHONPATH=(Resolve-Path ../packages).Path
$env:EM_CONFIG=(Resolve-Path emscripten.local).Path
$env:EM_CACHE=Join-Path (Get-Location).Path emscripten-cache
python -B generate_preview.py
python -B sdk/install/emscripten/em++.py -O2 preview_host.cpp gaussian-preview.a -I../packages/halide/include -sUSE_WEBGPU=1 -sASYNCIFY -sMODULARIZE=1 -sEXPORT_ES6=1 '-sEXPORTED_RUNTIME_METHODS=ccall,HEAPF32' -sENVIRONMENT=web -sALLOW_MEMORY_GROWTH=1 --no-entry -o preview_host.mjs
python -B patch_preview_glue.py preview_host.mjs preview_host_parking.mjs
python -B patch_preview_glue.py preview.mjs preview_parking.mjs --app
python -B run_parking_preview.py --out run-first --pairs 8 --frames 10 --timeout 45
python -B run_parking_preview.py --out run-trace --pairs 4 --frames 6 --trace --timeout 45
```

The stock and callback modes use the same Wasm binary `d7c2d3f620568ae48d25c365c35678bd80ded6ecb0195680d5117697fa65514d`. Only the tiny browser bridge varies. The primary benchmark includes an actual Gaussian parameter change through both Halide GPU passes, WebGPU buffer transfer into host Wasm memory, and synchronous canvas bitmap update. Image decode, one-time resident input upload, validation, hashing, compositor scheduling and display scanout are outside the window. The output is compared against a separate Float64 CPU reference at every pixel, and all equal-input variants must hash identically. Use trace results to diagnose causal waits and uninstrumented runs for claims about latency.

## Companion runs

The CPU mode performs the same Gaussian operation, but compiles a tiled, vectorized Halide CPU schedule and therefore requires no GPU readback. It runs as an independent Chrome session with an identical canvas boundary and asset so the GPU comparison does not imply which processing backend to choose for a small preview.

```powershell
python -B generate_cpu_preview.py
python -B sdk/install/emscripten/em++.py -O2 -msimd128 cpu_preview_host.cpp cpu-gaussian-preview.a -sMODULARIZE=1 -sEXPORT_ES6=1 '-sEXPORTED_RUNTIME_METHODS=HEAPF32' '-sENVIRONMENT=web,node' -sALLOW_MEMORY_GROWTH=1 --no-entry -o cpu_preview_host.mjs
python -B run_cpu_preview.py --out run-cpu --pairs 8 --frames 10 --timeout 45
```

The Laplacian-of-Gaussian case processes a different image with a 33-tap window, a larger output and a third GPU stage. It uses same-case CPU mathematical validation, both baseline modes and both callback modes. The source workload is based broadly on scale-space image preview. [scikit-image LoG example](https://scikit-image.org/docs/0.26.x/auto_examples/features_detection/plot_blob.html)

```powershell
python -B prepare_hubble_preview.py
Push-Location hubble_case
python -B ../generate_log_preview.py
python -B ../sdk/install/emscripten/em++.py -O2 preview_host.cpp log-preview.a -I../../packages/halide/include -sUSE_WEBGPU=1 -sASYNCIFY -sMODULARIZE=1 -sEXPORT_ES6=1 '-sEXPORTED_RUNTIME_METHODS=ccall,HEAPF32' -sENVIRONMENT=web -sALLOW_MEMORY_GROWTH=1 --no-entry -o preview_host.mjs
python -B patch_preview_glue.py preview_host.mjs preview_host_parking.mjs
python -B run_parking_preview.py --out run-first --pairs 8 --frames 6 --timeout 45
Pop-Location
```

Single-thread and six-thread CPU versions use the same 33 taps per dimension and scale-normalized derivative. The tiled SIMD schedule is identical. The threaded schedule parallelizes the outer row tiles and preallocates six browser workers. The loopback CPU page serves browser cross-origin isolation headers for WebAssembly shared memory. The tolerance `1e-4` covers amplification of Float32 summation rounding by the σ²-normalized derivative. The four GPU arms also have to match bit for bit.

```powershell
Push-Location hubble_case
python -B ../generate_cpu_log_preview.py
python -B ../sdk/install/emscripten/em++.py -O2 -msimd128 cpu_preview_host.cpp cpu-gaussian-preview.a -sMODULARIZE=1 -sEXPORT_ES6=1 '-sEXPORTED_RUNTIME_METHODS=HEAPF32' -sENVIRONMENT=web -sALLOW_MEMORY_GROWTH=1 --no-entry -o cpu_preview_host.mjs
python -B ../generate_cpu_log_preview.py --threads
python -B ../sdk/install/emscripten/em++.py -O2 -msimd128 -pthread -DCPU_PREVIEW_THREADS=6 cpu_preview_host.cpp cpu-gaussian-preview.a -sMODULARIZE=1 -sEXPORT_ES6=1 '-sEXPORTED_RUNTIME_METHODS=HEAPF32' '-sENVIRONMENT=web,worker' -sPTHREAD_POOL_SIZE=6 -sINITIAL_MEMORY=67108864 --no-entry -o cpu_preview_host_threaded.mjs
Pop-Location
python -B run_cpu_preview.py --log --out hubble_case/run-cpu-simd --pairs 8 --frames 6 --timeout 45
python -B run_cpu_preview.py --log --threads --out hubble_case/run-cpu-threaded --pairs 8 --frames 6 --timeout 45
```

All GPU runs use the normal Chrome WebGPU API on loopback. The reported results characterize these two isolated previews and the legacy Halide/browser bridge. The downstream CTest workload in the upstream issue, modern Emdawnwebgpu, worker/browser differences, native Dawn, scheduling under tab throttling, and broader application performance need their own measurements.

## Recoverable validation control

Build a separate test-only module with a Halide error handler that logs and permits a return code. The stock and callback variants in this run share the same module and handler. The injected dispatch requests an absent shader entry point and then restores the valid entry point to verify recovery.

```powershell
python -B sdk/install/emscripten/em++.py -O2 preview_host.cpp failure_handler.cpp gaussian-preview.a -I../packages/halide/include -sUSE_WEBGPU=1 -sASYNCIFY -sMODULARIZE=1 -sEXPORT_ES6=1 '-sEXPORTED_RUNTIME_METHODS=ccall,HEAPF32' -sENVIRONMENT=web -sALLOW_MEMORY_GROWTH=1 --no-entry -o preview_host_failures.mjs
python -B patch_preview_glue.py preview_host_failures.mjs preview_host_failures_parking.mjs
python -B patch_preview_glue.py preview.mjs preview_parking_failure.mjs --app --failure-probe
python -B run_parking_preview.py --out run-failure --pairs 4 --frames 3 --trace --failure-probe
node --test test_callback_parking.mjs
```
