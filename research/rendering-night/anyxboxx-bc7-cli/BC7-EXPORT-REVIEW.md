# Review of the BC7 decoder candidate and CLI export measurement

Reviewed AnyXboxX main `b92a71b9308e76f8ec9059c01d6e18f21611dc20` and open #188 head `22c1cf973e7e2ad89fbec8e801d77d287c48729f`. The existing source-only package records the tested patch, full CPU differential, raw timing samples, and file digests. [Decoder evidence](../portbridge-anyxboxx-bc7-decode-proof/BC7-DECODE.md) · [Open tiling PR](https://github.com/LooperSalty/AnyXboxX/pull/188)

## Review result

- The fixed anchor array carries the same per-subset order as the public vector. Padding duplicates texel zero, which leaves its bit set once. The supported modes contain one to three anchors, each within the 16-texel block.
- The decoder uses the same index width and weight table for each path. Only the two-stream mode with a selected secondary color stream swaps color and alpha roles. The integer interpolation keeps the `+32` rounding term, and the decoder uses the original endpoint expansion and component rotation.
- The destination receives the same bytes in row-major order. The row loop clips the right and bottom of the final blocks. An empty surface returns immediately after the same length check, before calculating a row stride. Baseline and candidate already agreed for the fixture’s 400 valid, cropped and empty shapes, malformed lengths, and 4,560 complete BC7 payloads.
- Dimension multiplication remains unchecked for unrepresentable, oversized caller values in the existing API. That predates this performance change. No new dependency, shared state, unsafe production code, or public signature was introduced.

LooperSalty’s open #14 asks for tested texture conversion. Yoshi-233 already tested all five existing BC7 tests on the original #188 head. The earlier PortBridge comment on #188 concerns real copying of tiled data. This review concerns the shared BC7 decoding and PNG export after that stage. [Maintainer’s #14](https://github.com/LooperSalty/AnyXboxX/issues/14) · [Independent #188 test](https://github.com/LooperSalty/AnyXboxX/pull/188#issuecomment-7151190742) · [Prior PortBridge copy result](https://github.com/LooperSalty/AnyXboxX/pull/188#issuecomment-7151524901)

## Why 1.76× is a decode result

The actual `anyxboxx_texture bc7` CLI reads the compressed blocks, decodes to RGBA8, encodes an uncompressed PNG and writes it. On a generated 3840×2160 image, the PNG carries 33,179,760 scanline bytes and 507 stored DEFLATE blocks. The existing bitwise CRC loop performs approximately 265 million bit updates for the one IDAT chunk. PNG encoding also walks the scanlines for Adler-32 and copies large buffers. The relative cost of those stages needs its own measurement. The 39.3 ms median reduction in the earlier decode benchmark does not establish the speedup of the whole export. For example, if all other stages together consumed the original decode time and the isolated times transferred exactly, the total speedup would be about 1.27×. [Pinned CLI](https://github.com/LooperSalty/AnyXboxX/blob/b92a71b9308e76f8ec9059c01d6e18f21611dc20/rust/anyxboxx-texture/src/main.rs#L10-L28) · [PNG encoder](https://github.com/LooperSalty/AnyXboxX/blob/b92a71b9308e76f8ec9059c01d6e18f21611dc20/rust/anyxboxx-texture/src/png.rs)

## Fresh-process CLI measurement

`export_cli.py` builds the exact `main.rs` against the two existing release libraries from the decoder proof. Rust’s standard library is the only runtime dependency. The script stages 3840×2160 and cropped 1919×1079 synthetic BC7 using the same mode schedule and seed as the direct decoder fixture. Each arm starts a fresh CLI child and creates a fresh output file. Elapsed time includes process startup, input read, BC7 decode, PNG encoding and the production write. An independent PNG parser checks chunk order, CRCs, zlib decoding, image dimensions and scanline layout on the first output for each case. Every other complete output matches its reference SHA-256 byte for byte. Validation runs outside timed intervals.

Four alternating A/B and B/A pairs per size ran on an Intel Core i5‑13600KF, Windows x64, using `rustc 1.100.0` at `-C opt-level=3` and the default target CPU. All 16 arms completed and matched their case’s PNG. [Raw samples](cli-samples.csv) · [Medians](cli-summary.csv) · [Admission record](cli-admission.txt)

| Synthetic export | Baseline median | Patched median | Baseline range | Patched range |
| --- | ---: | ---: | ---: | ---: |
| 3840×2160 | 273.925 ms | 226.422 ms | 269.476–317.377 ms | 218.572–249.107 ms |
| 1919×1079 | 72.327 ms | 60.443 ms | 71.538–73.255 ms | 59.674–61.268 ms |

The measured full export was **1.21×** and **1.20×** as fast, respectively. The 4K result writes a 33,182,358-byte PNG with SHA-256 `6ca389819d30ff62087345f3d817289d614fb0226f809c1c3e5e721f7c0e307b`. The cropped result writes 8,284,181 bytes with SHA-256 `fc2a7208cca138cfc7477db541641f6d70a5b2e013c4301e1dc23756cf6348d8`.

From this directory, passing the original checkout that already has the decoder patch applied:

```text
python ../portbridge-anyxboxx-bc7-decode-proof/run_proof.py build --repo path/to/anyxboxx --output generated
python export_cli.py build --repo path/to/anyxboxx --output generated
python export_cli.py time --output generated --pairs 4
```

The same Rust compiler and linker options can be passed to both build commands. The run measures the first export in a fresh process. The OS page cache was uncontrolled and the production CLI submits its write without requesting a durable disk flush. This test uses linear input through the normal command. Game performance and the tiled-input flag are outside this measurement.
