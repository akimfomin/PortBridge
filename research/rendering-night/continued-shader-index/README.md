# Continued shader index. Retain one JSON entry at a time

OreoFR traced a distinct first-use delay in Continued #1308 to loading a shader catalog with 29,187 entries. This experiment addresses the loader's temporary memory and parsing work on public main `871e4b8b990bb9424c6f3c06175259d1a548239c`. The separate work by Kadamitas in #1108 removes recursive subtree copies. Sodove's #1218 reads the file in blocks and handles read errors. The new change composes with both. [First-use measurement](https://github.com/ubiquitarianism/leonida/pull/1308#issuecomment-7148830079) · [Coordination claim](https://github.com/ubiquitarianism/leonida/issues/14#issuecomment-7150216093) · [#1108](https://github.com/ubiquitarianism/leonida/pull/1108) · [#1218](https://github.com/ubiquitarianism/leonida/pull/1218)

The main file still reads into a text buffer. The existing JSON parser visits its complete top-level entries one at a time. It stages only the lookup records until the whole document succeeds. Duplicate names and hashes retain original order. A malformed main load retains the previous library. The existing optional-index parse and load behavior remains in use.

## Repeated native CPU results

Windows 11 on Intel Core i5-13600KF, LLVM-MinGW Clang, C++20, `-O2`. Each variant had one warm-up per file and eight balanced rounds in fresh processes with ordinary filesystem caching. Timing covers the exact public `ShaderLibrary::load()` call. The independent test checks every expected record afterwards. Peak commit and working set are whole-process Windows counters sampled immediately after the call, before the record checks. All data is generated metadata.

| Input | Main → one entry at a time | #1108 + #1218 → also one entry at a time |
| --- | ---: | ---: |
| 64 rows, 42 KB | 1.01 → 0.93 ms | 0.77 → 0.59 ms |
| 8,000 rows, 10.4 MB | 149.25 → 103.09 ms | 84.12 → 60.90 ms |
| 29,187 rows, 57.4 MB | 808.83 → 559.31 ms | 419.52 → 317.39 ms |
| Large input peak process commit | 458.76 → 154.72 MB | 499.34 → 103.84 MB |
| Large input peak working set | 412.73 → 113.32 MB | 488.80 → 99.11 MB |

The stock branch and the branch with both pending improvements are separate baselines. Timing includes the data read and real index construction. File shape and processor affect the magnitude. Real title startup, gameplay, GPU performance and other platforms are outside this test. [All samples](load-paired-final.json)

The repository's native shader-library executable passed in all four source variants. Additional synthetic checks covered UTF-8 BOM, repeated root names and digest order, appending matches from two optional index routes, processing non-object members, rejecting trailing data, preserving the previously loaded state on malformed main input, discarding a malformed optional index after a valid row, and replacing the catalog with a new or empty valid one.

## Reproduce

Use two copies of exact main at the revision above and two copies with #1108 and #1218 applied in that order. Apply [the standalone patch](continued-load-index-one-entry-871e4b8.patch) to one copy of each pair. Name the four directories `baseline`, `candidate`, `combined`, and `combined-stream`.

```powershell
python -I -B index_fixture.py cases
foreach($variant in @('baseline','candidate','combined','combined-stream')) {
    $headers = Join-Path $variant 'runtime/src'
    & clang++ -std=c++20 -O2 -static -municode "-I$headers" load_probe.cpp -o "$variant-load.exe" -lpsapi
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    & ".\$variant-load.exe" checks cases/controls
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
}
python -I -B measure_index.py cases load-paired.json
```

The runner checks for at least 3 GiB free system commit and 6 GiB usable RAM. [Windows memory counters](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-performance_information)
