# Test Lab review in public discussions

## Accepted on 2026-11-25

The first monitored discussion on a reviewed task card receives decisions from that repository's owner. A decision names the task, the permalink of a report in one of its monitored discussions, the current report digest and either approval or revocation. PortBridge uses the latest matching decision made after the report's latest edit. The review and the original test keep separate attribution and links. Maintainer adoption stays a separate field.

The refresh and invitation paths resolve the same evidence. Cached decisions are stored beside the corresponding report scan under a separate scope. A temporary failure retains the previous state and marks it stale. A new approval requires a successful check of the target report at or after the decision. A successful scan removes deleted decisions. Evidence from a source that becomes private is cleared. Earlier releases continue to read their existing report rows after a rollback.

Approving a report changes its review authority. Its actual test outcomes, revisions and the author's opt-in come from the report itself. GitHub supplies the reviewer identity and repository owner association.

See [Test Lab](../TEST-LAB.md#review-a-community-report) for the user workflow.
