# Bounded graph analysis in XCL direct DXIL

The existing repeated immediate-dominator intersections can revisit long unrelated paths for each join. The draft uses simple Lengauer–Tarjan in both CFG reducibility and module CSE, then answers ancestry in constant time. It skips reducibility analysis for acyclic graphs and avoids allocating successor lists during basic-block traversal. The compact version reuses storage by phase. [Original algorithm](https://doi.org/10.1145/357062.357071)

## Observations

The source revision was `20cf13022f764208384c610c2ae6a3f4eed201a2`. The patch also applied cleanly at `80f4819098e921f2e1ab371144d4832f68ffedd6`, where the recent cache/CSE work modifies nearby code. All workloads used source-generated inputs. No game data or retail run was involved. [Maintainer shader campaign](https://github.com/xcl-dev/xcl/issues/1269) · [Nearby #1836](https://github.com/xcl-dev/xcl/pull/1836)

| Full XCL route | Base | Compact |
| --- | ---: | ---: |
| 7,167 RDNA2 instructions, long paths with cross-branch joins | 21.764 ms | 14.924 ms |
| 4,097 RDNA2 instructions, 1,024 loops | 19.449 ms | 14.065 ms |
| 5,121 RDNA2 instructions, diamonds | 12.479 ms | 11.612 ms |
| 223 RDNA2 instructions, short join control | 0.831 ms | 0.835 ms |

The raw graph-only test with 49,153 vertices took about 911 ms in the original traversal and 3.28 ms in the first implementation. In the isolated compact test with 24,577 vertices, peak requested heap bytes were 2,646,113 compared with 2,777,137 in the original comparison and 3,735,584 in the first implementation. These cover the graph pass and its allocations. [First graph timings](dom-graphs-initial.log) · [Compact allocation measurements](dom-memory-compact.log)

The nine complete outputs were byte-identical and passed DXC validation. On an independent set of 24 programs from BetterJdue's proposed #1763 generator, the compact median relative change was −1.12% and individual median changes ranged from −3.80% to +5.31%. All outputs remained byte-identical there, too. This set does not show a consistent large translation improvement. [Native results](cfg-native-compact-results.json) · [Independent corpus results](campaign-compact-results.json) · [Original generator](https://github.com/xcl-dev/xcl/blob/e3806688e4d9e4fb4be9f49369fe8f5b184f8b6c/crates/xcl/tests/compile_bench/gen.rs)

An independent vertex-removal oracle matched the graph trees for 65,536 exhaustive four-vertex graphs and 10,000 seeded graphs, including repeated edges and unreachable vertices. The exact candidate library passed 923 ordinary tests, with 25 ignored and platform-specific runtime skips. The separate fuzz groups validated all 2,000 generated shader containers and compared 1,232 results with the CPU oracle on RTX 4070 Ti SUPER. Native Wave64/AMD and runtime game workloads remain open.

The candidate changes compiler cost while preserving shader bytes in the checked arms. To prioritize integration, profiles with the number of CFG vertices, join depth and CPU translation time would show whether the synthetic tail occurs in other workloads. [Compact patch](xcl-dominance-compact.patch) · [Reproduction](REPRODUCE.md)

## Confirmatory rerun

The same 24 fixed fixtures were rerun in 40 matched process rounds. The compact patch used 1.78% less translation time on the fixed corpus. Resampling process pairs gave a 95% interval of 1.33–2.22% improvement for these repeats. All output bytes remained exact. [Data and method](CONFIRMATORY.md)
