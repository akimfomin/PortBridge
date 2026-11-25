# Independent GFX10 copy coordinates

The original AnyXboxX #188 and the optimized copy compare equal to 105 published byte addresses across 12 layouts. At each address the probe verifies the coordinate and bytes copied in both directions. This covers separate 256 B, 4 KiB and 64 KiB layouts, element widths from one to sixteen bytes, and selected BC7 mip-tail locations. The reference coordinates are synthetic numerical facts from the independent Xbox2Windows #1469 harness at `088add19123aceba20c60b7c0498033f08d193c2`. That harness records Mesa 25.1.0 addrlib results on navi21. [Primary coordinate table](https://github.com/Holastor/Xbox2Windows/blob/088add19123aceba20c60b7c0498033f08d193c2/tests/startup_xg_gfx10_check.py)

For each clean AnyXboxX checkout, compile its actual texture library and link this probe. Run with Rust 1.100 and a working platform linker. Commands below assume a shell with those tools on PATH. Use `probe.exe` on Windows if needed.

```sh
rustc --edition=2021 -O --crate-name anyxboxx_texture --crate-type lib <checkout>/rust/anyxboxx-texture/src/lib.rs -o libanyxboxx_texture.rlib
rustc --edition=2021 -O gfx10_mesa_oracle.rs --extern anyxboxx_texture=libanyxboxx_texture.rlib -o probe
./probe gfx10-mesa-coordinates.csv
```

Repeat for [exact #188](https://github.com/LooperSalty/AnyXboxX/commit/22c1cf973e7e2ad89fbec8e801d77d287c48729f) and for a separate checkout of that same revision with [the GFX10-only patch](gfx10-188.patch). [Actual run](gfx10-mesa-proof.json). This is a CPU address and copy check for the selected surfaces. GPU execution, array coverage and timing were outside this independent probe. The probe source is MIT and the original production patch is unchanged.
