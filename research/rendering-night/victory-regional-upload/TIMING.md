# D3D12 queue timestamps for partial texture uploads

The original 512×512 four-byte RGBA8 fixture showed equal full readbacks and a smaller submitted copy. This extension generates boxes for four changed-tile patterns from the same CPU planner and adds timestamps directly around the texture copies on the direct queue. It compares two identical initialized resources and uses an independently computed expected image for each pattern.

| Changed tiles | Boxes | Submitted bytes in regional arm | Whole-copy median | Regional-copy median |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1 | 65,536 | 25.648 µs | 2.080 µs |
| 4 adjacent | 1 | 262,144 | 24.256 µs | 5.616 µs |
| 4 separated | 4 | 262,144 | 24.400 µs | 5.728 µs |
| 8 separated | 8 | 524,288 | 24.640 µs | 10.176 µs |

The whole-copy arm always submits 1,048,576 bytes. Four fresh RTX 4070 Ti SUPER workers provided 48 measured pairs per row. Each worker first ran an unmeasured pair, then alternated which arm went first. At the end of each pattern, all 1,048,576 bytes in both resources matched the independent expected image. The direct queue reported a 1 GHz frequency. In the one-tile case, the four separate medians ranged from 21.680 to 30.800 µs for the whole copy and 2.064 to 2.192 µs for one region. One additional launch was refused before opening a device because of system commit headroom. All four launched workers were reaped. A 501.600 µs regional interval in the four-separated case is retained. The regional arm was faster in 47 of 48 pairs in that case and in all 48 pairs for each other shape. Peak job commit was 107,122,688 B. [Raw timing data](timestamp-rtx-a.csv) · [Second complete process](timestamp-rtx-c.csv) · [Third](timestamp-rtx-d.csv) · [Fourth](timestamp-rtx-e.csv) · [Refusal](timestamp-rtx-b.csv) · [Summary](timestamp-summary.json)

Each timed interval is a warmed, repeated GPU copy on the already allocated fixtures. Timestamp queries have their own overhead. Actual submission, detiling, staging writes, synchronization across frames, and an application's frame time are outside this measurement. Use the results to choose candidate shapes for an integrated comparison. [D3D12 timing](https://learn.microsoft.com/en-us/windows/win32/direct3d12/timing)

## Reproduce

Use the original fixture directory and the toolchain from [README.md](README.md). The recorded cases are in `timing-cases.inc`. Generate them with `emit_timing_cases.rs` and check the four positions and sizes before using a fresh build. Rust may need an explicit linker on a GNU Windows toolchain.

```powershell
rustc --edition=2024 -C opt-level=2 -D warnings .\emit_timing_cases.rs -o .\emit-timing-cases.exe
.\emit-timing-cases.exe | Set-Content -Encoding ascii .\generated-timing-cases.inc
clang++ -std=c++20 -O2 -static -municode -Wall -Wextra -Werror .\timestamp-upload.cpp -ld3d12 -ldxgi -lpsapi -o .\timestamp-upload.exe
.\timestamp-upload.exe --hardware-timing > .\timestamp-rtx-f.csv
python -I -B .\analyze_timing.py
```

The worker retains the 512 MiB, three-second guard and admission checks. Only this adapter is accepted. Wait for a suitable system window and run a single worker at a time.
