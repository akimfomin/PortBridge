# AMD compute-derivative follow-up

## Independent hardware result

Xbox2Windows maintainer linked lambirou’s physical RX 9060 XT report to the PortBridge AMD replay. The `(8,4,1)` case expected FP32 `0x3f800000` but read `0x3f948000` on both Xbox2Windows main `a44e1f951f47ef90850f4727c2345fed8ae1cebb` and the stack `4a00791293cbd731550ac24036879ce0db278e36`. The published 1D cases and compile controls passed. WARP skipped. This is one independent report across two trees on one adapter. The tester performed the work in Xbox2Windows. [Hardware report](https://github.com/R0Y00/Xbox2Windows/pull/3241#issuecomment-7233177324) · [Maintainer's request](https://github.com/R0Y00/Xbox2Windows/pull/3255#issuecomment-7233201943)

## Distinguish the two paths

The original fixture checks the implicit arm first and stops at its first failed assertion. It can leave the explicit LOD control unobserved. The [diagnostic patch](separate-derivative-readbacks.patch) runs both arms, labels each result, and retains the final failure. It affects only the synthetic test. Apply it to the named main revision. No game files are required.

```powershell
git switch --detach a44e1f951f47ef90850f4727c2345fed8ae1cebb
git apply --check <path-to-separate-derivative-readbacks.patch>
git apply <path-to-separate-derivative-readbacks.patch>
cmake --build --preset dev --target compile_dxil offscreen_check
ctest --preset dev --no-tests=error -j 1 -R '^native_compute_implicit_lod_hardware$' -V
```

A local CPU fixture injected an implicit-arm failure, verified that the explicit arm and next shape ran, and confirmed that the test still failed. The patch was also applied to the named public fixture. PortBridge has no physical readback for this diagnostic yet. The reported FP32 word decodes to `1.16015625`; it is outside the fixture’s three solid mip colours. The report alone cannot distinguish sampler, coordinate or lane-mapping behaviour. [CPU check](verify_readback_arms.py) · [Original fixture](https://github.com/R0Y00/Xbox2Windows/blob/a44e1f951f47ef90850f4727c2345fed8ae1cebb/tests/native_compute_implicit_lod_check.py)
