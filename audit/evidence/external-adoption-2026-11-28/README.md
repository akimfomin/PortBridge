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

## FP16 exp2 and a second adapter

At [Xbox2Windows head 41d79706](https://github.com/R0Y00/Xbox2Windows/commit/41d79706aa9f024dff5b77d6cbc9d2598fb1434d), Leyukaka published a bounded correction and an author's RTX 5080 report. PortBridge independently checked all 70 C++ table pairs with a 96-digit reference. Sixty-two finite interior inputs lie within the documented relative-error band. The wider 70-entry table covers them; the exact tie at `exp2(-25)` is a separate emitter path. This is a CPU comparison against the pinned table, without results from a second GPU. [Published change and author's report](https://github.com/R0Y00/Xbox2Windows/pull/3220#issuecomment-7232975412) · [Independent validator](verify_exp2_table.py) · [Microsoft exp instruction](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/exp--sm4---asm-)

## FrameLab FL-19

[FrameLab #54](https://github.com/5headsmartbtw/leonida-framelab/issues/54) asks for RTX 3060 confirmation that two same-feature Super Resolution evaluations on the same D3D12 queue can be submitted with neither retired. Its announced main pin `1d782810ad82a18cec49164928f11028725de5c1` still matched the public Git ref. PortBridge prepared an optional [receipt check](verify_framelab_queue_receipt.py) for the existing probe. Use two freshly initialized fences. Queue the wait at gate value 1, submit frames with retire values 1 and 2, read both fences before releasing the gate, then verify each reference readback and retirement. Stop or release the gate on a controlled error. Keep shared parameters and per-packet parameters as separate rows. This check accepts fixed known synthetic per-frame hashes. If the agreed acceptance uses a tolerance, report that separately with FrameLab's normal numerical comparison.

Run `python verify_framelab_queue_receipt.py --self-test`. It accepted the intended receipt and rejected early retirement, early gate release, reversed output, a boolean masquerading as a submission number, and the D3D12 device-removal sentinel. This is a CPU validation of a trace shape. Only independently observed GPU evidence can prove the native feasibility. The file takes an optional receipt JSON as its single argument. No runtime or game data is bundled. [Approval](https://github.com/5headsmartbtw/leonida-framelab/issues/4#issuecomment-7227889076) · [D3D12 fence documentation](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12fence-getcompletedvalue)

```json
{
  "submitted_before_gate_release": [1, 2],
  "gate_completed_before_release": 0,
  "retired_before_release": 0,
  "retired_after_release": 2,
  "expected_readbacks": ["<first frame SHA-256>", "<second frame SHA-256>"],
  "observed_readbacks": ["<first observed frame SHA-256>", "<second observed frame SHA-256>"]
}
```

## Delivery and adoption receipts

- The [own Lab request #159](https://github.com/akimfomin/PortBridge/issues/159) records the independent AMD result and links the exact failing main revision. PortBridge returned the split-readback diagnostic to [Xbox2Windows #3255](https://github.com/R0Y00/Xbox2Windows/pull/3255#issuecomment-7233284599). The maintainer had already used the waiting AMD replay to route a meaningful next check. The independent report is credited to lambirou. No physical result for the split test has been received.
- The independent table check was [sent to Xbox2Windows #3220](https://github.com/R0Y00/Xbox2Windows/pull/3220#issuecomment-7233385268). The existing [Lab #155](https://github.com/akimfomin/PortBridge/issues/155) now gives the exact current head and test for a second adapter. No early NVIDIA author report is counted as a second independent submission.
- The [FrameLab #54 delivery](https://github.com/5headsmartbtw/leonida-framelab/issues/54#issuecomment-7233384999) provides the CPU-checked receipt verifier and offers one consent-based RTX 3060 replay after their probe is posted. The proposal has no confirmed response or physical run.
- The public [invitation #112](https://github.com/akimfomin/PortBridge/issues/112) now links the live AMD case and the existing [PR request form](https://github.com/akimfomin/PortBridge/issues/new?template=pr-check.yml). The two routes tested this wave are a prepared check in a maintainer's active discussion and a live result inside the public volunteer invitation. No bulk notifications were sent.

This wave verified one newly linked independent hardware report, in one external team. There were three published technical handoffs across Xbox2Windows and FrameLab, no newly confirmed independent issue-form submissions, and no newly verified external team installations or repeat use. The Xbox2Windows maintainer's concrete follow-up is separate from installation and autonomous use metrics.

## LAB-09 acceptance blocker

The live returned handoff covers source attribution and delivery. The review workflow still rejects a closed or merged receiving PR even with its original exact head. A local SQLite control exercised `current_receiver` with the same public-style PR permalink and full SHA. Open succeeded. Both `merged` and `closed` produced `The receiving revision changed or the task closed`. The call guard currently covers post-test delivery and decision receipt actions for source-reviewed work. Historical outcome recording needs to retain exact reviewed pins through a later close. No production write or external report was simulated. [Guard and workflow](https://github.com/akimfomin/PortBridge/blob/4b3378af870d8b3fac78bb50ffd019c886a056ba/portbridge/lab_workflow.py#L156-L168) · [Requirement](https://github.com/akimfomin/PortBridge/blob/4b3378af870d8b3fac78bb50ffd019c886a056ba/docs/PORTBRIDGE-CHECKLIST.md)

No requirements were promoted on the basis of invitations or this partial handoff. The current count remains 83 of 122 verified.
