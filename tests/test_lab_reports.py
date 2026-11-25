from hashlib import sha256
import json
from unittest.mock import patch

from portbridge.catalog import ReadOnlyCatalog
from portbridge.export import export
from portbridge.github import API, RepositoryNotPublic, Unavailable
from portbridge.lab import FRAMELAB_HANDOFF_HEAD, FRAMELAB_RESULTS, TASKS, build_lab
from portbridge.lab_reports import (FRAMELAB_TASK, FRAMELAB_TESTER_ID, coverage_cells, normalize_report,
                                    refresh_reports, report_source, report_sources)
from portbridge.mcp import PortBridgeMCP

from test_portbridge import CatalogFixture


REPO = "5headsmartbtw/leonida-framelab"
ISSUE = f"{API}/repos/{REPO}/issues/15"
BODY = """## Vulkan handoff result

The run used Khronos synchronization validation enabled.
- Exact unmodified source revision: {revision}.
- GPU: AMD, Vulkan vendor/device 1002:{device}.
- OS: Windows 11.
- Driver: 26.11.1.
- Vulkan SDK 1.4.363.1.

| Queue families | Semaphore | Exact image readback | Consumer fence | Result |
| --- | --- | --- | --- | --- |
| 0 → 0 (two distinct queues) | Binary | 64/64 pixels matched | Completed | PASS |
| 0 → 0 (two distinct queues) | Timeline | 64/64 pixels matched | Completed | PASS |
| 0 → 1 | Binary | 64/64 pixels matched | Completed | PASS |
| 0 → 1 | Timeline | 64/64 pixels matched | Completed | PASS |

Validation: synchronization enabled; warnings=0; errors=0; skips=0

## Reproduction
Previous environment failed. That was a different run.
"""


def comment(ident, *, device="1114", revision=FRAMELAB_HANDOFF_HEAD, actor=FRAMELAB_TESTER_ID):
    return {"id": ident, "html_url": f"{FRAMELAB_RESULTS}#issuecomment-{ident}", "issue_url": ISSUE,
            "url": f"{API}/repos/{REPO}/issues/comments/{ident}",
            "user": {"type": "User", "login": "test-reporter", "id": actor},
            "created_at": f"2026-11-25T01:01:{ident:02}Z", "body": BODY.format(revision=revision, device=device)}


class LabReportsTest(CatalogFixture):
    def refresh(self, *responses, private=False):
        def request_page(url, resource, etag):
            if url.startswith(ISSUE + "/comments?"):
                response = next(expected)
                if isinstance(response, Exception):
                    raise response
                return response
            self.assertTrue(url.startswith(f"{API}/repos/{REPO}/issues/12/comments?"))
            return [], {}

        expected = iter(responses)
        frame = next(task for task in TASKS if task["id"] == FRAMELAB_TASK)
        with patch("portbridge.lab_reports._Sync._require_public") as public_check, \
                patch("portbridge.lab_reports._Sync._request", side_effect=request_page) as request:
            if private:
                public_check.side_effect = RepositoryNotPublic("not public")
            states = refresh_reports(self.catalog, [frame])
            public_check.assert_called_with(REPO, verify_anonymous=True)
            if not private:
                self.assertIn(f"{ISSUE}/comments?per_page=30&page=1",
                              [call.args[0] for call in request.call_args_list])
        return states[FRAMELAB_TASK]

    def card(self):
        return build_lab(self.catalog, task=FRAMELAB_TASK)["tasks"][0]

    def test_report_updates_status_and_shared_snapshot_without_duplication(self):
        first, second = comment(1), comment(2, device="13c0")
        self.assertEqual(self.card()["report_sync"]["state"], "unchecked")
        initial = self.refresh(([first, second], {}))
        self.assertEqual(initial["state"], "fresh")
        self.assertEqual([r["outcome"] for r in initial["reports"]], ["pass", "pass"])
        self.assertEqual(len({r["hardware"] for r in initial["reports"]}), 2)
        self.assertEqual(self.card()["status"], "awaiting_review")
        self.assertEqual(self.card()["adoption"], "pending")
        self.assertEqual(build_lab(self.catalog, status="needs_run", task=FRAMELAB_TASK)["tasks"], [])

        retried = self.refresh(([first, second], {"Link": '<unused>; rel="next"'}), ([second], {}))
        self.assertEqual(initial["reports"], retried["reports"])
        static = export(self.catalog, self.workspace / "site")
        snapshot = json.loads((static / "data/lab.json").read_bytes())
        tool = PortBridgeMCP(ReadOnlyCatalog(self.catalog.path))
        response = tool.run_tool({"name": "portbridge_lab", "arguments": {"task": FRAMELAB_TASK}})
        self.assertIn(self.card(), snapshot["tasks"])
        self.assertEqual(response["structuredContent"]["tasks"], [self.card()])

    def test_bad_source_incomplete_scope_and_failed_result_do_not_advance(self):
        quoted = comment(4)
        quoted["body"] = "\n".join("> " + line for line in quoted["body"].splitlines())
        same_queue = comment(5)
        same_queue["body"] = same_queue["body"].replace(" (two distinct queues)", "")
        failing = comment(6, device="13c0")
        failing["body"] = failing["body"].replace("| Completed | PASS |", "| Aborted | FAIL |", 1)
        disallowed = comment(7)
        disallowed["issue_url"] = ISSUE.replace("/15", "/12")
        fenced = comment(9)
        fenced["body"] = "~~~\n" + "\x60" * 3 + "\n" + fenced["body"] + "\n~~~"
        missing_setup = comment(10)
        missing_setup["body"] = missing_setup["body"].replace("- Driver: 26.11.1.", "")
        observed = self.refresh(([comment(1, actor=123), comment(2, revision="0" * 40),
                                  quoted, same_queue, failing, disallowed, fenced, missing_setup], {}))
        self.assertEqual([r["outcome"] for r in observed["reports"]], ["partial", "fail", "partial"])
        self.assertEqual(self.card()["status"], "needs_run")
        passing = comment(8)
        self.refresh(([passing, failing], {}))
        self.assertEqual(self.card()["status"], "needs_run")

    def test_partial_source_failure_retains_previous_scan_then_complete_scan_removes_it(self):
        wait = self.refresh(Unavailable("temporarily unavailable", http_status=503))
        self.assertEqual((wait["state"], wait["reports"]), ("stale", []))
        primary = next(source for source in wait["sources"] if source["url"] == FRAMELAB_RESULTS)
        self.assertEqual((primary["state"], primary["checked_at"]), ("unavailable", None))
        initial = self.refresh(([comment(1)], {}))
        stale = self.refresh(([], {"Link": '<unused>; rel="next"'}), Unavailable("rate limited"))
        self.assertEqual(stale["state"], "stale")
        self.assertEqual(stale["checked_at"], initial["checked_at"])
        self.assertEqual(stale["reports"], initial["reports"])
        self.assertEqual(self.card()["status"], "awaiting_review")
        cleared = self.refresh(([], {}))
        self.assertEqual((cleared["state"], cleared["reports"]), ("fresh", []))
        self.assertEqual(self.card()["status"], "needs_run")

    def test_cached_reports_do_not_cross_revision_or_visibility(self):
        self.refresh(([comment(1)], {}))
        frame = next(task for task in TASKS if task["id"] == FRAMELAB_TASK)
        with patch.dict(frame["revisions"][0], {"sha": "0" * 40}):
            self.assertEqual(self.card()["report_sync"]["state"], "unchecked")
        removed = self.refresh(private=True)
        self.assertEqual((removed["state"], removed["reports"]), ("unavailable", []))


def structured_comment(task, source, ident, *, equipment, actor_id=9876, association="NONE", cases=None):
    repo, issue = report_source(task, source)
    hardware = {"amd": ("AMD Radeon RX 9070 XT", "1002:7550"),
                "intel": ("Intel Arc B580", "8086:e20b"),
                "nvidia": ("NVIDIA RTX 4090", "10de:2684"),
                "cpu": ("Intel Core i5-13600KF", "")}
    model, pci = hardware[equipment]
    fields = ["PortBridge test report v1", f"Task: {task['id']}",
              "Revisions: " + " ".join(row["sha"] for row in task["revisions"]), f"Equipment: {equipment}",
              f"Hardware: {model}", f"OS: {task['os'][0]} 25H2", "Toolchain: Python 3.12.10 or DXC 1.9",
              "Opt-in: yes"]
    if pci:
        fields.extend((f"PCI: {pci}", "Driver: 1.2.3"))
    fields.extend(f"Case: {name} = {outcome}" for name, outcome in
                  (cases or {name: "pass" for name in task["report_cases"]}).items())
    return {"id": ident, "html_url": f"{source}#issuecomment-{ident}", "issue_url": issue,
            "url": f"{API}/repos/{repo}/issues/comments/{ident}", "author_association": association,
            "user": {"type": "User", "login": f"volunteer-{actor_id}", "id": actor_id},
            "created_at": f"2026-11-25T02:00:{ident:02}Z", "body": "\n".join(fields)}


class StructuredLabReportsTest(CatalogFixture):
    def test_all_curated_tasks_accept_only_their_exact_structured_inputs(self):
        for task in TASKS:
            source = report_sources(task)[0]
            repo, issue = report_source(task, source)
            with self.subTest(task=task["id"]):
                result = structured_comment(task, source, 1, equipment=task["equipment"][0])
                report = normalize_report(result, task, source, repo, issue)
                self.assertEqual((report["outcome"], report["authority"]), ("pass", "community"))
                self.assertEqual(report["revisions"], [row["sha"] for row in task["revisions"]])
                self.assertTrue(report["opt_in"])
                result["body"] = result["body"].replace(task["revisions"][0]["sha"], "0" * 40)
                self.assertIsNone(normalize_report(result, task, source, repo, issue))

    def test_partial_skips_and_malformed_hardware_never_count_as_pass(self):
        task = next(task for task in TASKS if task["id"] == "xcl-2126-scratch-coverage")
        source = report_sources(task)[0]
        repo, issue = report_source(task, source)
        row = structured_comment(task, source, 1, equipment="intel", cases={"skip-middle-piece": "skip"})
        self.assertEqual(normalize_report(row, task, source, repo, issue)["outcome"], "partial")
        for new_body in (
            row["body"].replace("8086:e20b", "1002:e20b"),
            row["body"].replace("Intel Arc B580", "WARP"),
            row["body"].replace("Windows 25H2", "Linux 25H2"),
            row["body"] + "\nCase: skip-middle-piece = pass",
            "\n".join("> " + line for line in row["body"].splitlines()),
        ):
            self.assertIsNone(normalize_report({**row, "body": new_body}, task, source, repo, issue))

    def test_combined_coverage_uses_both_sources_and_preserves_partial_failure(self):
        task = next(task for task in TASKS if task["id"] == "xcl-2126-scratch-coverage")
        primary, linked = report_sources(task)
        amd = structured_comment(task, primary, 1, equipment="amd", association="OWNER")
        intel = structured_comment(task, linked, 2, equipment="intel", association="OWNER")
        community = structured_comment(task, linked, 3, equipment="intel")

        def refresh(primary_reports, linked_reports):
            def request(url, resource, etag):
                data = primary_reports if "/issues/54/comments" in url else linked_reports
                if isinstance(data, Exception):
                    raise data
                return data, {}
            with patch("portbridge.lab_reports._Sync._require_public"), \
                    patch("portbridge.lab_reports._Sync._request", side_effect=request):
                refresh_reports(self.catalog, [task])
            return build_lab(self.catalog, task=task["id"])["tasks"][0]

        partial = refresh([amd], [community])
        self.assertEqual(partial["status"], "needs_run")
        self.assertEqual([cell["state"] for cell in partial["coverage"]], ["covered", "reported"])
        full = refresh([amd], [community, intel])
        self.assertEqual(full["status"], "awaiting_review")
        self.assertEqual(full["adoption"], "pending")
        self.assertEqual(len(full["report_sync"]["reports"]), 3)
        retained = refresh([], Unavailable("temporarily unavailable", http_status=503))
        self.assertEqual([cell["state"] for cell in retained["coverage"]], ["missing", "covered"])
        self.assertEqual(retained["report_sync"]["state"], "stale")
        self.assertEqual(retained["status"], "needs_run")

    def test_legacy_and_reviewed_prose_are_bound_to_exact_contracts(self):
        frame = next(task for task in TASKS if task["id"] == FRAMELAB_TASK)
        changed_frame = {**frame, "report_cases": frame["report_cases"] + ["new-control"]}
        self.assertIsNone(normalize_report(comment(1), changed_frame, FRAMELAB_RESULTS, REPO, ISSUE))

        task = next(task for task in TASKS if task["id"] == "xcl-2126-scratch-coverage")
        source = report_sources(task)[1]
        repo, issue = report_source(task, source)
        row = structured_comment(task, source, 2, equipment="amd")
        row["body"] = "Verified free-form report with the two published synthetic tests."
        record = next(iter(task["reviewed_reports"].values()))
        reviewed = {**task, "reviewed_reports": {row["html_url"]: {**record, "actor_id": row["user"]["id"],
                    "body_sha256": sha256(row["body"].encode()).hexdigest()}}}
        self.assertEqual(normalize_report(row, reviewed, source, repo, issue)["authority"], "approved")
        row["body"] += " An edit requires a new review."
        self.assertIsNone(normalize_report(row, reviewed, source, repo, issue))

    def test_edited_approved_outcome_supersedes_a_newer_created_report(self):
        task = next(task for task in TASKS if task["id"] == "xcl-2126-scratch-coverage")
        source = report_sources(task)[0]
        repo, issue = report_source(task, source)
        old = structured_comment(task, source, 1, equipment="amd", association="OWNER",
                                 cases={"overlapping-edges": "fail"})
        old["updated_at"] = "2026-11-25T03:00:00Z"
        latest = structured_comment(task, source, 2, equipment="amd", association="OWNER")
        reports = [normalize_report(row, task, source, repo, issue) for row in (old, latest)]
        self.assertEqual(coverage_cells(task, reports)[0]["state"], "contradicted")
