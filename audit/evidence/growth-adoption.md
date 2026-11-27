# Growth campaign · source and validation notes

## Compare the original frametime-report pair

The original tool is [`16b22b49d47439679811054e19db4aab70fda39c`](https://github.com/leixner/frametime-report/tree/16b22b49d47439679811054e19db4aab70fda39c). The released fix is [v0.1.1 at `1e68449753af153e1650d3211bde534bc63e73c5`](https://github.com/leixner/frametime-report/commit/1e68449753af153e1650d3211bde534bc63e73c5). leixner reproduced the reported failure and authored the released change. [Original report](https://github.com/4lwayz/portwatch-vi/issues/233#issuecomment-7206144658) · [Author's result](https://github.com/4lwayz/portwatch-vi/issues/233#issuecomment-7206219321) · [PortBridge readback](https://github.com/akimfomin/PortBridge/issues/99#issuecomment-7206434423)

Write two `.ftlog` files using the public [format](https://github.com/leixner/frametime-report/blob/16b22b49d47439679811054e19db4aab70fda39c/SPEC.md). Both use `scene=city-walk`, `settings.profile=series-s`, `settings.output=1920x1080`, `settings.raytracing=false` and `settings.upscaler=none`. Set A to `settings.internal=1280x720`, `settings.fpsCap=0`, 10,000 rows each 20 ms apart. Set B to `settings.internal=1600x900`, `settings.fpsCap=30`, 8,000 rows each 25 ms apart. Both contain 200 seconds of synthetic intervals. Values for FPS are controls for the comparator and do not simulate a real frame cap. The first numeric field is cumulative elapsed milliseconds and the second is the interval.

```sh
python -I ftreport.py summarize A.ftlog --skip 0
python -I ftreport.py summarize B.ftlog --skip 0
python -I ftreport.py compare A.report.json B.report.json A.report.json
```

On the original revision both reports passed format validation and were marked like-for-like, `-20.0%`. Version 0.1.1 rejected A/B for `settings.internal, settings.fpsCap`. The identical A/A control remained like-for-like, `+0.0%`. Only the CLI was independently rerun. leixner reported updating the web comparison as well.

The BM-v1 and frametime-report 1% lows use the same slowest-frame count and reciprocal-mean method in the pinned [KLBF implementation](https://github.com/PastiiJay/klbf-lab/blob/a0687b76d3926894c46de85f77463cc0e0e4ad7a/crates/victory-gpu/src/bench.rs#L438-L446) and [frametime-report spec](https://github.com/leixner/frametime-report/blob/16b22b49d47439679811054e19db4aab70fda39c/SPEC.md#definitions). An absolute 200 ms freeze count and a median-relative stutter count describe different thresholds. The report should also retain time origin, window, internal/output sizes, frame cap, upscaler version, frame generation policy and rendering work skipped, each as reported or unknown.

UwUCammie's [cold-launch record](https://github.com/UwUCammie/victory-amd/blob/55938e98/benchmarks/README.md#first-boot-at-1280720) independently records 4,268 accepted presents in 300 seconds from launch on RX 7900 XT, 14.23 average FPS, 292 ms P99 and an 11.18-second longest gap with five empty graphics caches. BM-v1 starts on the first world frame of its prescribed scene. The two records can be linked with their own protocol labels. No performance ranking or metric conversion was inferred. Use the [original KLBF reports and exact controls](klbf-bm-v1-pilot.md#independent-same-host-controls).

## An external participant returned a Mac row

halfwave50 independently responded to the volunteer card, after the outreach in [VIctory #1410](https://github.com/fxceless/victory-fork/issues/1410#issuecomment-7206318187). The submitted build is [`e35196aaf26ca233a66a8b08b2da06267fb134e6`](https://github.com/halfwave50/VIctory-macOS-halfwave/commit/e35196aaf26ca233a66a8b08b2da06267fb134e6). The primary notes encode separate checkpoint and boat scenes. PortBridge checked the commit and the published frame counts, then returned the attributed report to PortWatch. [Participant submission](https://github.com/akimfomin/PortBridge/issues/99#issuecomment-7206515563) · [Verification](https://github.com/akimfomin/PortBridge/issues/99#issuecomment-7206550453) · [PortWatch delivery](https://github.com/4lwayz/portwatch-vi/issues/233#issuecomment-7206556537)

MacBook Pro M4 Pro, Series X, 60-second fixed windows, native presents, no cap or frame generation as reported. At 1920×1080 output and 1280×720 internal, the two scene counts are 170 and 335 (2.83 and 5.58 FPS). The 3840×2160 output and 2560×1440 internal results are separate observations. No percentile was derived. This is self-service use of a PortBridge request with an existing report. There is no new benchmark run or installation claim.

Later the same participant independently ran the card's second exercise, using 6,000 identical 33.333 ms intervals for both samples. v0.1.0 accepted the metadata mismatch at equal measured FPS. v0.1.1 rejected it without changing the identical metadata control. PortBridge regenerated the two inputs and matched the recorded verdicts. This makes the comparison independent of the different synthetic rates in the original repro. [Participant's independent control](https://github.com/akimfomin/PortBridge/issues/99#issuecomment-7206709995) · [PortBridge verification](https://github.com/akimfomin/PortBridge/issues/99#issuecomment-7206800208)

## Native XCL controls

For [XCL #2920](https://github.com/xcl-dev/xcl/issues/2920), the [published independent inbox control](https://github.com/xcl-dev/xcl/issues/2920#issuecomment-7206406424) used two fresh processes with idle RTX 4070 Ti SUPER devices, driver 617.14, Windows 11 Pro build 28000. There is no work submission or forced device removal. See [Microsoft's DRED setup](https://learn.microsoft.com/en-us/windows/win32/direct3d12/use-dred#setting-up-dred-in-code) and [the exact test source](growth-dred-control.cpp).

```powershell
clang++ -std=c++20 -O2 -static -Wall -Wextra -Werror audit/evidence/growth-dred-control.cpp -ld3d12 -ldxgi -o growth-dred-control.exe
.\growth-dred-control.exe early
.\growth-dred-control.exe late
```

| Settings applied | Breadcrumbs | Page fault | Device status |
| --- | --- | --- | --- |
| Before creation | 0x887a0022 | 0x887a0022 | S_OK |
| After creation | 0x887a0004 | 0x887a0004 | S_OK |

This only tests the Windows inbox device. It makes the ordering distinction observable without forcing failure and separately from the XCL Agility factory. The AMD/Intel task is [#103](https://github.com/akimfomin/PortBridge/issues/103).

For [XCL #2916](https://github.com/xcl-dev/xcl/pull/2916), two isolated mode tests checked the exact decision functions using ntdll on Windows and a synthetic AMD ID. Subsequently, vibryxcx independently showed native RX 6800 worker startup on both the exact base and PR head with the setting unset. The two focused upstream tests passed with no skips. These are distinct runs. The native AMD result answers the PR author's request and was returned to the Lab under the original author's name. [Original hardware report](https://github.com/xcl-dev/xcl/pull/2916#issuecomment-7206399186) · [Credited return to #101](https://github.com/akimfomin/PortBridge/issues/101#issuecomment-7206434010)

## Other focused checks

- [KLBF #118 vs beta-2](https://github.com/PastiiJay/klbf-lab/pull/118#issuecomment-7206242382). The ordinary URL+SHA CLI could not establish a merge base. Checking the exact two-commit diff against a disposable beta-2 checkout showed that the PE file and the first two shader hunks apply, with the last shader hunk rejected. The code was not built on beta-2.
- [AnyXboxX #441, #443 and #444](https://github.com/akimfomin/PortBridge/issues/102). Git's three sequential merges on `5a08a334ef216eff98d2c7d9a9166f94c9ef70ed` produce `e880fcc0a27a4a6db1f43c7742d8f775a4f09235`. The tree is verified. The cards retain the exact shas and steps for the remaining behavior and timing run.
- [Continued #2193](https://github.com/ubiquitarianism/leonida/pull/2193#issuecomment-7206242446). Put the exact `scripts/run_standalone_tests.py` and `tests/test_run_standalone_tests.py` from `53b846f6cc5d990e381c0b2779422936f1c20a86` in matching directories in a scratch root. On Windows and Python 3.12.14, `python -I tests/test_run_standalone_tests.py -v` ran five tests with no failures. CI time was not measured by this check.
- [Continued #2414](https://github.com/ubiquitarianism/leonida/pull/2414#issuecomment-7206328423). Exact source `8cde0bef3922116bef153f2ab65ee6e8a8d01245`, `runtime/test/isa_jit_patch_test.cpp` and three referenced headers in `runtime/src`. LLVM-MinGW uses `-std=c++23 -O2 -fms-extensions -static -Iruntime/src`. The i5-13600KF passed 51 families, two fused pairs and a generated PE fixture. A compiler warning for the declaration of `__cpuidex` remains. An AVX1-only Windows host was not tested.
- [KytyPS5 #2410](https://github.com/akimfomin/PortBridge/issues/100). Exact head `c65b1abe825cc4ef2eebd3e8e082f72885f2e3fe` is textually clean against `61db2f8874d4a94fd2908a87cefa973ddc48ef6e`. Intel Arc fixture runs remain open. [shadPS4 source already uses containment](https://github.com/shadps4-emu/shadPS4/blob/0256d9e11c97938e0c2b2ea58bc93d8c7f3fbafb/src/video_core/texture_cache/texture_cache.cpp#L374-L397), so an equal-address error alone does not justify copying the Kyty fix.

## Self-service Lab cards

At publication the longer Markdown descriptions were readable by people. The current invitation parser accepts a bounded plain-text form with no links in the requested-check field. The short descriptions were put in the issue forms and the complete optional recipes moved into the discussions, preserving all source links. Each exact public issue body passed `portbridge.test_requests.parse_request`. [#99 recipe](https://github.com/akimfomin/PortBridge/issues/99#issuecomment-7206586319) · [#100](https://github.com/akimfomin/PortBridge/issues/100#issuecomment-7206586780) · [#101](https://github.com/akimfomin/PortBridge/issues/101#issuecomment-7206587037) · [#102](https://github.com/akimfomin/PortBridge/issues/102#issuecomment-7206586554) · [#103](https://github.com/akimfomin/PortBridge/issues/103#issuecomment-7206586054)

## Reuse, attribution and installation

PortWatch received one proposal to link a single unscored native report, with a live partner-feed example. FrameLab received one optional maintainer proposal for a read-only one-PR workflow. Installations, score changes, and routine usage await a separate first-party response. The public [PR intake and current tasks](https://github.com/akimfomin/PortBridge/issues/98#issuecomment-7206391931) let contributors return their own result without installing anything. The open source practices behind this path are small first contributions, clear scope, and public recognition. [Open Source Guides](https://opensource.guide/best-practices/#leverage-your-community)
