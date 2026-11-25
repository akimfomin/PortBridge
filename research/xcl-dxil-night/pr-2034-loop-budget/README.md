# XCL compact DXIL loop-budget equivalence

Reviewed Royalflamejlh's open #2034 at `0e4e10e53b2f0f7d9a8bf2b09f1f0d137bde2d62`. The plain translator checks and spends the loop budget before the body of every CFG loop-header visit. The compact form checks and spends it after an edge when the destination number is at most the source number. Compact block numbers follow PC order. A backwards address can be acyclic and the first forward entry into a genuine loop header does not individually spend the compact budget. [Plain guard](https://github.com/xcl-dev/xcl/blob/0e4e10e53b2f0f7d9a8bf2b09f1f0d137bde2d62/crates/xcl/src/gpu/dxil/kernel.rs#L308) · [CFG headers](https://github.com/xcl-dev/xcl/blob/0e4e10e53b2f0f7d9a8bf2b09f1f0d137bde2d62/crates/xcl/src/gpu/dxil/cfg.rs#L235) · [Compact guard](https://github.com/xcl-dev/xcl/blob/0e4e10e53b2f0f7d9a8bf2b09f1f0d137bde2d62/crates/xcl/src/gpu/dxil/compact.rs#L196)

The standalone CPU model applies those exact predicates to a finite counter loop and two small control-flow graphs. A loop terminating naturally after 65,537 iterations produces counter 65,536 without the exit marker in the plain form, and 65,537 with the marker under the compact rule. The model uses the stock budget and a finite step bound, with controls ending naturally at 65,535 and 65,536. A reduced-budget acyclic witness shows that a decreasing PC can spend the compact budget. The third graph has the same class payload and successor offset in an ordinary block and a loop header, so the guard bit cannot be inferred from the original class or offset pair. The tested packed-table model restores agreement in all three cases. Native DXIL output, drivers and real workloads were outside the model. [Stock budget](https://github.com/xcl-dev/xcl/blob/0e4e10e53b2f0f7d9a8bf2b09f1f0d137bde2d62/crates/xcl/src/gpu/dxil/lower.rs#L32)

```powershell
python -I -B witness.py
```

## Local source candidate

[Patch against the exact PR head](guarded-compact-offsets.patch). The candidate distinguishes otherwise identical successor pairs by source-header status. It puts that flag in the low bit of the taken word and recovers the signed offset with an arithmetic shift. The guard runs before dispatch and shares an exit block with the normal end. The common block supplies the registers read by the epilogue.

The standalone check covers signed offsets, the non-header end entry, pair deduplication, cross-word packed entries and the stock budget. The patch adds two Rust tests for the offset encoding and the shared-class witness. The patch applies cleanly to the pinned Git index. The Rust crate and GPU tests remain unrun.

Each step still uses two words. The two example programs in the PR originally have 79 and 77 step pairs. The step ID grows by one bit if the guard distinction reaches 129 distinct keys, which would move either program past the 8,192-word cutoff. The examples retain the original entry width with at most 49 and 51 additional pairs respectively. Their real pair counts need checking before this change is adopted. [Author's table sizes](https://github.com/xcl-dev/xcl/pull/2034)
