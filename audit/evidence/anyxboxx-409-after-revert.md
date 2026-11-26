# AnyXboxX after #452 · first comparison on the receiving branch

## Which base is being considered

Current AnyXboxX main is [`15024d54e690743604a67287f0e3f3f30adbaba8`](https://github.com/LooperSalty/AnyXboxX/commit/15024d54e690743604a67287f0e3f3f30adbaba8). Its tree `118499ccd684215724c071c3ce00845234644e92` is identical to pre-#409 [`50936c0f15d3daa3060389f8977f4e977476d2b9`](https://github.com/LooperSalty/AnyXboxX/commit/50936c0f15d3daa3060389f8977f4e977476d2b9). The combined base is archived by the [#409 merge `37d4686711bbb04c2cc3825f3f13bbff7c140fb0`](https://github.com/LooperSalty/AnyXboxX/commit/37d4686711bbb04c2cc3825f3f13bbff7c140fb0). In #452 the maintainer makes a renewed combined-base trial conditional on NVIDIA performance. No newer candidate SHA was identified in the public refs and discussions checked. [Maintainer's revert and criteria](https://github.com/LooperSalty/AnyXboxX/pull/452) · [mauroalvare's request](https://github.com/LooperSalty/AnyXboxX/pull/409#issuecomment-7201621736)

The combined base had reported AMD/Linux speed and rendering gains and independently reported lower memory demand on NVIDIA, alongside an NVIDIA frame-rate regression. The warm RTX 5070 comparison used a moving player and one sample per row. It informs the revert, with the same-scene and rendering comparison still relevant for the next candidate. [AMD/Linux](https://github.com/LooperSalty/AnyXboxX/pull/409) · [NVIDIA 32 GB system](https://github.com/LooperSalty/AnyXboxX/pull/409#issuecomment-7203675744) · [Warm NVIDIA comparison](https://github.com/LooperSalty/AnyXboxX/pull/452#issuecomment-7203430171)

## A bounded triage

Checked the current receiving tree and four open heads with `git merge-tree --write-tree --name-only`. A clean tree merge tests textual compatibility. The proposed behavioral controls below would establish whether the code still does the right thing.

| PR and pinned head | Result for the restored main | Next behavior check |
| --- | --- | --- |
| [#429](https://github.com/LooperSalty/AnyXboxX/pull/429) · merge `91c15f25eb674db83eb044af5b9f63754bc668d5` | Already in history. The restored tree contains the `VICTORY_LEVELS_RECLAIM` opt-in. | Keep existing retention controls for held and GPU-written mips when evaluating a future replacement. |
| [#416](https://github.com/LooperSalty/AnyXboxX/pull/416) · merge `50936c0f15d3daa3060389f8977f4e977476d2b9` | Already in the restored tree, whose tree ID equals the merge commit's. | On a future replacement, verify cold and warm runs with a driver cache hit and equivalent output. |
| [#433](https://github.com/LooperSalty/AnyXboxX/pull/433) · `7fa7e26ac1a58e68ea692d0ced17319025683e19` | Conflict in `draw.rs`. Main's ordinary reset clears `fresh_tables`, while `State::replay` on a cut retains them. The replay fix is still meaningful. | After a wait cuts a command list, resolve the same table on the new list and ensure it observes current constants and indirect data. Earlier slots must survive until the earlier work completes. |
| [#447](https://github.com/LooperSalty/AnyXboxX/pull/447) · `854b138652448f3f5a23a41ee1be9cef40ce75ba` | Conflict in `pipeline/host.rs`. | Test creation with mixed integer and normalized targets, and repeat after a change in the number of render targets. Require valid output as well as pipeline creation. |
| [#448](https://github.com/LooperSalty/AnyXboxX/pull/448) · `534396239a59d9273a6edcdf05e87c7f64e46937` | Lowering files merge. Conflicts remain in `emit/valu_tests.rs` and `lib.rs`, including test integration and cache-version context. Neptune still emits constant-predicate floating-point compares. | Keep the WARP dispatch and native hardware tests for finite, infinite and NaN inputs, and verify old shader cache entries are invalidated. |
| [#436](https://github.com/LooperSalty/AnyXboxX/pull/436) · `c60ae2c8bf0c1ab96710e12e5955c51adade8431` | Directly based on the restored main, clean textual merge. | Check pooling at the fence boundary and verify contents on repeated readbacks. Compare warm performance with equivalent rendered work. |

The two early candidates for the current tree are #433 for correctness at list cuts and #436 for a cleanly applicable readback optimization. This was the source-only triage. [Confirmed receiving tree](https://github.com/LooperSalty/AnyXboxX/commit/15024d54e690743604a67287f0e3f3f30adbaba8) · [Current replay](https://github.com/LooperSalty/AnyXboxX/blob/15024d54e690743604a67287f0e3f3f30adbaba8/third_party/victory/crates/victory-gpu/src/draw.rs#L904-L923)

## Follow-up on the receiving commit

[PortBridge #96](https://github.com/akimfomin/PortBridge/pull/96) adds a rerunnable Git comparison. Give it a public pull request URL and the full receiving commit. It checks the current PR head, records both pins, shows changed test files and suggests a first verification. It never runs code from the PR. The next behavioral step for #433 (checking current constants after a cut and preserving earlier descriptors until the fence completes) came from manual source review. The automated report supplies the exact conflict and test file.

```sh
python -B -m portbridge.merge_check https://github.com/LooperSalty/AnyXboxX/pull/433 15024d54e690743604a67287f0e3f3f30adbaba8
```

On that same receiving commit, #433 reported one conflict in `draw.rs` and linked [the changed cut regression](https://github.com/LooperSalty/AnyXboxX/blob/7fa7e26ac1a58e68ea692d0ced17319025683e19/third_party/victory/crates/victory-gpu/src/draw/cut_tables_tests.rs). #436 reported a clean merge. #429 reported no tree changes.

### Independent GPU check for #436

Built and ran the PR's public tests at [`c60ae2c8bf0c1ab96710e12e5955c51adade8431`](https://github.com/LooperSalty/AnyXboxX/pull/436/commits/c60ae2c8bf0c1ab96710e12e5955c51adade8431) on a physical NVIDIA GeForce RTX 4070 Ti SUPER with driver 617.14. From the PR worktree's `third_party/victory` directory:

```sh
cargo test --locked -p victory-gpu texback::tests -- --test-threads=1 --nocapture
```

Three tests passed. The reuse case ran 128 readbacks with two resource allocations, 50,331,648 allocated bytes, zero CPU scratch allocations and 3,029 µs aggregate landing time. Pattern changes and guard padding were covered. The test waits for each batch through `host.execute()`, so it supplies no evidence for two outstanding submissions or game frame times.

A useful next control keeps two distinct readback payloads outstanding, delays the first completion, and checks that each result retains its own contents. spk-c's VIctory #1376 test demonstrates separate stale-mapping and fresh-readback controls at a different lifetime boundary. [Readback reuse tests](https://github.com/LooperSalty/AnyXboxX/tree/c60ae2c8bf0c1ab96710e12e5955c51adade8431/third_party/victory/crates/victory-gpu/src) · [VIctory #1376](https://github.com/fxceless/victory-fork/pull/1376)

