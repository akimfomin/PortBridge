# Public discovery and reviewed capability evidence

PortBridge uses three fixed tracker feeds and the existing bounded GitHub search during scheduled synchronization. It keeps normalized repository names, provenance, fetch timestamps and cache validators. The regular index continues to follow the reviewed repository registry. A lead can come from multiple sources and still needs a scope and license review.

An external outage should leave the previous useful feed available. The SQLite cache records the outcome for each source separately. Reusing the Pages schedule keeps discovery and published metadata on the same deployment path, with a separate six-hour interval for these feeds and the existing GitHub rate-limit handling for Search.

Capability evidence lives in a reviewed file. Each entry names a technical area, a specific test or behavior, the level of evidence, and its primary source. Grouping a capability with its evidence gives agents and people enough context to identify a possible transfer without ranking projects by overall progress.
