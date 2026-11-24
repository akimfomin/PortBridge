# Repeated draw readback for Continued #511

This synthetic check compares immediate and deferred pipeline creation over 32 color-changing draws. It reuses the pixel-check method from SceneGate VI and runs against Continued's offscreen Vulkan D3D12 draw fixture. [SceneGate evidence](https://akimfomin.github.io/PortBridge/cases/pb-0021.html) · [Continued #511](https://github.com/ubiquitarianism/leonida/pull/511)

Use Continued commit `88658f1b3fcdca2231358c18d09253a213dc8533` in a separate checkout. Read the source and the project's test setup. On Windows with the project's C++ build tools and Vulkan SDK, apply [sequence.patch](sequence.patch), configure the normal runtime build, and build `d3d12_draw_test`. Set the patch path for your checkout. The example executable path follows the Visual Studio build layout. The sequence runs when `PORTBRIDGE_DRAW_SEQUENCE` is set. [Upstream test setup](https://github.com/ubiquitarianism/leonida/blob/88658f1b3fcdca2231358c18d09253a213dc8533/CONTRIBUTING.md) · [Upstream fixture](https://github.com/ubiquitarianism/leonida/blob/88658f1b3fcdca2231358c18d09253a213dc8533/runtime/test/d3d12_draw_test.cpp)

```powershell
$patch = 'C:\path\to\PortBridge\contrib\continued-repeated-draw\sequence.patch'
git apply --check $patch
git apply $patch
cmake -S runtime -B runtime/build
cmake --build runtime/build --config RelWithDebInfo --target d3d12_draw_test

$test = '.\runtime\build\RelWithDebInfo\d3d12_draw_test.exe'
$env:PORTBRIDGE_DRAW_SEQUENCE = '1'
foreach ($mode in @('0', '1')) {
    $env:LEONIDA_LAZY_PSO = $mode
    Remove-Item Env:\PORTBRIDGE_OMIT_SEQUENCE_DRAW -ErrorAction SilentlyContinue
    & $test
    if ($LASTEXITCODE -ne 0) { throw "Sequence did not pass with mode $mode" }
    $env:PORTBRIDGE_OMIT_SEQUENCE_DRAW = '1'
    & $test
    if ($LASTEXITCODE -ne 44) { throw "Omitted draw was not detected with mode $mode" }
}
Remove-Item Env:\PORTBRIDGE_DRAW_SEQUENCE, Env:\PORTBRIDGE_OMIT_SEQUENCE_DRAW, Env:\LEONIDA_LAZY_PSO
```

On each mode the sequence should report 32 frames of 4,096 matching RGBA8 pixels and green values 63–94. The control omits the eighth draw. It should report frame 7, pixel (0,0), expected RGBA `255,70,0,255` and observed `0,0,255,255`. A missing adapter or a skip is useful to report separately with the diagnostic.

PortBridge ran the fixture on Windows 11 build 28000 with RTX 4070 Ti SUPER driver 617.14 and LLVM-MinGW Clang 23.1.6. The sequence passed three times in each mode. All six omission controls failed at the expected pixel. The original fixture also passed both modes with the PortBridge option unset. The local build used a DirectX aggregate-return ABI adapter and an abort-on-use swapchain link stub to exercise the offscreen path. The normal project build on AMD hardware still needs a run.

If you repeat it, report the exact revision and patch, GPU, driver, OS, toolchain, both mode results and the omission control in [Continued #511](https://github.com/ubiquitarianism/leonida/pull/511).

The patch modifies the original Continued fixture and retains its upstream [GPL-3.0 license](COPYING).
