# XCL #2080. Reduce scratch transfer between dispatches

Kalmarv's split compiler in [XCL #2080](https://github.com/xcl-dev/xcl/pull/2080) moves live shader values through a scratch UAV between Direct3D dispatches. The author measured substantial driver compile-time gains with the split. Their selected large example moves about 30 MB per dispatch on the longer path. This follow-up tests two ways to reduce the cost of that handoff. It uses generated data and independent HLSL programs. No title bytes or closed SDKs are in the tests.

| Control | Workgroup geometry | Earlier layout | Candidate | Paired outcomes faster / equal / slower |
| --- | --- | ---: | ---: | ---: |
| Two dispatches, vectorize memory operations | 32 threads, 32×4×3 groups | 4.096 µs | 4.096 µs | 11 / 20 / 1 |
| Two dispatches, vectorize memory operations | 64 threads, 64×4×8 groups | 24.576 µs | 24.576 µs | 12 / 13 / 7 |
| Three dispatches, retain 16 common words | 32 threads, 32×4×3 groups | 7.168 µs | 6.144 µs | 31 / 1 / 0 |
| Three dispatches, retain 16 common words | 64 threads, 64×4×8 groups | 47.104 µs | 32.768 µs | 31 / 0 / 1 |

Each row gives the two raw GPU interval medians from four separate RTX 4070 Ti SUPER processes and 32 balanced measured pairs. An unmeasured first pair per process warmed each pair of programs. The two large timing sets both retain a slow scalar-arm outlier. The hardware runs matched **110,592** and **1,179,648** expected per-lane output digests for each arm and process. The 64-thread shape used two physical wave32s. The intervals include the synthetic dispatches and their intervening UAV barriers. PSO build time, hardware Wave64, retail shaders, frame time and the XCL integration are outside this measurement. [D3D12 timestamp semantics](https://learn.microsoft.com/en-us/windows/win32/direct3d12/timing) · [Vector timing](native-a/transport-summary.json) · [Retention timing](native-retain/transport-summary.json)

## Vector operation control

The layout groups payload dwords in groups of four per lane. All crossing edges use the same width per tile to prevent different edges in a group from aliasing. The CPU proof checked 5,444 patterns and caught a deliberately wrong spacing rule. DXIL validation accepted all eight generated modules. The send and receive transport operations decreased from 39 to 11 in the generated HLSL comparison. The logical transfer size stayed the same. The equal GPU medians make this candidate a lower priority for performance. [Source experiment](fixed-layout/xcl-2080-scratch-tiles.patch) · [DXIL validation](native-a/validation.json)

## Retain words that all crossing edges carry

The second candidate assigns fixed scratch slots only to scalar values defined in the first piece and live on every crossing edge. Later pieces never resend those values. They load a retained value only if an original instruction in that piece uses it. Dynamic per-edge data starts after the shared prefix. The tag and maximum allocation stay unchanged. The synthetic intermediate shader changed from 24 loads and 36 stores to 8 loads and 20 stores. A lane that takes the intermediate edge avoids 128 requested scratch bytes. The larger fixture avoided 5,592,320–5,592,448 logical bytes each complete launch, depending on the synthetic seed. It uses hand-written shaders for both arms. The actual author's graph may have a different set of eligible values. [Source candidate and extracted selection checks](../portbridge-xcl-stable-scratch/README.md) · [Twelve validated modules](native-retain/validation.json) · [Independent graph oracle](../portbridge-xcl-stable-scratch-proof/README.md)

## Reproduce

Keep the adjacent `portbridge-victory-dirty-tile-upload` source folder. The driver worker reuses its adapter, fence and buffer helpers and the MIT Windows Job guard. Use Windows x64, directx shader compiler and validator, Python 3 and LLVM-MinGW. Select a new output directory for a rebuild.

```powershell
python -I -B .\prove_layout.py
python -I -B .\make_programs.py --dxc C:\dxc\dxc.exe --dxv C:\dxc\dxv.exe .\rebuild-vector
clang++ -std=c++20 -O2 -static -municode -Wall -Wextra -Werror -Irebuild-vector .\native-transport.cpp -ld3d12 -ldxgi -lpsapi -o .\rebuild-vector\transport.exe
python -I -B .\make_programs.py --sticky --dxc C:\dxc\dxc.exe --dxv C:\dxc\dxv.exe .\rebuild-retained
clang++ -std=c++20 -O2 -static -municode -Wall -Wextra -Werror -DPORTBRIDGE_STICKY=1 -Irebuild-retained .\native-transport.cpp -ld3d12 -ldxgi -lpsapi -o .\rebuild-retained\transport.exe
.\rebuild-retained\transport.exe --hardware-transport > .\rebuild-retained\rtx-a.csv
python -I -B .\analyze_transport.py .\rebuild-retained
```

The optional worker refuses entry below 4 GiB available system commit and 6 GiB physical memory. It is capped at 512 MiB and three seconds and looks for the exact RTX model. One planned vector cohort was stopped before spawning. Debug-layer reports were unavailable. The test needs no interactive window or alteration of GPU settings. The XCL patches and Rust checks retain XCL's GPL-2.0 terms. The adapted D3D12 harness and adjacent texture fixture retain GPL-3.0-or-later. HLSL and the guard carry their indicated MIT terms.
