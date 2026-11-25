# A research queue from public evidence

## Decision

The Activity page, read-only activity API and MCP tool share the same queue. The queue is rebuilt from indexed public observations, known revision changes and Test Lab coverage. The existing build publishes it as a field in the Activity snapshot. This uses the current schedule and source freshness checks without adding a network reader or a database for public assignments. A private Office plan still requires participant action and consent.

The first rules cover four actions.

- Review the exact Test Lab pin after an observed open pull request moves to a new revision.
- Check public reports at the pinned revision. A community report starts review. Maintainer approval remains a separate decision.
- Find the remaining eligible hardware when the task needs more coverage. An all-vendor task can have a report awaiting review and a different hardware gap at the same time.
- Compare two public project sources when the open discussion cites the other project and both mention the same technical symbol. A closed source can be used with a known revision to examine what the discussion recorded. The target remains the open discussion. A shared revision is excluded because it does not establish a separate implementation result.

High priority applies to review of reports and version changes. Test Lab gaps follow. Cross-project comparisons remain exploratory. Confidence records whether the action rests on a curated test, an indexed transition, a submitted report or a direct citation with shared symbols. A lead carries the sources, a next step and a criterion for a useful result.

Stale and unobserved sources require a new source check before a run. A source is treated as fresh for two hours after its recorded check. Confirmed unavailable sources are skipped in cross-project comparisons. The queue neither claims tasks nor posts messages.

## Reading the queue

Open the [Activity page](https://akimfomin.github.io/PortBridge/#/activity) and find Research radar. Use the action and equipment filters to narrow the queue. For a test task, open the matching Test Lab card to see the setup and reporting instructions.

Use the same field through GET /api/v1/activity, activity.json or the portbridge_activity MCP tool. The radar field contains counts and actions. Actions include a stable identifier, kind, current state, priority, confidence, impact, evidence of demand, type of effort, hardware, freshness and source links. They can be filtered by those fields. The state verify_sources means a current source check is required. IDs depend on the action and its originating task or linked source pair, so repeated exports do not create extra entries. The queue is a snapshot. The existing source history provides observed revision changes.

The change is additive. A revert removes the queue and its panel while leaving the existing Test Lab, public catalog and private plans intact.
