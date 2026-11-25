# Simplifying live one-seed PHI cycles in XCL

The plain trivial-PHI fold leaves two or more PHIs that refer back to one another and agree on the one value entering the cycle. This prototype recognizes the strongly connected group and folds it when a single value dominates every member's block or is an approved constant. The original behavior remains for no seed, multiple seeds, undefined values and unsupported cases. The graph walk is iterative. [Reference algorithm](https://pp.ipd.kit.edu/uploads/publikationen/braun13cc.pdf)

## Exact source frontend A/B

The same release XCL `20cf13022f764208384c610c2ae6a3f4eed201a2` executable compiled six independent source-generated RDNA2 records with only `XCL_DXIL_NO_OPT=phi-scc` toggled for the control. All 12 outputs passed Microsoft DXC validation. Each two-seed control preserved the exact bytes. [Proof data](frontend-results.json)

| One-input rotation | Before → after PHIs | Before → after DXIL |
| --- | ---: | ---: |
| 2 independent registers | 4 → 2 | 2,280 → 2,268 bytes |
| 16 independent registers | 18 → 2 | 3,288 → 3,180 bytes |
| 64 independent registers | 66 → 2 | 6,820 → 6,408 bytes |

An additional bounded source-generated kernel ran on RTX 4070 Ti SUPER. Both arms matched all scalar and lane outputs plus untouched memory on Wave32 and split Wave64. The 64-register variant shrank by 412 bytes in both modes. The 16-register two-seed control retained size and every output. These are correctness and emitted-size results. Driver timings and representative frequency remain open.

The fold assumes builder-formed SSA with valid PHI edges and the production metadata paths exercised here. The patch clean-applies to newer `80f4819098e921f2e1ab371144d4832f68ffedd6`; the results above refer to `20cf1302`. Use [this research patch](xcl-phi-scc-20cf130.patch) and the included source-only fixtures. The optional [GPU readback test](gpu_ring_readback.rs) can be copied into `crates/xcl/tests` in an isolated patched checkout. Build it with `cargo test --release --locked -p xcl --test gpu_ring_readback --no-run`. On a Wave32 physical adapter, run the resulting binary with `--ignored --skip phi_ring_native_wave64 --test-threads=1 --nocapture` under both settings of `XCL_DXIL_NO_OPT`. [XCL compiler campaign](https://github.com/xcl-dev/xcl/issues/1269)
