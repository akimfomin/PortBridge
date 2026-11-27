# Discovery source release · 27 November 2026

The release candidate is `9c7cb306675167f791549899436e2d133bd69f9b`. A cold build obtained **71 files from 14 projects**. The compact source snapshot is 3,259,588 bytes. The previous PR preview indexed 40 files. A repeat reused all 71 files without requesting trees or source bytes. The production predecessor indexed 16 files. Large GitHub trees now resolve approved subdirectories individually. Snapshots keep the original explicit files first for older readers. Source bytes for selected files are checked against their pinned Git blobs.

Issue-linked results require an exact diagnostic or corroborating implementation evidence. One exact ordinary declaration can support a focused implementation question. A performance claim needs supporting evidence beyond a shared status code or list of presentation enums. Results remain candidates, and technical review remains a separate step.

| Frozen sample | Previous PR | Release candidate |
| --- | --- | --- |
| Earlier diagnostic controls | 4/5 exact spans | 4/5 exact spans |
| Earlier mixed positive controls | 2/6 exact spans | 2/6 exact spans |
| New suite, seven positives | 2/7 exact spans | 2/7 exact spans |
| New suite, four negative controls | 10 candidate links | 1 candidate link |
| Independent repeat, two positives | 1/2 exact spans | 1/2 exact spans |
| Independent repeat, two negative controls | 10 candidate links | 3 candidate links |

The first new suite was frozen before its initial scoring. One exposed failure informed a general review of corroboration, so the final result for that suite is a regression/control result. The second suite was frozen separately before checking the revised rule and evaluated once. The first new suite included three cross-project references and retrieved none of their scored spans. Generic candidates still appear in one negative issue in each new suite. This establishes reduced noise and preserved exact hits on these samples. General cross-project recall and precision remain open.

[First frozen labels](holdout.json) · [Before](before.json) · [After](after.json) · [Independent repeat labels](confirm-holdout.json) · [Before](confirm-before.json) · [After](confirm-after.json)

## Acceptance and reproduction

316 tests passed on Windows, with zero failures and zero skips. The normal export passed the publication gate. The browser source-only regression checks both local and static rendering. The review run on GitHub uses an empty checkout and authenticated public tree reads before export. [Candidate](https://github.com/akimfomin/PortBridge/pull/125) · [Cloud cold build](https://github.com/akimfomin/PortBridge/actions/runs/46045849378)

```sh
python -B -m unittest discover -s tests -v
python -B -m portbridge.code_search --db .portbridge/discovery-IV.sqlite3 --refresh --require-complete
python -B -m portbridge --db .portbridge/discovery-IV.sqlite3 export --out .portbridge/discovery-IV-site
python -B -m portbridge.release_gate .portbridge/discovery-IV-site
```

Run `python -B audit/evidence/core-mission-iii/replay.py PRODUCT_CHECKOUT INDEX_DATABASE audit/evidence/discovery-release/holdout.json` from the audit checkout. Run again with `confirm-holdout.json`. Use previous candidate `5a7cb0877c00aeeecdd3d3737087fba000b8dd75` for the 40-file baseline. The script verifies the public input hashes and refuses edited issue bodies. Only labels, lines and result URLs are committed. Anonymous GitHub limits can require a read-only token.

The merge `88d02b3a39757ffefb3b9eebe6847085643f30b6` was published and verified. The live source snapshot, the branch review artifact and the local export have identical SHA-256 `18a3b3b45c9cb4f5da74a5b2cfa8a58ee37ded734033cb4e0f975b734ad60cc9`. The browser displayed a pinned source candidate for a recent AnyPS5 pull request. The live API returned Vulkan WSI line 6902 for a known diagnostic. The site, Lab, MCP and partner feed checks passed against the same deployment with 35,929 observations. The previous PR client still reads its explicit API symbol lead. [Main deployment](https://github.com/akimfomin/PortBridge/actions/runs/46046222773) · [Live evidence](live.json) · [Measurements and scheduled receipts](measurements.json)

If rollback is needed, revert the normal merge `88d02b3a39757ffefb3b9eebe6847085643f30b6` and rebuild from main. The previous public release is `917976823ef03334bffa9e2903684dbc5fd7436e`. Its verified run retains the checkpoint. [Previous working deployment](https://github.com/akimfomin/PortBridge/actions/runs/46042940074)

## Community and operations

jstrdev independently ran the two packed-U8 tests on a physical Arc B580 at Xbox2Windows `246857e4593880fbc19ab18eb1d4a56ba8370ad6`, Debug, driver `32.0.101.9175`. Both passed, zero skips, each readback matched all 2,064 words. The tester separately identified the default D3D12 device. At that pin the native harness bypasses the shared adapter selector and ignores the environment filter. PortBridge closed the test request and delivered the result and tester's adapter finding to Xbox2Windows with attribution. RX 9060 XT testing on a later revision remains separate evidence. [Intel](https://github.com/akimfomin/PortBridge/issues/121#issuecomment-7224783967) · [AMD](https://github.com/R0Y00/Xbox2Windows/issues/3052#issuecomment-7223989165) · [Returned upstream](https://github.com/R0Y00/Xbox2Windows/issues/3052#issuecomment-7224882175)

The XCL C5 request remains open and the upstream PR #3037 addresses the separately scoped back-off portion. No new result is recorded for the separate KytyPS5 B580 request. The last two proven scheduled Pages deliveries were 8.47 h apart. The reviewed cold build and the merge deployment should be treated as manual and push-triggered events respectively. [C5](https://github.com/akimfomin/PortBridge/issues/126) · [KytyPS5](https://github.com/akimfomin/PortBridge/issues/100) · [First schedule](https://github.com/akimfomin/PortBridge/actions/runs/45917400112) · [Second schedule](https://github.com/akimfomin/PortBridge/actions/runs/45970589550)

Qualification of unrestricted transfer search, a receiving follow-up on the new Intel report and sustained schedule evidence remain open. The 81 verified, 40 partial and 1 blocked statuses are preserved pending their full evidence.
