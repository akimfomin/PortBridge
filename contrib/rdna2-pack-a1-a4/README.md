# Native RDNA2 integer pack, cases A1–A4

KainanP requested four raw results to distinguish unsigned and signed 32-to-16-bit saturation from truncation in AnyXboxX. This optional PortBridge runner executes the four ordinary pack instructions with the exact LLVM 20.1.8 bytes and register inputs in the request. The original test cases, expected alternatives and receiving implementation are KainanP's. PortBridge supplied the standalone kernel, host launcher and output checks. [Original request and input table](https://github.com/akimfomin/PortBridge/issues/84) · [Receiving revision](https://github.com/KainanP/AnyXboxX/commit/6b052d2e12d611c490c384ef0134100ce21b9aad)

## Run on a physical GPU

Use a Linux system with a working AMD HIP installation for the card, LLVM with the AMDGPU backend and LLD. Select the actual target reported by `rocminfo` (`gfx1030` through `gfx1036`). The launcher uses HIP's current device. If the system has multiple GPUs, select the intended card with `HIP_VISIBLE_DEVICES`. Leave target overrides such as `HSA_OVERRIDE_GFX_VERSION` unset. The participant builds all three artifacts locally. [LLVM AMDGPU ABI](https://llvm.org/docs/AMDGPUUsage.html) · [HIP module API](https://rocm.docs.amd.com/projects/HIP/en/latest/doxygen/html/group___module.html)

```sh
# Start in the directory containing this README. Set the actual native target.
target=gfx1030
sed "s/gfx1030/$target/g" pack_probe.s > pack_probe-local.s
llvm-mc -triple=amdgcn-amd-amdhsa -mcpu="$target" --amdhsa-code-object-version=5 \
  -filetype=obj pack_probe-local.s -o pack_probe.o &&
ld.lld -shared pack_probe.o -o pack_probe.hsaco &&
hipcc -std=c++17 launch.cpp -o launch &&
./launch pack_probe.hsaco &&
sha256sum pack_probe.hsaco
```

The kernel runs one Wave32 group per launch. Lane zero writes six result rows into a 48-byte buffer. Two ordinary launches start with opposite byte fills. The launcher requires every row's tag, matching values on both launches, entry EXEC `ffffffff` and the in-range control `01230abc`. It then prints the four observations without choosing an arithmetic hypothesis.

Report the two launcher output lines, OS, GPU driver package version, `llvm-mc --version` and code-object SHA-256 in the original issue. An error exits before printing any observation. A case from sections B or C requires a separate measurement. [Submit an A1–A4 result](https://github.com/akimfomin/PortBridge/issues/84)

## Verified before hardware testing

LLVM 23.1.6 assembled and linked both `gfx1030` and `gfx1036` on the host. Disassembly of the pinned words returned `v_cvt_pk_u16_u32 v0, v1, v2` and `v_cvt_pk_i16_i32 v0, v1, v2` on both targets. The two linked code objects each contained three unsigned instructions (including the control) and two signed instructions with the issue's exact bytes. The source encodes these words explicitly to preserve the LLVM 20 form's unused operand bits.

The portable checker exercises missing or reordered tags, each stuck result bit, both failed controls, and valid unknown arithmetic values. The host launcher also passed 18 simulated successful/error cases. These checks establish the reporting behavior. Physical RDNA2 results are pending.

```sh
c++ -std=c++17 test_results.cpp -o test_results && ./test_results
```
