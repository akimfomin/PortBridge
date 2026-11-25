# AnyXboxX lot 9. What the shader and pipeline cache keys invalidate

AnyXboxX [#25](https://github.com/LooperSalty/AnyXboxX/issues/25#issuecomment-7149111612) asks for a second-run check and invalidation across releases. AnyXboxX `728c96800564acdbd9ee0516c48deff8bfef80a4` pins LooperSalty's VIctory `80d58f8fe2769d6c857eb27abc159b6cf64530a3`. That build includes t4l03's translator-based cache identity from [victory-fork #282](https://github.com/fxceless/victory-fork/pull/282).

- The pinned [build script](https://github.com/LooperSalty/victory/blob/80d58f8fe2769d6c857eb27abc159b6cf64530a3/crates/victory-shader/build.rs#L13-L58) hashes the translator sources, manifests and lock file, compiler identity, and target and feature settings. The [shader cache](https://github.com/LooperSalty/victory/blob/80d58f8fe2769d6c857eb27abc159b6cf64530a3/crates/victory-gpu/src/shader_cache.rs#L66-L101) reads that hash when forming its build identity, then [adds wave width, descriptor limit and input bytes](https://github.com/LooperSalty/victory/blob/80d58f8fe2769d6c857eb27abc159b6cf64530a3/crates/victory-gpu/src/shader_cache.rs#L181-L193).
- The [D3D12 pipeline library](https://github.com/LooperSalty/victory/blob/80d58f8fe2769d6c857eb27abc159b6cf64530a3/crates/victory-gpu/src/pipeline/library.rs#L496-L505) names entries from the pipeline type, serialized root signature, translated DXIL and state. New shader bytes or a different description produce a new key. Changing the app alone can reuse entries with identical descriptions.

The reproduction runs the exact build script on two synthetic source trees. Editing only the app or moving the checkout keeps the translator identity. Editing translator source, changing the workspace lock file, selecting a translator feature or changing target features gives four different identities. Restoring the inputs restores the original identity. Separately it calls the extracted production key functions with synthetic build, shader and descriptor inputs. Shader keys separate a changed build, wave width and view limit. A padded and unpadded input with the same DXBC-declared length share a key. Different translated bytes, root signatures and state change the pipeline name. [Recorded outcomes](verified-keys.json)

## Reproduce

```powershell
cargo build --locked --release
$rustcPath = (Get-Command rustc -CommandType Application).Source
python -I -B verify.py --rustc $rustcPath --bin-dir target/release --target x86_64-pc-windows-msvc --out another-keys.json
```

The recorded test used Windows gnullvm, Rust 1.100.0 and BLAKE3 1.8.7. `translator_identity.rs` matches the pinned Git blob `098cc85b7734a047566936a628b766bca404f85b`. `source_keys.rs` extracts the public GPL-3.0-or-later key functions linked above. `cache_keys.rs` and `verify.py` are the synthetic fixtures. The key test does not run a retail executable, create a D3D12 pipeline or read the user's cache. It provides evidence about compiler identity and namespace invalidation. The outstanding acceptance test is a second supported launch with normalized runtime counters for cached and newly translated shaders. It also leaves reclamation of older files open.

[VIctory license](LICENSE) · [Official Cargo build-script reference](https://doc.rust-lang.org/cargo/reference/build-scripts.html)
