# ADR-011: Read local Test Lab comment events and verify Pages publication

Status: Accepted

GitHub Actions can delay or drop a scheduled build. Test Lab needs prompt feedback when someone submits a structured report or review, and a maintainer needs to know when a new snapshot has reached public Pages. [Scheduled events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

A separate read-only workflow checks structured comment events from explicitly mapped issues in PortBridge. It validates GitHub identifiers and task contracts and records a short-lived receipt in Actions. An event can describe a previous state after an edit or deletion. Quick edits to the same comment can replace a pending receipt in GitHub's queue. Each publishing run scans the current sources, including upstream threads, before using reports for coverage. Keeping the publishing workflow on its existing trusted triggers prevents public comments from consuming a full deployment or receiving publishing permissions. [Comment events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#issue_comment)

A build records how old the current public snapshot is. After GitHub Pages deploys, a separate read-only job compares the exact public site and Test Lab JSON with the build, allowing brief propagation time. A successful comparison after a stale snapshot proves publication recovery. The attempt and success times for individual sources show whether their data also recovered. See the [publishing runbook](../MAINTAINERS.md#публичный-сайт).

Pages uses its read-only token for report scans to avoid the shared anonymous runner quota. The collector checks repository visibility before and after an authenticated comment scan. A source outside the token's access can still use the anonymous public path. Local scans stay anonymous by default. [REST API limits](https://docs.github.com/en/actions/reference/limits#github-token-limits)
