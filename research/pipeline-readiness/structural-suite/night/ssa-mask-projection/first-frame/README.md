# First verified raylib image through the XCL runtime

The ordinary XCL pixel entry point and a single D3D12 draw produced the same 800 × 450 RGBA32F image in all six fresh renderer processes. The projected shader saved 120.0, 110.6 and 99.2 ms from the launch of the translation worker to verification of all 360,000 pixels. This uses the original raylib raymarching scene, its first camera, guest wave64 and four generic memory windows on an i5-13600KF and RTX 4070 Ti SUPER with driver 617.14. [Original shader by Inigo Quilez](https://github.com/raysan5/raylib/blob/7aeef5775435ed9f57890bf3c1b53279f6b0866a/examples/shaders/resources/shaders/glsl330/raymarching.fs)

| Median over three runs per mode | Whole | Equivalent SSA projection |
| --- | ---: | ---: |
| XCL `console_to_dxil_in` | 57.3 ms | 52.1 ms |
| D3D12 graphics PSO creation | 855.4 ms | 750.8 ms |
| Render setup, creation, one draw, fence and CPU readback | 898.0 ms | 791.3 ms |
| Translation worker launch through verified image on disk | 1,305.1 ms | 1,194.5 ms |
| Renderer process peak commit from the Windows job | 220.2 MiB | 209.0 MiB |

Each sample used a new translation process and a new guarded rendering process. The launch order was whole/project, project/whole, whole/project. Each pair began with an empty XCL translated cache. The first worker supplied a legally generated shader container to XCL, validated the resulting DXIL and wrote it to disk. The controller checked the exact DXIL digest before passing it to the second worker. The renderer prepared the common vertex shader, disabled both implicit D3D12 shader cache kinds for its device, created a fresh graphics PSO, drew once, waited on its fence and wrote one readback. The observer measured native creation with a timer nested inside the render interval. The outer wall timer includes both process launches, transfer through disk, renderer shutdown and the final image hash. It ends after the readback has returned to the controller. Presentation and interactive application startup lie outside these timings. This comparison measures a pair of coupled test processes. [Microsoft shader cache control](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device9-shadercachecontrol)

The shader bytecode from ordinary XCL matched both offline reference digests. The six images matched each other and the previously captured whole-shader reference, SHA-256 `3bdf7492ada35017f67fd89c256cb994251a249a5a567d225b177f06cbfc36ae`. That native D3D12 reference has a separately rendered original OpenGL comparison. [Original scene controls and cross-API comparison](../../open-scenes/ray800-primary/scene.json)

An earlier renderer was stopped by the guard when other activity consumed system commit. It did not produce a frame and contributes no observation to the table. The six accepted workers exited successfully within a 512 MiB Windows job. In eight additional CPU-only processes, both variants correctly reused their own translated cache on subsequent runs. The four warm API calls took 1.81–2.09 ms. [Initial qualified pair](measurements/first-cold-pair.json) · [Two counterbalanced pairs](measurements/counterbalanced-cold-pairs.json) · [Excluded attempt](measurements/incomplete-guarded-attempt.json) · [CPU cache hits](measurements/two-cpu-pairs.json)

## Verify the recorded experiment

From this directory, `python verify_results.py` checks the six receipts against their worker logs, per-mode bytecode, prior framebuffer digest and cache state. It recomputes the three paired differences and the table medians. With the original raw captures present, add `--raw-dirs <initial-pair-directory> <two-counterbalanced-pairs-directory>` to rehash all six full float images. To run the updated translator without copying any XCL sources, add `--runtime <pinned-runtime_pixel_routed.exe> --dxc-dir <DXC-directory>`. This optional run checks the binary against the separately recorded observer hash and passes the included synthetic container through both normal XCL modes in fresh processes. Both outputs from the reviewed `0c8a01c` matched the DXIL used for all six physical draws. The original GPU timings remain attributed to `5ea2b96`. [Results of the verified replay](measurements/reviewed-runtime-replay.json)

## Reproduce

The public XCL base is `08db8020d323bf478964fcc586152cce54959cfc`. These physical runs used local XCL `5ea2b9693158e92f3caab1631829e153abd564e8`. The reviewed follow-up `0c8a01c` keeps the offline reference independent of the switch. A repeat should record its actual revision and tool hashes. [Runtime and compiler patches](../README.md)

1. Apply the documented XCL projection and runtime patches. Copy [timed_runtime.rs](timed_runtime.rs) to `crates/xcl/examples/timed_runtime.rs` and build it with `cargo build --release --locked -p xcl --example timed_runtime`. It records the time inside XCL separately from shader validation and disk I/O.
2. Run the CPU comparison from this directory. The pinned [fixture](fixture/raylib-synthetic.dxbc) contains open AMD PAL shader output and independently generated format metadata. The 512-byte scalar table fixes the public camera and time. They can be regenerated via the [raylib preparation](../../open-scenes/prepare_raylib.py) and [synthetic wrapping](../runtime/wrap_fixture.py). The [upstream shader notice](fixture/RAYMARCHING-LICENSE.txt) accompanies its compiled derivative.

```powershell
python first_image.py --runtime PATH/timed_runtime.exe --fixture fixture/raylib-synthetic.dxbc --fixture-sha256 959c3b32bb9f4c78bcc1356baa938b0b9ad8675772389939e3016d105842acc6 --census ../corpus.json.gz --scene fixture/scene.json --dxc-dir PATH/TO/DXC --xcl-revision YOUR_REVISION --out NEW_CPU_DIRECTORY --pairs 2 --cpu-only
```

3. Build the [open scene renderer](../../open-scenes/README.md) with its current opt-in PSO blob capture. Build the existing [Windows test guard](../../../../guarded-test.cpp) with support for the 512 MiB worker option. The [small-job guard change](guard-512.patch) applies to PortBridge revisions that only implement its original two-GiB worker. For physical runs, replace `--cpu-only` with `--renderer PATH/open-scene-test.exe --guard PATH/bounded-test.exe --cache cold` and choose a fresh output directory. Use `--first-mode project` to invert the order. Multiple pairs alternate automatically. The measured renderer used the source changes at the open scene and MiniEngine patches in PortBridge `4fe517d`. The render log must contain exactly one successful test and its PSO timing, with no repeated GPU timing or blob request. [Scene renderer patch](../../open-scenes/open-scene-draw.patch) · [Final fixture options](../../open-scenes/mini-display-draw.patch)

The supplied scene fixes the reference pixels recorded on this NVIDIA driver. An independently reproduced original output on a different adapter can be supplied through a fresh scene receipt with that adapter's own baseline hash. Include the adapter, driver and original-shader comparison when reporting a new platform. A match to a locally generated reference establishes agreement on that platform.

The receipt records peak renderer process memory. It cannot establish driver-wide shader memory savings or the size of a native executable. The observed first-image improvement covers one camera and host. Cross-vendor and title-level measurements remain open.
