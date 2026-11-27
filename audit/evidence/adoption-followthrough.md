# Follow-through from the 50 public handoffs

The source of truth for these 50 outbound links is [the first campaign audit](https://github.com/akimfomin/PortBridge/blob/3e53950701713c6259eb7028eef2ae594d948fda/audit/LATEST.md). All 50 original comments were found in public GitHub discussion listings. The entries below have subsequent posts from another human account. Reviews, unrelated updates, requests, an explicit adoption and a separate reproduction remain different outcomes. The other 32 threads had no subsequent public message from another human account at this read.

| Original outbound | Subsequent source links |
| --- | --- |
| [AnyXboxX #454](https://github.com/LooperSalty/AnyXboxX/pull/454#issuecomment-7205087487) | [mauroalvare](https://github.com/LooperSalty/AnyXboxX/pull/454#issuecomment-7205307619) |
| [victory-fork #1393](https://github.com/fxceless/victory-fork/pull/1393#issuecomment-7205145118) | [UwUCammie](https://github.com/fxceless/victory-fork/pull/1393#issuecomment-7205439168) |
| [AnyXboxX #449](https://github.com/LooperSalty/AnyXboxX/issues/449#issuecomment-7205184273) | [KainanP](https://github.com/LooperSalty/AnyXboxX/issues/449#issuecomment-7206246860) |
| [xcl #2910](https://github.com/xcl-dev/xcl/pull/2910#issuecomment-7205205815) | [fromthemoonx](https://github.com/xcl-dev/xcl/pull/2910#issuecomment-7205391801) · [KOLESNiii](https://github.com/xcl-dev/xcl/pull/2910#discussion_r4714525020) · [KOLESNiii](https://github.com/xcl-dev/xcl/pull/2910#pullrequestreview-6081962370) · [KOLESNiii](https://github.com/xcl-dev/xcl/pull/2910#issuecomment-7206489501) |
| [klbf-lab #86](https://github.com/PastiiJay/klbf-lab/issues/86#issuecomment-7205205908) | [PastiiJay](https://github.com/PastiiJay/klbf-lab/issues/86#issuecomment-7205221785) |
| [AnyXboxX #436](https://github.com/LooperSalty/AnyXboxX/pull/436#issuecomment-7205213561) | [LooperSalty](https://github.com/LooperSalty/AnyXboxX/pull/436#issuecomment-7205296487) |
| [xcl #2908](https://github.com/xcl-dev/xcl/issues/2908#issuecomment-7205310457) | [CryingLaughing](https://github.com/xcl-dev/xcl/issues/2908#issuecomment-7206798381) |
| [VIctory-7900XTX #27](https://github.com/jtrudeau1530/VIctory-7900XTX/pull/27#issuecomment-7205556913) | [UwUCammie](https://github.com/jtrudeau1530/VIctory-7900XTX/pull/27#issuecomment-7205708084) |
| [VIctory-7900XTX #237](https://github.com/avatarmanz/VIctory-7900XTX/pull/237#issuecomment-7205598787) | [Jesper-Andersson](https://github.com/avatarmanz/VIctory-7900XTX/pull/237#issuecomment-7205899562) |
| [VIctory-7900XTX #386](https://github.com/avatarmanz/VIctory-7900XTX/pull/386#issuecomment-7205598843) | [UwUCammie](https://github.com/avatarmanz/VIctory-7900XTX/pull/386#issuecomment-7205984874) · [UwUCammie](https://github.com/avatarmanz/VIctory-7900XTX/pull/386#issuecomment-7206676743) |
| [leonida #2352](https://github.com/ubiquitarianism/leonida/pull/2352#issuecomment-7205599124) | [ecox982745](https://github.com/ubiquitarianism/leonida/pull/2352#issuecomment-7205880035) |
| [victory-fork #1333](https://github.com/fxceless/victory-fork/pull/1333#issuecomment-7205727397) | [CwWwWwW](https://github.com/fxceless/victory-fork/pull/1333#issuecomment-7205834214) |
| [portwatch-vi #233](https://github.com/4lwayz/portwatch-vi/issues/233#issuecomment-7206144658) | [leixner](https://github.com/4lwayz/portwatch-vi/issues/233#issuecomment-7206219321) · [UwUCammie](https://github.com/4lwayz/portwatch-vi/issues/233#issuecomment-7206398500) |
| [xcl #2916](https://github.com/xcl-dev/xcl/pull/2916#issuecomment-7206328392) | [vibryxcx](https://github.com/xcl-dev/xcl/pull/2916#issuecomment-7206399186) |
| [Vice-Tay #91](https://github.com/TaynanGT/Vice-Tay/pull/91#issuecomment-7206299280) | [HabibUrRehmanBhattii](https://github.com/TaynanGT/Vice-Tay/pull/91#issuecomment-7206859809) |
| [victory-fork #1414](https://github.com/fxceless/victory-fork/pull/1414#issuecomment-7206317317) | [Filip722](https://github.com/fxceless/victory-fork/pull/1414#issuecomment-7206583060) |
| [xcl #2920](https://github.com/xcl-dev/xcl/issues/2920#issuecomment-7206406424) | [andrewDoing](https://github.com/xcl-dev/xcl/issues/2920#issuecomment-7206656661) |
| [xcl #2869](https://github.com/xcl-dev/xcl/issues/2869#issuecomment-7206407695) | [Natakout](https://github.com/xcl-dev/xcl/issues/2869#issuecomment-7206623336) |

## Run the existing workflow with an agent

- AnyXboxX #465 merges cleanly on `4340aac1a494b9649c00e0e1ad2c6fbe6ea00e80` at head `f9e426063fff21619ecb5e15498d58a21ade7e77`. Anyone can run the same check using the documented PR+SHA input. The Git test reports no changed test file because the relevant regression sits inside `resource.rs`. [Pinned host test and 8 GB recipe](https://github.com/akimfomin/PortBridge/issues/107#issuecomment-7206929868)
- VIctory #1414 response by Filip722 supplies the exact fixture `4f1640797187b37666cab4a78175830bd20c2ed8` and correction `f189f9a3a670f67feb18a8c6b5efafe3f32ac509`. These public revisions are suitable for a second synthetic hardware report. [Agent recipe and expected outcomes](https://github.com/akimfomin/PortBridge/issues/106#issuecomment-7206930100)
- For XCL CopyTiles and Continued placed write-back, the credited authors already ran the controls that PortBridge suggested. [Evidence submission #108](https://github.com/akimfomin/PortBridge/issues/108) links both exact before/after pairs, what can be borrowed, and what was actually tested. This is a reference for adjacent work without needing to ask the same contributors to repeat it.
- The independent XCL factory comparison is linked in [Lab #103](https://github.com/akimfomin/PortBridge/issues/103#issuecomment-7206944673) alongside the inbox D3D12 experiment. andrewDoing owned the test and measurements. Other vendors remain open.

```sh
python -B -m portbridge.merge_check https://github.com/LooperSalty/AnyXboxX/pull/465 4340aac1a494b9649c00e0e1ad2c6fbe6ea00e80
```

## PortWatch and BM-v1 adoption trial

[The live results widget](https://akimfomin.github.io/PortBridge/partner.html?kind=result) displays the frametime-report story and the attributed Mac report. The existing PortWatch proposal now links the widget. The tracker and any scoring change remain under the maintainer's control. [Updated proposal](https://github.com/4lwayz/portwatch-vi/issues/233#issuecomment-7206556537)

Tested [frametime-report v0.3.0](https://github.com/leixner/frametime-report/releases/tag/v0.3.0), exact commit `2e637f41d10371f542d1fe8eb9c54499e5d267ff`. Make an ordinary `frametime-log v1` file with marks a=0 ms, b=200000 ms, c=400000 ms. Include `scene=city-walk`, `settings.profile=series-s`, `settings.output=1920x1080`. Window a to b has 1,995 intervals of 100 ms followed by 99, 200, 201 ms. Window b to c has 2,000 intervals of 100 ms. Use elapsed milliseconds as the first field of every frame line and the interval as the second field.

```sh
python -I ftreport.py summarize example.ftlog --skip 0 --from-mark a --until-mark b
python -I ftreport.py summarize example.ftlog --skip 0 --from-mark b --until-mark c
```

| Window | Duration | Frames | Freezes above 200 ms | Longest interval | Median-relative stutters |
| --- | ---: | ---: | ---: | ---: | ---: |
| a–b | 200 s | 1,998 | 1 | 201 ms | 0 |
| b–c | 200 s | 2,000 | 0 | 100 ms | 0 |

Both windows passed the tool's checks. The count uses BM-v1's strict threshold, with a separate metric for median-relative stutters. Record the original time origin and window definitions. Do not infer that an interval-based capture has counted idle time before its first present. [Versioned specification](https://github.com/leixner/frametime-report/blob/2e637f41d10371f542d1fe8eb9c54499e5d267ff/SPEC.md) · [Lab discussion](https://github.com/akimfomin/PortBridge/issues/99#issuecomment-7206945697)

## Outstanding adoption checks

Three new addressed offers were posted to HabibUrRehmanBhattii, Solarthis and Epic-Y. A current upstream decision and a ready input are linked from each. Follow-up replies from a new participant or acceptance of the PortWatch/FrameLab integration have not yet been observed. The GitHub Action, MCP and bare tools still have separate evidence from their technical readiness. No external repository received an installation.
