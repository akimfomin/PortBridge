# AnyXboxX texture candidates on current source

The public #188 head was `22c1cf973e7e2ad89fbec8e801d77d287c48729f`; upstream main was `d02eee01bedefedda48204b798df3002c7e2ffcc`. Lewandox owns the GFX10 PR. The open #14 feature request identifies texture conversion as the receiving engineering goal. [Upstream #188](https://github.com/LooperSalty/AnyXboxX/pull/188) · [Feature request](https://github.com/LooperSalty/AnyXboxX/issues/14)

- [GFX10 copy patch](gfx10-188.patch) applies to #188 and is locally committed as `f2329f13fc4c9dee11fe21897698323c6a3067b2`. It reuses each coordinate’s contribution to tiled copying and adds 104 synthetic layout comparisons against the original address oracle, with padding and failed-input checks.
- [BC7 decoder patch](bc7-main.patch) applies independently to the official main revision above, with local commit `b923a550f9a9602a95ebc0d7e8d686211c869728`. The changes apply together to #188 as local proof commit `1844f3b76df63e6a05add7927ad34408a287f373`.

The standard pinned Cargo workspace command `cargo test --locked --manifest-path rust/Cargo.toml -p anyxboxx-texture` ran under Windows x64 with Rust 1.100.0 and upstream TomBox gitlink `f89e4106fe8a1728515afa34ceb5097132cadcda`. On #188 it passed 13 original tests, 16 with the copy optimization alone, and 17 with both patches. On main it passed the five original BC7 tests and the new crop/block-order check. Git apply and git diff checks were clean. Yoshi-233 also passed the original 13 on Ubuntu. [Independent report](https://github.com/LooperSalty/AnyXboxX/pull/188#issuecomment-7151190742)

The earlier release microbenchmark measured 1080p detile at 36.34 → 3.71 ms and tile at 35.62 → 2.51 ms. The separate linear BC7 CLI check measured 4K PNG export at 274 → 226 ms with byte-identical files. Those timings are prior measurements for the same source changes. The current verification adds combined crate regression evidence and an independent landing point for BC7. [First handoff to Lewandox](https://github.com/LooperSalty/AnyXboxX/pull/188#issuecomment-7151524901)

The patches are GPL-3.0-or-later and preserve the source acknowledgements. The GFX10 equations retain AMD Mesa addrlib’s MIT notice. Test inputs are synthetic. [AnyXboxX licence](LICENSE.AnyXboxX)
