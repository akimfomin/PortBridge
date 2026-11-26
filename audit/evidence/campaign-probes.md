# Independent compatibility checks

## AnyXboxX · the proposed Vice-Tay base

Receiving commit [`5ac6926e59043c06317edbe012aee7e51e738cf7`](https://github.com/LooperSalty/AnyXboxX/commit/5ac6926e59043c06317edbe012aee7e51e738cf7).

```sh
python -B -m portbridge.merge_check https://github.com/LooperSalty/AnyXboxX/pull/433 5ac6926e59043c06317edbe012aee7e51e738cf7
python -B -m portbridge.merge_check https://github.com/LooperSalty/AnyXboxX/pull/436 5ac6926e59043c06317edbe012aee7e51e738cf7
```

PR #433 at `3b56fa946b35b933fb0c0255086758475f98f0e8` conflicts in `draw.rs`. PR #436 at `137dd1522cc32f8f0f3cc057bc1cadcf61cf941b` conflicts in `texback.rs` and `texback/tests.rs`. The compare command reports the live PR head, so later results may change. The Git comparison alone leaves behavior and performance open. [Published comparison](https://github.com/LooperSalty/AnyXboxX/pull/454#issuecomment-7205087487)

Lewandox added the proposed overlapping-readback test to [#436](https://github.com/LooperSalty/AnyXboxX/pull/436#issuecomment-7205033607). From `third_party/victory` on exact head `137dd1522cc32f8f0f3cc057bc1cadcf61cf941b`, all four tests passed on a physical RTX 4070 Ti SUPER (617.14, Rust 1.100.0 with LLVM-MinGW). The new test checks distinct GPU buffers and payloads before completion, then hits in a second overlapping pair after the fences. The suite ran without the Vice-Tay integration. [PortBridge's test return](https://github.com/LooperSalty/AnyXboxX/pull/436#issuecomment-7205213561)

```sh
cargo test --locked -p victory-gpu texback::tests -- --test-threads=1 --nocapture
```

## XCL · native CopyTiles byte-offset control

On an RTX 4070 Ti SUPER with driver 617.14, a 64 KiB reserved buffer on a native D3D12 direct queue was mapped to one real heap tile. Both copy directions round-tripped a generated pattern. All payload and guard bytes matched at offsets 0, 4096, 65536 and 69632. 69632 combines the report's 4096-byte prefix with a 64 KiB caller offset. The test runs without XCL and establishes a host reference for a new compound-offset regression. [CryingLaughing's XCL reproduction](https://github.com/xcl-dev/xcl/issues/2908) · [Native API](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12graphicscommandlist-copytiles)

```powershell
clang++ -std=c++20 -O2 -static -Wall -Wextra -Werror audit/evidence/copytiles-offset-probe.cpp -ld3d12 -ldxgi -o copytiles-offset-probe.exe
.\copytiles-offset-probe.exe
```

```text
adapter=NVIDIA GeForce RTX 4070 Ti SUPER
offset=0 payload_mismatches=0 guard_mismatches=0
offset=4096 payload_mismatches=0 guard_mismatches=0
offset=65536 payload_mismatches=0 guard_mismatches=0
offset=69632 payload_mismatches=0 guard_mismatches=0
```

## VIctory · command-signature concurrency

[Source at `0a7ee02`](https://github.com/fxceless/victory-fork/blob/0a7ee02e8b2f3e27e7df5ef07c094f148d15a788/crates/victory-gpu/src/draw.rs#L4829-L4848) was extracted verbatim into a temporary Rust unit test and compiled with Rust 1.100.0. The CPU test uses two channels for ordering. Thread A starts creating key 1, notifies B and waits. B immediately creates and publishes `Some(42)`, then signals A. A's create callback returns `None`. The original returned `None` for A even though B's value was already live (0 passed, 1 failed). Delaying `?` until after the second lookup returned B's value (1 passed, 0 failed). The creation error is simulated and its frequency in D3D12 is unmeasured. [Published to the author](https://github.com/fxceless/victory-fork/pull/1393#issuecomment-7205145118)

The same forced ordering passed against UwUCammie's AMD/Linux port at [`2936e0c10e43c38ef13542e2349f9468325c8780`](https://github.com/jtrudeau1530/VIctory-7900XTX/commit/2936e0c10e43c38ef13542e2349f9468325c8780). The author then added the ordering to the actual PR regression at [`4455a70d6065b2dacdd8aafdb05121360fcd2756`](https://github.com/jtrudeau1530/VIctory-7900XTX/commit/4455a70d6065b2dacdd8aafdb05121360fcd2756) and reported a pass under Wine 11.22. [Author's report](https://github.com/jtrudeau1530/VIctory-7900XTX/pull/27#issuecomment-7205708084)

## VIctory-7900XTX · placed-texture integration

[PR #97](https://github.com/avatarmanz/VIctory-7900XTX/pull/97) head `856b6f87ea7b08b092a57b95796e962f0a703b2e` against receiver `014d52dedf837d1ac660a0bd256c4704be9eeb40`. Resolve the textual conflict in `draw.rs` using receiver's `host_heaps_set` path. The text merge still fails to compile: the new placement path returns a `PlacedTexture` while `begun_before` needs a reference to a `View`. Borrow `&placed.view` and keep `PlacedTexture` in scope until the query returns. Retain the existing direct `&View` for the shader path. The resulting test tree `e7d0b88fbea83194211b1df36bbf7964ea85aa2e` passed this four-test filter. This was a local candidate and the report was sent to the author. [Exact conflict, compilation error and result](https://github.com/avatarmanz/VIctory-7900XTX/pull/97#issuecomment-7205775800)

```sh
cargo test --locked -p victory-gpu --lib placed_texture -- --test-threads=1 --nocapture
```
