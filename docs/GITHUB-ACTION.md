# Optional PortBridge check for pull requests

A maintainer can install the [pinned workflow](../examples/portbridge-pr.yml) in any selected repository. It looks up an ordinary public PR URL against the published PortBridge snapshot and posts a summary in **Actions**. For an automatic PR event, open **Checks → prior-work → Summary**. Select the linked sources to inspect their revision, scope and limits.

## Install or try a single PR

1. Copy the example to `.github/workflows/portbridge-pr.yml` on the receiving repository's default branch. This requires that repository's permission.
2. Open a PR or update its branch. Alternatively, choose **Actions → Optional PortBridge prior work → Run workflow** and enter one full public GitHub PR URL.
3. Open the run summary. A source link and exact PR revision identify the input. For a PR event the revision comes from GitHub's event. A typed URL resolves through one anonymous GitHub metadata read. The Action searches the published snapshot. An empty result may include a reason such as the absence of a saved external search. Snapshot evidence can predate the displayed PR head. Historical or automatic leads still require review in the receiving project.

The example allows `opened`, `reopened` and `synchronize`. Remove the `pull_request` trigger to run only on demand. GitHub verifies its own events and supplies the event file to a hosted runner. PortBridge does not operate a webhook listener or require an App key. The workflow has `permissions: {}`, processes the title and public URL, and runs only the pinned Action. It does not check out or execute the contributor's code. Keep this advisory job optional in branch protection. [GitHub event reference](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request) · [Job summaries](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-job-summary)

## Repeat, recover or disconnect

- Each run writes to its own job summary. Replaying an event reads the catalog again. It creates no PR comment, enrollment, task or external message. The concurrency group cancels superseded runs for the same PR. A newer catalog can return different content.
- A catalog outage still lets the receiving workflow continue. Open the summary for the scope of any bundled fallback. Re-run the job after service returns. A successful GitHub job means the advisory step ran, including when its input or the catalog was unavailable.
- Other steps may read the optional Action output `steps.<id>.outputs.status`. A read snapshot gives `reported` even when partial, stale or empty. A catalog outage gives `unavailable`. For a typed URL, anonymous GitHub 404/410 gives `origin_missing` (absent or private), and a rate limit or an unverified identity gives `origin_unverified`. Other outcomes are `invalid_input`, `skipped` and `summary_unavailable`. An error resolving the Action itself happens before its outputs exist.
- To pause, open the workflow menu under **Actions** and choose **Disable workflow**. To uninstall, remove the workflow file. Prior runs remain in the repository's Actions history under its retention policy. To roll back the component version, restore the preceding known-good commit pin from the workflow's Git history.

Agents can obtain structured results through the [MCP quick start](QUICKSTART.md#connect-codex-or-claude-code) or poll the [partner feed](../API.en.md#partner-feed). The prior-work job reads public data without a token or a partner subscription. A team may separately credit a source or send a report through its normal review process. An Action run alone establishes only that the integration executed.

The previous [one-PR demonstration](https://github.com/akimfomin/PortBridge/actions/runs/45420038315) used an earlier Action. The [M6 receiver](https://github.com/akimfomin/PortBridge-integration-test) is owned by PortBridge and separates real GitHub checks from independent team adoption.
