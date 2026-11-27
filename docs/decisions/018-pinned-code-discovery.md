# ADR 018 · Search code as a separate source of evidence

**Status** Proposed for deployment. **Date** 2026-11-27.

PortBridge matches navigation and discussion metadata well enough to produce candidates. Some references that could answer an investigation are indexed neither as issues nor as PRs. The public code layer is an advisory stage that can return an exact file and line.

The first corpus covers a small set of reviewed, licensed public files. Each entry names a GitHub repository, full commit SHA, path and license. The scheduled job checks the list and downloads only missing files. GitHub redirects, non-text files, files over 1.2 MB and entries outside the manifest are excluded. The database stores searchable identifiers and line numbers. Raw files stay out of the database and export. The current catalog checkpoint schema is retained so the previous release can read it on rollback.

Candidates rank by rare technical identifiers and local co-occurrence. Exact URL preflight forwards bounded body signals from the saved public origin. A fresh origin requires the existing explicit Discovery lookup or a catalog refresh. Text queries can search immediately. CLI, MCP preflight and the PR Action expose candidate links. Browser Search continues to use historical and reviewed catalog data. Radar can queue a code lead for review without granting it high confidence, creating an external message or assigning a Lab task.

A changed pin or license gets a different Radar input fingerprint. Candidates referring to a retired pin become stale. A failed fetch retains the other reviewed pins and the current public output gives both indexed and expected counts. The exporter and release gate enforce the same snapshot size limit.

Local check:

```powershell
python -m portbridge.code_search --db .portbridge/code-demo.sqlite3 --refresh
python -m portbridge.code_search --db .portbridge/code-demo.sqlite3 --q GetDiskFreeSpaceA
python -m portbridge.preflight --url https://github.com/KytyPS5/KytyPS5/pull/2575
```

Adding a source requires reviewing its license and paths and pinning a full SHA. Corpus growth should be evaluated on a fresh blind sample. A coincidentally similar line should be checked with a distinct negative control in the receiving project. Live branch history and diffs, an independent mechanism model, broad browser code search and automatic verification remain follow-up work.
