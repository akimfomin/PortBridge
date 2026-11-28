# Candidate patches for receiving maintainers

## Xbox2Windows binary16 exp2 midpoint

- Base [`8027ad6e7012ecd821ed7606ec86bcb6f227ca1d`](https://github.com/R0Y00/Xbox2Windows/commit/8027ad6e7012ecd821ed7606ec86bcb6f227ca1d). [Hardware report by Leyukaka](https://github.com/R0Y00/Xbox2Windows/pull/3220#issuecomment-7231716533).
- [Patch](xbox-exp2-midpoint.patch) selects the correct binary16 result for the measured input `0x11c5` after input modifiers. The native arithmetic test checks the midpoint and neighboring encodings exactly and still checks the upper destination half. This is a narrow fix. The broader transcendental tolerance remains.
- `git apply --check` passed on the named files. The upstream standalone model passed 340 cases, including an explicit rejection of the pre-fix midpoint. Native DXIL and physical GPU execution of this revision remain open. The prior hardware report covers the baseline.
- The midpoint was originally characterized in [VIctory #3609](https://github.com/Marvisak/VIctory/pull/3609). The Xbox2Windows patch applies the rule through this project's own integer rounding path. The patch is offered under the receiving project's MIT terms.

## AnyXboxX locked corrupt shader cache entry

- Base [`512099cd752c7c07a19b60667a460af602b547e8`](https://github.com/LooperSalty/AnyXboxX/commit/512099cd752c7c07a19b60667a460af602b547e8). Receiving thread [AnyXboxX #556](https://github.com/LooperSalty/AnyXboxX/pull/556).
- [Patch](any-cache-locked-read.patch) returns a cache miss if deleting a corrupt entry fails with the Windows sharing/access error. It keeps the bad bytes out of the in-process cache. Other unexpected failures keep their existing behavior.
- `git apply --check` passed. The supplied isolated runner executes the new regression against the exact production class. The baseline raised `PermissionError`. The patched class returned a cache miss and left the locked entry on disk. This is a CPU test with an injected Windows-style file error. The full translation suite and a real file-lock test are still open.
- The patch is for the public AnyXboxX GPL-3.0 source and is offered under its receiving license. The standalone runner imports only the reviewed cache module.

Use a detached checkout at the listed base to apply either patch. Keep the exact new commit with any reported result.
