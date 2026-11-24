# Optional PortBridge pull request summary

Maintainers can add a job that searches for prior work when someone opens or updates a pull request. It lists relevant catalog cards, possible matches, and a first check when one is available. Open the workflow run under **Actions** to read the job summary. The result is advisory and can be incomplete.

If the maintainers want to try the Action, add the following workflow as `.github/workflows/portbridge-summary.yml`. This example pins the tested v0.1.1 commit. Keep the job optional in branch protection. [v0.1.1 release](https://github.com/akimfomin/PortBridge/releases/tag/v0.1.1) · [GitHub Marketplace listing](https://github.com/marketplace/actions/portbridge-prior-work-summary) · [Pinning actions to a commit](https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions)

```yaml
name: PortBridge prior work

on:
  pull_request:
    types: [opened, reopened, synchronize, edited]

permissions: {}

jobs:
  prior-work:
    runs-on: ubuntu-latest
    timeout-minutes: 2
    steps:
      - name: Add prior-work links to Job Summary
        continue-on-error: true
        uses: akimfomin/PortBridge@7b1dbdedccccdf75b257c130e970344e3434d0e4 # v0.1.1
```

The action reads the title and GitHub PR URL from `GITHUB_EVENT_PATH`. It uses those values locally against PortBridge's public JSON snapshot. The snapshot fetch does not include the title or PR URL. The job uses the runner's Python 3.10 or newer and needs no secrets, repository checkout, or installed Python packages. It writes only to `GITHUB_STEP_SUMMARY`. If the snapshot cannot be read, the summary tells the reviewer to continue the usual review. [Composite action metadata](https://docs.github.com/en/actions/reference/workflows-and-actions/metadata-syntax#runs-for-composite-actions) · [GitHub job summaries](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-job-summary)

Use `pull_request` as shown. The action works with a public GitHub PR URL and declines other event types. Keep any unrelated workflow that runs contributor code separate from this job. For external contributions, GitHub may require a maintainer to approve running the workflow. [GitHub pull request events and forks](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)

The summary distinguishes confirmed catalog sources from possible matches. The first check includes the reported outcome and scope. Separate history indicators show whether the source repository's older records and recent changes were indexed.

For a pilot, open the summary for one public pull request. If a source helped the review, link it in that PR and state what changed, such as a test the team ran or work it chose to reuse. Credit the source author and link PortBridge when it helped find the source. The job summary records that the Action ran. The receiving team's linked decision or test report records that the result was useful. [One-PR pilot and setup-free alternative](AGENT-PROMPT.md#try-portbridge-in-your-repository)

## Verify a release candidate

Run the repository tests and check the job summary on a sample public PR with the candidate SHA. The [texture upload case](https://github.com/Marvisak/VIctory/pull/641) should have no rectangle-test recommendation. The [rectangle-list control](https://github.com/ubiquitarianism/leonida/pull/207) should still link the verified VIctory result. Check the public snapshot after deployment because the action reads it at runtime.

The root `action.yml` defines a reusable composite action. For a Marketplace release, the owner chooses the tested commit, accepts the GitHub Marketplace Developer Agreement if prompted, and publishes a tagged release. A pinned commit can be used directly before Marketplace listing. [GitHub Marketplace release steps](https://docs.github.com/en/actions/how-tos/create-and-publish-actions/publish-in-github-marketplace)

To remove the integration, remove the workflow file from the repository that enabled it.
