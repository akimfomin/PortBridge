# XCL. Share the background PSO commit estimate across size lanes

On Windows, XCL `cbc296ab` checks free commit separately for ordinary huge PSOs and giant PSOs. Raylitebull's [#1996](https://github.com/xcl-dev/xcl/pull/1996) improves admission within each lane and caps wanted compiles. The check still lets different lanes read the same free commit before either driver call starts growing memory. This is the driver PSO path, separate from the DXC compile-growth accounting in [#139](https://github.com/xcl-dev/xcl/pull/139).

The CPU fixture extracts the real gate from both pinned sources and from the patched #1996 source. In a controlled 3,328 MiB free-commit snapshot, #1996 allowed the two background jobs to overlap even though their estimates totalled 3,584 MiB. The patch deferred the second job until the first released its estimate. Controls cover enough budget to overlap, wanted limits, release during unwind and the cases where the monitor is unavailable.

This candidate applies one reservation to both size lanes for both ordinary and two-pass PSO creation. The reservation lives through the driver call. Existing lane caps, wanted priority and the wanted bypass stay in place. The admit check retains the existing headroom floor and additionally considers active estimates. It can conservatively count memory already committed by a running build. External memory activity, actual driver growth and wanted bypass can still exceed an estimate. No Windows D3D driver memory or whole-runtime result is inferred from this CPU fixture.

## Reproduce

Use Rust edition 2024, Python 3 and Git with a clean copy of the two pinned revisions. The only source read from XCL is `crates/xcl/src/hle/d3d12x/real.rs`. Use a clean fixture directory because the extractors create their outputs exclusively.

```powershell
python -B .\extract_legacy.py C:\path\to\xcl .\legacy.rs
python -B .\extract_legacy.py . .\wanted_legacy.rs --wanted-pr-source .\wanted-pr-real.rs
python -B .\prepare_candidate.py .\wanted-pr-real.rs .\candidate
python -B .\extract_candidate.py .\candidate\real.rs .\patch_gate.rs
rustc --edition=2024 -O .\gate_proof.rs -o .\gate-proof.exe
.\gate-proof.exe
```

Get `wanted-pr-real.rs` from the pinned public Git source. Its SHA-256 is `3ba091d7c9d198f90874aabd561cc463df2324268bca6582e25490eead4edc39`. On Windows use a byte-preserving write. The patched source SHA-256 is `e4357df4167c06b62a895763d158128852a48f4aee36fae6d7995ce153ee10c2`. The fixture does not use the graphics device. [Original main](https://github.com/xcl-dev/xcl/blob/cbc296ab65a2661a61e3e2da109134bcd5319f60/crates/xcl/src/hle/d3d12x/real.rs) · [Pinned #1996 source](https://github.com/xcl-dev/xcl/blob/ae00ec73ed21cc4d266a8f42649eaeae3387ae84/crates/xcl/src/hle/d3d12x/real.rs) · [Patch](candidate-v1/shared-psocl-commit.patch) · [CPU results](gate-proof-v2.log)
