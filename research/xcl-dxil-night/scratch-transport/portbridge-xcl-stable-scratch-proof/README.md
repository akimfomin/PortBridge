# XCL #2080 stable scratch prefixes

An independent Python model of the XCL dispatch-chain handoff, built from synthetic lane programs. It compares the original lane without splitting, the original per-edge scratch layout, and a candidate shared prefix. The expected lane results come from executing the original synthetic operations directly. The other two arms perform actual reads and writes of a poison-initialized list of DWORDs, including the selector accesses on every later launch.

The reference is [`split.rs` at `af2bd61e39344b0db2f37f14d950c78e0022e7df`](https://github.com/Kalmarv/xcl/blob/af2bd61e39344b0db2f37f14d950c78e0022e7df/crates/xcl/src/gpu/dxil/module/split.rs). The reference places a selector at DWORD 0, computes thread stride from the widest crossing edge, dispatches later pieces through the lane's tag, and repacks live payload before writing the next tag. The model implements the reference's one-word and two-word raw scalar storage plus zero-transport rematerialization. The fixture source is original and MIT-licensed.

## Candidate rules

- Intersect the live values for **all** actual piece-crossing edges, then retain only scalar SSA values defined in piece 0. A value defined later, present on only some edges, or rematerialized is outside the prefix.
- Keep the original maximum stride and tag offset. Allocate eligible values at the same offsets on every edge. Pack the rest per edge after the prefix in the original relative order.
- Write the prefix only when piece 0 takes a crossing edge and before publishing the tag. On any later crossing, write only the dynamic payload and the new tag. Terminal and skipped lanes use the original tag protocol.
- When the correct bridge is entered, load a stable value if an original operation in the destination piece consumes it. The modeled load is conservative for an operand used by only part of that piece: every lane entering the piece loads that operand. Operand accounting includes original phi and terminator uses. A value carried solely for an outgoing edge causes no additional load or store in a later piece.

In the mixed fixture the prefix has one i32 word and two i64 words. The remaining i32 begins at different offsets on two edges. Lane routes include a direct `0 → 4` skip, exits from three nonfinal pieces, two distinct incoming payload assignments and a phi-like selection. A second branching fixture keeps differently typed, path-specific definitions dynamic and checks raw f32 sign and NaN payload bits.

## Run and results

```text
python -I -B validate.py --json results.json
```

Four regression checks compare 576 lane/case executions. For each case the figures below count reads plus writes across 96 lanes, including selector accesses. `results.json` records reads and writes separately.

| Case | Reference bytes | Candidate bytes | Saved | Stride, DWORD/lane |
| --- | ---: | ---: | ---: | ---: |
| Mixed, five pieces and eight edges | 9,644 | 7,448 | 22.77% | 7 |
| Linear, three pieces | 7,680 | 5,376 | 30.00% | 5 |
| Linear, four pieces | 11,520 | 6,912 | 40.00% | 5 |
| Linear, five pieces | 15,360 | 8,448 | 45.00% | 5 |
| Linear, five pieces with transient values only | 6,144 | 6,144 | 0.00% | 2 |
| Branching, no common scalar definition | 2,880 | 2,880 | 0.00% | 3 |

For a path with `C` crossings and `W` stable DWORDs, the modeled write saving is `(C - 1) × W` when `C ≥ 1`. Add `W - R` for each entered noninitial bridge, where `R` is the number of stable words consumed by original operations in its piece. Multiply DWORD counts by four to obtain logical bytes.

The counts measure logical transport requests from these fixtures. Allocation size, physical memory traffic, compiler integration, driver behavior and the workload discussed in #2080 require separate measurements. The independent model uses just Python's standard library and has no shader compilation or device dependency.
