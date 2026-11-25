# Common Test Lab report contracts

## Accepted on 2026-11-25

Every curated Test Lab task declares its allowed setups, exact revisions and stable case IDs. GitHub issue and PR discussions come from the reviewed card. The collector scans shared discussions once per refresh and retains the last complete observation per source. A temporary failure in one discussion can coexist with new evidence from another. Source scopes include the report contract and exact revisions, so a changed instruction or pin does not inherit a previous result.

A structured report describes one setup and verifies its own required cases. GitHub supplies the report authorship and permalink. Reports from unaffiliated contributors are shown for review. An owner of a linked repository or a tester approved for that task can supply evidence that satisfies a hardware cell. A wider campaign can require every named hardware cell before it leaves the queue for new runs. A coverage decision is separate from receiving-team adoption.

The original two FrameLab reports use a narrow legacy adapter, tied to their known discussion, authorized reporter and revision. The previous SQLite state remains available during migration. New tasks use the same structured format without a task-specific parser. A maintainer can also register a reviewed prose report with its exact permalink, author ID, content hash and supported cases. An edit to that report requires a new review.

Mixed revisions, software GPU adapters, malformed or incompatible environments, missing cases, failures and skips cannot satisfy coverage. A reviewer still verifies the raw result and its relevance. The invitation workflow rechecks the open request and its linked reports before sending any approved invitation. It does not use community replies as commands.

Rollback is a revert of the product change. Earlier releases ignore the new source-scope rows in the existing report table.
