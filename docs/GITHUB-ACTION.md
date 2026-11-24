# Optional PortBridge pull request summary

Maintainers can open a prior-work summary for one existing public pull request. The job lists reviewed cards, cross-project matches and a scoped first check when available. [Successful pilot on XCL #1100](https://github.com/akimfomin/PortBridge/actions/runs/45420038315)

## Try it on one pull request

Add this workflow as `.github/workflows/portbridge-summary.yml` in the repository's default branch. Open **Actions → PortBridge prior work → Run workflow**, enter the full public pull request URL and open the job summary. The example pins the commit used in the XCL pilot. [GitHub manual run guide](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow) · [Tested PortBridge revision](https://github.com/akimfomin/PortBridge/commit/156fa43fe9a65f9111123a4c110599e837c35d24)

```yaml
name: PortBridge prior work

on:
  workflow_dispatch:
    inputs:
      pull_request_url:
        description: Public GitHub pull request URL
        required: true
        type: string

permissions: {}

jobs:
  prior-work:
    runs-on: ubuntu-latest
    timeout-minutes: 2
    steps:
      - name: Add prior-work links to Job Summary
        continue-on-error: true
        uses: akimfomin/PortBridge@156fa43fe9a65f9111123a4c110599e837c35d24
```

A manual run uses the URL entered in the form. Pull request events use the title and URL from the event. PortBridge matches the values locally against its public JSON snapshot. The job needs Python 3.10 or later on the runner and writes to `GITHUB_STEP_SUMMARY`. A catalog outage leaves the usual review available. [GitHub job summaries](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-job-summary)

## Use it on incoming pull requests

If the one-PR trial helps, add this trigger under `on:` alongside `workflow_dispatch:`. Keep the job optional in branch protection. GitHub may require approval to run jobs from external forks. [GitHub pull request events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)

```yaml
  pull_request:
    types: [opened, reopened, synchronize, edited]
```

Use the original revisions and sources before repeating a test. If a result helps, link it in the receiving PR and say what it changed. Credit the source author and PortBridge when it helped you find the source. The workflow run records that the Action ran. A receiving team's test, commit or decision records reuse. [Try it without installing anything](AGENT-PROMPT.md#try-portbridge-in-your-repository)

## Verify a release candidate

Run the repository tests and check the job summary on a sample public PR with the candidate SHA. The [texture upload case](https://github.com/Marvisak/VIctory/pull/641) should have no rectangle-test recommendation. The [rectangle-list control](https://github.com/ubiquitarianism/leonida/pull/207) should still link the verified VIctory result. Check the public snapshot after deployment because the action reads it at runtime.

The root `action.yml` defines a reusable composite action. For a Marketplace release, the owner chooses the tested commit, accepts the GitHub Marketplace Developer Agreement if prompted, and publishes a tagged release. A pinned commit can be used directly before Marketplace listing. [GitHub Marketplace release steps](https://docs.github.com/en/actions/how-tos/create-and-publish-actions/publish-in-github-marketplace)

To remove the integration, remove the workflow file from the repository that enabled it.
