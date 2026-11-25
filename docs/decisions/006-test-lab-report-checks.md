# Scheduled Test Lab report checks

## Accepted on 2026-11-25

A FrameLab test procedure lived on merged PR #12. The maintainer sent the AMD run to issue #15, where both reports arrived while PortBridge still asked for a run. A task can now name a reporting discussion separate from its original test procedure.

The existing Pages build reads that public discussion without credentials and saves only normalized report facts in its catalog SQLite database. Each scan is scoped to the task, all its pinned revisions and the report parser version. It validates the GitHub account, comment URL, hardware, source revision and four required cases before treating a report as passing coverage. The card moves to review only with passing coverage and no current reported failure. Adoption still comes from a separate, reviewed receiving decision.

A complete scan replaces the observed reports by canonical comment URL. A transient failure retains the previous scan and its successful check time when a database is available. Confirmed private sources and legal unavailability clear the cached reports. Without the cache and with an unreachable source, the card shows that the check is unavailable. The original public reports remain the source for rebuilding state. Before an invitation can be sent for a monitored task, the dispatcher rechecks that discussion live and rechecks human approval immediately before sending.

The static site, local API and MCP read the same card builder. This first rollout uses FrameLab’s task-specific validation rules. A different test needs its own reviewed report source and coverage rules. No comment text is executed or copied into the public export.

Rollback is a revert of the change on the product branch. The report table is separate and earlier versions ignore it.

[GitHub issue-comment API](https://docs.github.com/en/rest/issues/comments#list-issue-comments) · [FrameLab report thread](https://github.com/5headsmartbtw/leonida-framelab/issues/15)
