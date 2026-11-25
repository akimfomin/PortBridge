# XCL #2080. Retain live scratch words across several dispatches

This candidate was generated on exact #2080 head `17a984b8fd72e68dc43d1bc0b98e9446f1c78248`. It changes the copy layout and access of common scalar values while preserving the original maximum scratch allocation, dispatch sequence, synchronization and selector. It only selects scalars defined in the first piece and present on every crossing edge. Those values are written at the original entry boundary, loaded at most once in each later piece that uses them, and retained until the full chain completes. The storage remains private to each lane. Dynamic values, handles and edge-specific values follow the baseline transfer. [XCL #2080 source](https://github.com/xcl-dev/xcl/blob/17a984b8fd72e68dc43d1bc0b98e9446f1c78248/crates/xcl/src/gpu/dxil/module/split.rs)

`git apply --check --whitespace=error-all` passed. The Rust fixture extracts the patched selection and lookup directly from the patched source. It verifies the stable i32, i64 and float slots, excludes values that are absent on an edge or defined in a later piece, verifies the total slot bound, and checks the empty case. The separate graph model compared 576 lane/case results with an unsplit oracle. The native measurement uses authored three-dispatch HLSL and verifies the same layout idea. Full XCL build, emitted shaders and actual traffic on #2080's workload are open validation. [Independent model](../portbridge-xcl-stable-scratch-proof/README.md) · [Hardware surrogate](../portbridge-xcl-scratch-tiles/README.md) · [Selection check](selection.log)

## Reproduce the patch and selection check

Save `split.rs` byte-for-byte from the pinned revision. The expected SHA-256 is `672c8cc98b881ebae69fc0be46a71d5401df21fbf415357112864c0cf0b95f81`. For a Rust GNU Windows toolchain, pass the full linker path with `--linker`.

```powershell
python -I -B .\prepare_patch.py .\split.rs .\replay
python -I -B .\check_selection.py .\replay\split.rs .\checked --rustc C:\rust\bin\rustc.exe
```

[Candidate patch](ready/xcl-2080-retain-scratch.patch) · [GPL-2.0](LICENSE)
