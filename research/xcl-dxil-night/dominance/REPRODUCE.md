# Reproduce the XCL graph experiments

The original, V1, compact and PHI workloads use the XCL commit `20cf13022f764208384c610c2ae6a3f4eed201a2`. Run the build commands from isolated checkouts. The data files describe exact inputs and per-process samples. The standalone XCL patches and fixtures use the same GPL-2.0-only license as the original optimizer.

## Build variants

1. Make a separate baseline worktree and one for each candidate from the pinned XCL revision. Apply [V1](xcl-dominance.patch) or [compact](xcl-dominance-compact.patch) to the corresponding candidate and leave the baseline at the pinned source. The PHI variant uses [the previous PHI research patch](https://github.com/akimfomin/PortBridge/blob/edfee7f248c2336eb139885d2b36c4c5589040f4/research/xcl-phi-worklist/xcl-phi-worklist.patch). The combined variant uses both, with the same dominator call substituted inside the PHI optimizer.
2. Copy [portbridge_cfg_compile.rs](portbridge_cfg_compile.rs) and [portbridge_campaign_compile.rs](portbridge_campaign_compile.rs) into each `crates/xcl/tests` folder. Copy [campaign_gen.rs](campaign_gen.rs) into each `crates/xcl/tests/portbridge_night/`. This generator is unmodified BetterJdue source from [XCL #1763 at e3806688](https://github.com/xcl-dev/xcl/blob/e3806688e4d9e4fb4be9f49369fe8f5b184f8b6c/crates/xcl/tests/compile_bench/gen.rs).
3. In each worktree set `CARGO_PROFILE_RELEASE_DEBUG=0` and run `cargo test --release --locked -p xcl --test portbridge_cfg_compile --test portbridge_campaign_compile --no-run`. Copy the resulting executables to distinct names in this proof directory. If sharing Cargo's target directory, force a rebuild on each switch and inspect the absolute source path in each build log. Keep outputs separate.

The original run used Windows, Rust 1.100.0 gnullvm with LLVM-MinGW, an Intel i5-13600KF and DXC 1.9.2602.17. [XCL build rules](https://github.com/xcl-dev/xcl/blob/main/CONTRIBUTING.md)

## Translate and compare

```powershell
python -I run_cfg_compare.py --baseline BASE_CFG_EXE --candidate COMPACT_CFG_EXE --dxc DXC_BIN_DIR --result cfg-native-compact-results.json
python -I run_campaign_matrix.py --variants baseline compact --dxc DXC_BIN_DIR --result campaign-compact-results.json
```

The campaign runner expects names `campaign-baseline.exe`, `campaign-dominators.exe`, `campaign-phi.exe`, `campaign-combined.exe` and `campaign-compact.exe` for the arms selected. A separate validation round calls DXC on every arm before the timed runs. Compilation variants stay in separate processes. Keep other heavy processes and GPU measurements idle.

To run the independent graph oracle compile [dom_graphs.rs](dom_graphs.rs) with `rustc --edition=2021 -C opt-level=3` and the platform linker. The plain executable includes the V1 production source from its worktree. Add `--cfg 'feature="compact_dominators"'` to include [dom_compact.rs](dom_compact.rs) instead. Run without arguments for correctness, or give a shape and number of repeated subgraphs, for example `comb 8192`. The `track_allocations` feature adds [dom_alloc.rs](dom_alloc.rs) and reports peak requested bytes and allocation calls without claiming process memory or timings.
