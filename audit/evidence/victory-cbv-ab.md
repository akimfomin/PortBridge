# VIctory CBV snapshot reuse · a matched gameplay comparison

## What is known

Zignixx measured the Series S prologue at about 39 ms per frame on RTX 5080 in the tested stack, down from 77.7 ms. LeonardoS11 measured a separate build comparison on an RTX 3080 Ti in the same opening scene. The two runs attributed to nvidia-wip were 64–73 ms with 0.6667 and 60–75 ms with the variable unset. Zignixx noted that the latter run may still have used the Series S internal resolution. LeonardoS11 corrected the window-screen report after examining a reference. None of those measurements toggled CBV snapshot reuse. [RTX 5080 breakdown](https://github.com/fxceless/victory-fork/issues/1379) · [RTX 3080 Ti runs](https://github.com/fxceless/victory-fork/issues/1379#issuecomment-7203857811) · [Picture correction](https://github.com/fxceless/victory-fork/issues/1379#issuecomment-7203875083) · [Scale caveat and current branch](https://github.com/fxceless/victory-fork/issues/1379#issuecomment-7204175309)

ByFxbian's PR reports a native RTX 3070 synthetic benchmark: median preparation/enqueue time goes from 15.131 to 0.135 ms with 64 distinct sources and from 14.890 to 14.990 ms with 22,000. The all-unique recording time rises from 36.288 to 40.761 ms. A different contributor measured a test-build problem with #860 and reported 290 passing tests after adjusting the old helper call. Those results do not establish a frame-time gain in the opening scene. [ByFxbian's numbers](https://github.com/fxceless/victory-fork/pull/1316) · [#860 compatibility note](https://github.com/fxceless/victory-fork/pull/1316#issuecomment-7204026080)

## PortBridge compatibility check

| Input | Exact revision |
| --- | --- |
| Zignixx nvidia-wip | [`90fe3144a4c5fe8ca4e6ce1b5f0e42f4fb28696b`](https://github.com/Zignixx/VIctory-7900XTX/commit/90fe3144a4c5fe8ca4e6ce1b5f0e42f4fb28696b) |
| ByFxbian #1316 | [`c5b08986a571f4befb6806ca94b8ab7ce8c58dba`](https://github.com/fxceless/victory-fork/pull/1316/commits/c5b08986a571f4befb6806ca94b8ab7ce8c58dba) |
| Baseline used to isolate the #1316 delta | [`58de9bf4c367d4e27f6dd5da523ca2f68951bc77`](https://github.com/fxceless/victory-fork/commit/58de9bf4c367d4e27f6dd5da523ca2f68951bc77) |
| #860 checked | [`4594ddb102b2c8ed1c3f2557dbe22d8e9cfc88a8`](https://github.com/fxceless/victory-fork/pull/860/commits/4594ddb102b2c8ed1c3f2557dbe22d8e9cfc88a8) |

`git grep -F VICTORY_CBV_SNAPSHOT_REUSE <nvidia> -- crates/victory-gpu` returned no match. Using #1316's baseline as the explicit comparison base, `git merge-tree --write-tree --name-only --merge-base=<baseline> <nvidia> <pr>` returned content conflicts in `copystat.rs`, `draw.rs`, `host.rs` and `list.rs`. This is a check of applying the #1316 delta, without assuming the projects' histories share that commit. No nvidia-wip overlay was built or run. Any future port needs to preserve invalidation on writes/copies, list-cut lifetime and the pending GPU-write fallback. The #860 note is separate from these four conflicts.

## One optional run for a participant with a lawful working test setup

1. The executable must include #1316. The quickest baseline is its exact PR head above, with the diagnostic build already described by its contributors. An nvidia-wip comparison requires a separately verified and pinned integration of the delta. Record which executable was used. An experiment on #1316's own head answers the reuse and cost question on that build.
2. Use the same title revision, existing local save, camera or repeatable route, GPU/driver, console profile, actual internal render size, upscaler, ray-tracing and other switches, executable and warmed cache. If comparing with the Series S 720p data, verify the internal size independently. Record the settings once. Keep the reports to permitted aggregates. Do not share a save, title files or images.
3. Use six fresh processes, alternating OFF/ON/OFF/ON/OFF/ON. Set only `VICTORY_CBV_SNAPSHOT_REUSE` to `0` or `1`. The switch is read once per process. After the same warmup, record the same 90-second window in the same scene. Record median and p95 frame time, 1% low, visible artifacts/crashes and draw counts to check for equivalent rendering. Verify that no compiles are active during the window.
4. Keep only the measured window from a single PresentMon process and swap chain per CSV. For each ON run, place the matching `.log` next to its `.csv`. Keep only complete diagnostic intervals inside the window. The source emits hits, misses, avoided bytes and invalidations per report with reuse enabled. Share `hits/(hits+misses)` for eligible lookups and the counts. OFF has no corresponding line. A missing ON line leaves activation unverified.
5. Run the following locally. Post only the aggregate output, build SHA, settings and a short description of whether the picture looked the same. Any performance result with dropped draws or altered picture needs separate investigation.

```sh
python -B audit/cbv_ab.py off1.csv on1.csv off2.csv on2.csv off3.csv on3.csv
```

PortBridge validated the summarizer against known synthetic frame times and counters, including the failure with missing ON diagnostics. This host had no verified lawful working setup for the requested scene. The compatibility check and measurements above come from public source or named contributors. [Diagnostic code](https://github.com/fxceless/victory-fork/blob/c5b08986a571f4befb6806ca94b8ab7ce8c58dba/crates/victory-gpu/src/host.rs#L9168-L9182) · [Summarizer](../cbv_ab.py) · [PresentMon column definitions](https://github.com/GameTechDev/PresentMon/blob/main/README-ConsoleApplication.md#csv-columns)
