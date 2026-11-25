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

## Follow-up. Reuse slots after the last consuming piece

The independent allocator model in `interval_slots.py` allows stable values defined after piece zero. It gives each scalar a lifetime beginning at the defining piece's exit and ending at the latest entry on a crossing edge that still carries it. Treat the end as inclusive. A later value may reuse the earlier slots once its first exit follows that end. This exploits the existing order of entry loads before exit stores. A consumer loads an eligible value only on entry to its live edge. The model retains the original selector and falls back when the conservative stable area plus the dynamic payload exceeds the original maximum.

The test covers 864 lane/case executions. Two i64s with disjoint dispatch lifetimes reuse two slots, reducing 9,984 to 6,912 logical bytes across 96 lanes and keeping the three-dword stride. A stricter policy that requires the separating dispatch barrier gives up same-dispatch reuse and falls back in the narrow overlapping case until read-before-write ordering within one piece is independently established. A crossing case keeps both i64s separate because the earlier value is read again. In a branch-exclusive control, a five-dword trial would exceed the original three-dword maximum, so the model retains the original layout. [Source](interval_slots.py) · [Results](interval-results.json)

```powershell
python -B .\interval_slots.py
```

Kalmarv's census found no words eligible for the original first-piece intersection in the 25 actual split programs. His own broader static count estimates 39% fewer total loads and stores over all crossing edges. The allocator above addresses one layout constraint for the broader follow-up. The load during each actual path and the benefit on the device still need measurement. [Upstream census](https://github.com/xcl-dev/xcl/pull/2080#issuecomment-7152849712)
