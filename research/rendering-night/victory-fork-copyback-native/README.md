# PortBridge · Relay readback copies on one D3D12 queue

This source-only package accompanies the `victory-fork` #470 investigation. It includes exact-head source patches, the synthetic native fixture, and the two complete probe receipts from an RTX 4070 Ti SUPER. KretliJ supplied the independent cold and stable observations that motivated the investigation. [Original discussion](https://github.com/fxceless/victory-fork/issues/470#issuecomment-7152241891) · [PortBridge](https://github.com/akimfomin/PortBridge)

The dense case kept the transferred bytes at 1 MiB and changed 16 `CopyBufferRegion` calls into one. The CPU recording loop went from 4.20 to 0.30 µs median and improved in all 16 measured pairs. The paired GPU median saved 0.608 µs, a small effect beside the unchanged sparse control. The overlap case copied 112 → 96 KiB and its paired GPU median saved 0.944 µs. Both workers verified 54 full destination windows each, including unchanged padding. [Native method and raw evidence](native/README.md)

The CPU interval excludes building the copy plan. The GPU interval excludes waiting in a busy application's queue and CPU merging. The experiment establishes copy equivalence, a command-recording reduction for this shape, and the observed local intervals. It does not establish an integrated runtime or frame-time gain. Existing #71 evaluates a dedicated COPY queue and parallel compare. This fixture stays on one DIRECT queue with no such changes. [Existing queue and compare PR](https://github.com/fxceless/victory-fork/pull/71) · [D3D12 timestamp documentation](https://learn.microsoft.com/en-us/windows/win32/direct3d12/timing)

- `reported-relay-fetch-pack.patch` targets `2119b0e44c53aa9648307b0c5c73590290305b1f`.
- `main-relay-fetch-pack.patch` targets `310c6eb6c16822ab95076aad61fce19bba86bb98`.
- `relay_fetch_pack.rs` is the exact helper compiled by `native/build.ps1` into the fixture descriptor. `proof.py` provides the independent CPU oracle.
- `native/` contains sources, reproduction instructions, exact generated descriptors, raw timing rows, and paired statistics.
- `LICENSE` carries the fork's project license. `LICENSE.guard` preserves the reused MIT guard's licensing. `MANIFEST.sha256` covers the text payloads.
