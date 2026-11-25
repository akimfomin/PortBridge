# victory-fork #583 — Shadow buffer decay at queue-call boundaries

Reviewed Lewandox’s [victory-fork #583](https://github.com/fxceless/victory-fork/pull/583) at `f176c4774680f5813461cc5bd4e3ccfda1f55dd3`, based on main `c96b4f2b8365bf43d54ab074940923ef8267f4c6`. The PR adds Shadow state tracking inside each list. Its original test sends each recorded list in a separate queue call. Regular `Host::submit` can put multiple `[prelude, list]` pairs in a single call. [Tracker](https://github.com/fxceless/victory-fork/blob/f176c4774680f5813461cc5bd4e3ccfda1f55dd3/crates/victory-gpu/src/host.rs#L766-L798) · [Submission](https://github.com/fxceless/victory-fork/blob/f176c4774680f5813461cc5bd4e3ccfda1f55dd3/crates/victory-gpu/src/host.rs#L4067-L4147)

Direct3D 12 buffers decay to `COMMON` when an `ExecuteCommandLists` call finishes on the GPU. Two lists in the same call share resource states, so a second tracked list cannot assume `COMMON` for a Shadow left in UAV state by the first. The optional card compare list also reads prior writes as compute SRVs. Its global UAV barrier orders accesses while leaving the Shadow state unchanged. [Microsoft state-decay rules](https://learn.microsoft.com/en-us/windows/win32/direct3d12/using-resource-barriers-to-synchronize-resource-states-in-direct3d-12#state-decay-to-common) · [Microsoft queue-call ordering](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12commandqueue-executecommandlists#remarks) · [Card compare source](https://github.com/fxceless/victory-fork/blob/f176c4774680f5813461cc5bd4e3ccfda1f55dd3/crates/victory-gpu/src/host.rs#L3251-L3292)

The [patch](vf583-shadow-batch.patch) inserts a queue-call boundary before a list whose tracked Shadow identity repeats in the current call. It keeps each texture prelude with its list, leaves disjoint lists in one batch, and sends the optional card compare in a following call. The queue finishes preceding calls in order, with the existing fence behind the logical submission. Timing mode still uses one fence per timed list. In relay mode the existing ordering mutex spans the added calls, so a relay fetch cannot enter between them, and is released before signaling.

## CPU model results

| Source-extracted submission case | #583 head | Patched |
| --- | --- | --- |
| Single-list UAV → read | Valid | Valid |
| Two disjoint list/prelude pairs | One valid call | One valid call |
| Nonadjacent pairs reuse one Shadow | Second pair assumes `COMMON` while actual state is UAV | Two ordered calls, no mismatch |
| A generated card compare reads a written Shadow | Compute SRV access while actual state is UAV | Compare runs after decay, no mismatch |
| Timed pair followed by a card compare | Timed lists separate, final compare can still see UAV | Compare gets its own call, two timed fences retained |

The baseline reports six modeled state mismatches in the default build and seven with diagnostics, with exit `2` in both. Both candidate versions return 0 with no modeled mismatches. The fixture checks exact command order, texture prelude adjacency, fences, and relay lock scope. It uses a mock queue and only fabricated IDs and states. [Raw results](results.txt)

The patch addresses boundaries between tracked lists and the generated card compare. Raw-address and dynamically indexed heap buffer use that bypasses #583’s `BufferStates` still needs its own audit. The whole crate, native Direct3D execution and frame timing are outside this CPU verification.

## Reproduce

From this folder, use Git, Python 3 and a Rust toolchain. A sparse checkout selects the exact `host.rs` source. The harness extracts `BufferStates`, list assembly, compare append, late/default/timed dispatch, and fence code from the pinned and patched versions. It supplies a CPU state model for the COM endpoints. [Extractor](extract_submit.py) · [Model](state_fixture.rs.in)

```text
git clone --filter=blob:none --no-checkout https://github.com/fxceless/victory-fork.git victory-open
git -C victory-open fetch --no-tags --filter=blob:none origin refs/pull/583/head
git -C victory-open sparse-checkout set --no-cone /crates/victory-gpu/src/host.rs
git -C victory-open checkout --detach f176c4774680f5813461cc5bd4e3ccfda1f55dd3
git -C victory-open apply --check ../vf583-shadow-batch.patch
git -C victory-open apply ../vf583-shadow-batch.patch
python run_fixture.py --repo victory-open
```

The runner accepts `--rustc` and `--linker` overrides. Generated source incorporates GPL-3.0-or-later victory-fork code at the pinned revision.
