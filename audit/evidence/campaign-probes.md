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
