# Optional positive-only typed sampling check

This standalone Windows fixture creates four 1×1 synthetic textures. It uses their own typed formats in the resource and its SRV, checks feature-level 12.0 Texture2D and shader sampling support first, then reads back a four-value compute sample using the compositor’s linear filter. The three prohibited baseline format/view pairs appear only in `run_cpu.py`. The native fixture tests filtered sampling. Composition, swap-chain presentation and title behavior are outside this fixture.

Build with DXC, Python and a Windows-targeting Clang with the Windows/DXGI/D3D12 SDK or compatible headers and libraries:

```text
dxc -WX -T cs_6_0 -E main -Fo native-typed-srv.dxil native-typed-srv.hlsl
python embed_shader.py native-typed-srv.dxil native-typed-srv.inc
clang++ -std=c++20 -O2 -fms-extensions -municode -static native-typed-srv.cpp -o native-typed-srv.exe -ld3d12 -ldxgi -ldxguid -lpsapi
./native-typed-srv.exe --cpu-oracle
```

The source builds and the CPU oracle passes. The `--hardware` mode selects an explicit RTX 4070 Ti SUPER, uses the included 512 MiB / three-second worker guard and returns 77 if the format support gate cannot verify all four formats. The locally built executable and compiled shader are identified by SHA-256. The package contains their source.

| Built file | SHA-256 |
| --- | --- |
| `native-typed-srv.dxil` | `f131237ee45bbd727c28adf711109d847800bcf3f9f09eaac025ddafb75ba8f8` |
| `native-typed-srv.exe` | `ece33b88f8c4d80225e8e5e1fa59f0c0c66fe87a8543819a32e75c03fc1bb024` |

## Single guarded run

The four capability gates passed, the worker completed with device status `S_OK`, and the guard reaped it at a 100,835,328-byte peak. The debug layer was unavailable. All 12 float32 words for formats 28, 11 and 13 exactly match their CPU references.

The fourth format, `R8G8B8A8_SNORM` (31), returned `[-0.5039216280, 0.2519608140, 1.0, 0.5039521456]`. The largest deviation from the ideal normalized value is approximately `1.538e-5`, above the fixture's predeclared `2e-6` tolerance. The parent validator returned `1`. All four words round back to the original signed 8-bit components when scaled by 127. This is an additional observation about the recorded output. The numerical run did not pass the original criterion. [Raw result](native-hardware.txt)

Direct3D 11.3 functional specification §7.18.16.2 describes source-format precision for fixed-point texture filtering. For SNORM8 the spacing between the non-endpoint code points is `1/127`. The observed maximum difference is about `0.002` of that step. This comparison uses the D3D11 text as context. It does not establish a Direct3D 12 per-sample floating-point tolerance or a driver conformance result. [Microsoft's functional specification](https://microsoft.github.io/DirectX-Specs/d3d/archive/D3D11_3_FunctionalSpec.htm) · [Recorded-word analysis](native-analysis.txt)

Run `python analyze_native.py` from this folder to reproduce the offline comparison of the captured words and exact-float references.
