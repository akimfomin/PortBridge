# Contributing to PortBridge

PortBridge helps independent Xbox Series compatibility teams share fixes and evidence. You can contribute from any project and keep the discussion in the repository where the work belongs.

[Quick start in English](docs/QUICKSTART.md) · [Русский](README.ru.md)

## Share a result

1. Search by the exact error, shader instruction, or PR number. Open the original links and check their revisions and scope. [Search PortBridge](https://akimfomin.github.io/PortBridge/)
2. Choose a test you can reproduce. Record the project and exact commit, platform and graphics backend, test input, expected result, actual result, and limits.
3. Submit one report with its original source and attribution. Include negative findings if they will save another team a repeat investigation. [Evidence form](https://github.com/akimfomin/PortBridge/issues/new?template=evidence.yml)
4. If it helps a second project, post the link in the relevant existing issue or PR with a specific proposed check or patch. Keep the resulting decision or change linked from the report.

Public primary-source links and synthetic fixtures are welcome. Pin the source revision and credit the author. For reused code or fixtures, record their origin and applicable license, confirm it permits the reuse, and keep its required notices.

Keep game files, executables, proprietary SDK files, keys, credentials, and private logs out of contributions. Leave out download links to leaked or restricted materials and instructions for bypassing protection. [Publication rules](docs/PUBLISHING.md#происхождение-материалов-и-жалобы)

## Suggest an improvement

Use the feedback form to propose a tracked repository, correct a search result, link related work, or improve the agent or two-team workflow. Include a public source and describe what a useful result would look like. English helps teams review a report together. Source links can be in any language. [Feedback form](https://github.com/akimfomin/PortBridge/issues/new?template=idea.yml)

## Review or pick up work

Check the current work and its sources before starting. Distinguish an author's report, a CI result, a source inspection, and an independent reproduction. Check both the receiving project and the exact revision before calling a result transferable. [Porting work log](docs/PORTING-WORK.md)

For code changes to PortBridge, read [AGENTS.md](AGENTS.md), keep the change scoped, and run `python -m unittest discover -s tests -v`.
