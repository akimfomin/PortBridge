# A loop-carried four-bit window on D3D12

The recovered value at a loop header depends both on the entry mask and on the mask from its last iteration. This control checks an actual cycle in the compiler's SSA graph. An ordinary D3D12 pixel shader starts with one of two masks, completes two trips around the loop, adds a different mask on each trip and exports its final local window. No game asset is used.

The test requires the experimental compiler to recognize the sealed loop header and its backedge. The Wave64 case inserts its high-word predecessor values in the opposite order. The baseline extracts a nibble from the full original mask. Both compile with the same XCL backend. Each returned pixel must agree with the CPU answer on all four channels, including the round count and initial seed. A fresh, complete 32×32 image was read after each draw. All eight draws passed on an RTX 4070 Ti SUPER, driver 617.14. This is a uniform trip-count regression on a physical subgroup of 32. Native 64-lane execution and arbitrary divergent loop bodies remain open. [Raw test output](observations.json) · [Test patch](loop-control.patch)

From an XCL checkout with the strong baseline `051bdda602796c47c107419ae5afff8272d5ca2d` imported from the parent [experiment bundle](../xcl-experiment.bundle), import the [loop bundle](xcl-loop-control.bundle) and run the test on Windows with a D3D12 adapter and DXC.

```sh
git bundle verify /path/to/xcl-loop-control.bundle
git fetch /path/to/xcl-loop-control.bundle refs/heads/codex/paired-mask-loop-control
git switch --detach 4423f915aa9286649563484174203b980650c203
cargo test --locked -p xcl --lib gpu_two_latch_updates_preserve_the_loop_header_mask_window -- --show-output --test-threads=1
```

The test prints eight `LOOP_GFX` rows only when a hardware adapter executes it. A machine that prints `SKIPPED` supplies no physical result. The compiler under test is `072b1f25bed8ef69d976f547d05fcc35f37db101`.

## Runtime scope and scalar loop counts

The strong stack merges with XCL main `b49be1836844fe0b0cdb3211dce3cb7fb4e21ac7`. Its complete workspace test initially found two failures that the isolated runs missed. One test expected a constant at IR construction time although the builder expressed the same value as a typed zero extension. Its independent constant-input oracle now reads the emitted integer operations and rejects unsupported ones. A second test requires byte-identical output from a divergent guest loop that accumulates a scalar population count. The opt-in compiler now uses full masks whenever a guest CFG contains a loop and a scalar population-count instruction. The existing byte-for-byte regression is retained. Neither licensed heavy Mobile NeRF instruction stream contains any scalar population count. These two results therefore remain applicable. Independent AMD, Intel and native Wave64 checks still matter before broadening the proven domain.

The [runtime candidate](https://github.com/akimfomin/xcl/commit/5d04cc10fa11654179d4bde0c1fcdc1d7ffb2cbc) uses its own cache identity `xcl-direct-pixel-mask-projection-v4` for the optional direct pixel stage. The loop test itself deliberately builds an SSA loop with local observations and no scalar population-count instruction. Its physical evidence complements the conservative guest fallback.

The complete Windows workspace on the [combined current-main snapshot](with-current-main.bundle) at `488ffe89e86e0a1678e2c1b44af4816708af20ec` passed 1,450 tests across 37 targets, with zero failures, 47 ignored and 28 explicitly skipped subcases. The authored guest title rendered and read back a triangle. Fetch this incremental bundle after importing the loop bundle above and fetching XCL main `b49be18`. [Test totals and skips](workspace.json) · [Path-scrubbed Rust output](workspace.log.gz)
