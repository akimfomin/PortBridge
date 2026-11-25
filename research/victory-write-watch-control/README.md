# Write-watch range grouping on native Windows

This standalone test measures the cost of querying eight memory ranges separately or through one enclosing `GetWriteWatch` query. It also checks what happens to dirty pages inside the gaps when that enclosing call resets the watch state. The test uses synthetic memory, the Windows API and one CPU. The timings apply to this native Windows API test. Proton, application frame time and GPU behavior would need separate measurements.

## Run

On Windows, use LLVM-MinGW's `clang++` and Python 3. The C++ executable writes one CSV row per timing batch. The reset check prints page counts and fails if any observed page set differs from the expected set.

```powershell
clang++ -std=c++20 -O2 -Wall -Wextra -Werror -static write_watch_control.cpp -o watch_control.exe
.\watch_control.exe | Set-Content -Encoding ascii latest.csv
python reset_gap_control.py
```

## Results

Collected on Windows 11 build 28000 with an Intel Core i5-13600KF on 25 November 2026. The program reserves 64 MiB with `MEM_WRITE_WATCH` and compares two sets of eight 4 MiB windows. The adjacent set covers 32 MiB under either strategy. For alternating windows the separate calls cover 32 MiB and one enclosing call covers 60 MiB. The sparse-write workload changes one 4 KiB page every 53 pages. Each result uses eight alternating-order pairs of 96 observations per arm. The C++ timing uses non-resetting queries to hold the page set constant.

| Native Windows workload | Eight calls, median µs | One call, median µs | Median paired change | Range across eight pairs |
| --- | ---: | ---: | ---: | ---: |
| Adjacent, clean | 32.791 | 15.637 | −52.40% | −53.50% to −51.48% |
| Adjacent, sparse writes | 42.580 | 25.263 | −39.70% | −42.62% to −39.05% |
| Gapped, clean | 33.642 | 29.596 | −13.90% | −16.83% to −9.59% |
| Gapped, sparse writes | 42.527 | 48.477 | +13.32% | +7.07% to +18.15% |

The dirty gapped arms agreed on all 155 selected pages. With the reset flag, eight separate queries left 135 dirty gap pages visible to a later query. The enclosing query returned all 290 dirty pages inside the span, including those 135 gap pages, and a later query found zero gap pages. Code that resets across gaps must record every returned page before limiting an individual consumer to its requested range. VIctory Fork already does this in the referenced journal code. [Windows API](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-getwritewatch), [VIctory Fork journal at `9376fd6`](https://github.com/fxceless/victory-fork/blob/9376fd60c0ba0e76a74c39b49b1407dbac0a64c7/crates/victory-gpu/src/watch.rs#L274-L311).

Use [raw CSV observations](write_watch_control.csv) and [paired summary](write_watch_control.json) to recompute the table. Each arm's time divides `total_ns` by `repeats` before finding its median. Paired changes compare the enclosing and separate arm in each round. The reset proof has a [separate output](reset_gap_control.txt).

## Why this test

[VIctory Fork #10](https://github.com/fxceless/victory-fork/issues/10) reports that on Proton, asking about fewer bytes while making more calls did not improve the observed write-watch time. The [later repeatability check](https://github.com/fxceless/victory-fork/issues/10#issuecomment-7156790682) also found large run-to-run differences. These controls isolate range geometry and reset semantics on one native Windows allocation. A matched Proton comparison could vary both the per-shadow enclosing ranges and the cross-shadow grouping limit while preserving the production journal and measuring calls, bytes, returned pages and tail latency. [Per-shadow grouping](https://github.com/fxceless/victory-fork/blob/9376fd60c0ba0e76a74c39b49b1407dbac0a64c7/crates/victory-gpu/src/host.rs#L4604-L4621), [cross-shadow grouping](https://github.com/fxceless/victory-fork/blob/9376fd60c0ba0e76a74c39b49b1407dbac0a64c7/crates/victory-gpu/src/watch.rs#L83-L132).

The original test code and generated observations in this directory are distributed under the [MIT License](LICENSE).
