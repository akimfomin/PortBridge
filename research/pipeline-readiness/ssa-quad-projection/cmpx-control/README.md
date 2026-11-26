# Partial EXEC word check after a guest pixel CMPX

The regression adds one synthetic RDNA2 pixel program to XCL's ordinary GPU tests. Its parent is `ba83447cd9ce59035cead63bc340135b5e46bc1b`. Apply [the test patch](cmpx-test.patch) to that revision and run the following on a Windows D3D12 machine with XCL's normal DXC setup.

```powershell
cargo test --locked -p xcl --lib gpu::dxil::lanes::ps_ballot_tests::gpu_pixel_cmpx_preserves_partial_exec_words -- --exact --nocapture --test-threads=1
```

The program saves the entry mask, filters its two words with different constants and executes `V_CMPX_NE_U32` to clear member 2 of each four-lane quad. After restoring EXEC, each pixel exports the entire entry word and entire observed output word in four exact 16-bit numeric channels. The host derives its expected word from entry coverage, the supplied mask and the lane number. It checks every pixel separately. A single oversized triangle covers all 1,024 pixels in each draw.

On the RTX 4070 Ti SUPER, the prior strict consumer, direct quad predicates and shared EXEC window all passed. Each produced all 32 low lane positions across the raster, including lane 31. The high word stayed empty on this physical Wave32 GPU under guest Wave64. Across nine draws the host verified 9,216 word pairs. This exercise measures correctness only. [Decoded receipt](result.json)

For independent native Wave64 coverage, report the `observed_entry` lines for guest Wave64 word 1. A nonzero high word must include its bit zero (guest lane 32) and a lane that the comparison actually clears. A zero entry only checks that no spurious upper bits appear.
