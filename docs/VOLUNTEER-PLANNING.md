# Plan parallel volunteer checks

Use this read-only planner for a Test Lab task with more than one hardware need. For example, [PortBridge #54](https://github.com/akimfomin/PortBridge/issues/54) requests separate Radeon and Intel Arc runs for the pinned XCL test.

Run the plan against the published Test Lab.

~~~sh
python -m portbridge.volunteer_plan --task xcl-2126-scratch-coverage
~~~

Add --db and the local catalog path to read a local snapshot. Run refresh-lab first if the local observations are old.

The plan includes the target link, the freshness of its report sources, each hardware cell's coverage, and the number of eligible volunteers. A previous passing report makes someone eligible when the report is approved, covers the same test profile and equipment under an eligible operating system, and explicitly opts in. The planner uses reports from the last 90 days whose sources were checked within the last two hours. The newest consent decision in that scope takes precedence. A covered cell, a pending report review or an unchecked source has no invitation proposal.

If the task requires several vendors, the planner proposes the largest set of distinct volunteers it can match to those cells. Each person appears at most once in the same plan. If the hardware options are alternatives for one check, the plan proposes at most one volunteer. A proposal records the matching public report and leaves the task open for a volunteer to accept.

The planner performs no network writes and sends no invitations. Confirm that the receiving discussion and the pinned task still need a run before acting on a proposal. Keep any outreach within the task's authorization and honor requests to stop.

## Preview a match from explicit consent

Ask volunteers who want one matching GitHub reply to post a one-line profile in the [volunteer thread](https://github.com/akimfomin/PortBridge/issues/112). For example:

```text
PortBridge volunteer v1 | windows-11-ltsc-d3d12 | amd: RX 6700 XT | yes
```

Use one active profile per GitHub account. Edit it to `PortBridge volunteer v1 | paused` or remove it to withdraw. Profiles expire after 90 days. A normal hardware report or a preference to select tasks independently does not enter this matching list. The matcher uses only the author of the consent comment and requires the exact model.

```sh
python -m portbridge.volunteer_requests 118 --scope windows-11-ltsc-d3d12
```

Read the public task before choosing its OS/API scope. The preview reads a fixed PortBridge thread and returns links to matching consent comments. It performs zero writes. Before sending an invitation, recheck the task, the consent and the discussion's invitation history. This preview is separate from the earlier maintainer-run invitation workflow.

## Find compatible Intel reports for human review

```sh
python -m portbridge.tester_discovery
```

The reader checks two public XCL discussions for Intel Arc Wave32 test reports under Windows and links each original result. A compatible report shows prior hardware use. Invitation proposals still depend on the planner's explicit opt-in checks. [XCL dispatch tests](https://github.com/xcl-dev/xcl/pull/2080) · [XCL scratch tests](https://github.com/xcl-dev/xcl/pull/2126)
