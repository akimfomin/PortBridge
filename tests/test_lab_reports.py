from datetime import datetime
from hashlib import sha256
import json
import os
from unittest.mock import patch

from portbridge.catalog import ReadOnlyCatalog
from portbridge.export import export
from portbridge.github import API, RepositoryNotPublic, Unavailable
from portbridge.lab import FRAMELAB_HANDOFF_HEAD, FRAMELAB_RESULTS, TASKS, build_lab
from portbridge.lab_reports import (FRAMELAB_TASK, FRAMELAB_TESTER_ID, coverage_cells, normalize_report,
                                    refresh_reports, report_source, report_sources, scan_reports)
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

    def test_authenticated_scan_rechecks_visibility_and_falls_back_on_scope_errors(self):
        frame = next(task for task in TASKS if task["id"] == FRAMELAB_TASK)
        repo_url = f"{API}/repos/{REPO}"
        visits = []

        def request(sync, url, *_):
            visits.append((sync.context, url))
            if url == repo_url:
                if sync.token and any("/comments?" in path for _, path in visits):
                    return {"private": True, "visibility": "private"}, {}
                return {"private": False, "visibility": "public"}, {}
            return ([comment(1)] if url.startswith(ISSUE + "/comments?") else []), {}

        with patch.dict(os.environ, {"PORTBRIDGE_GITHUB_TOKEN": "test-token"}), \
                patch("portbridge.lab_reports._Sync._request", request):
            states = refresh_reports(self.catalog, [frame], authenticated=True)
        self.assertGreaterEqual(visits.count(("authenticated", repo_url)), 2)
        self.assertEqual(states[frame["id"]]["reports"], [])

        def denied(sync, url, *_):
            if sync.token:
                raise Unavailable("not in token scope", http_status=404)
            if url == repo_url:
                return {"private": False, "visibility": "public"}, {}
            return ([comment(1)] if url.startswith(ISSUE + "/comments?") else []), {}

        with patch.dict(os.environ, {"PORTBRIDGE_GITHUB_TOKEN": "test-token"}), \
                patch("portbridge.lab_reports._Sync._request", denied):
            states = refresh_reports(self.catalog, [frame], authenticated=True)
        self.assertEqual([row["outcome"] for row in states[frame["id"]]["reports"]], ["pass"])

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
        reviewed["reviewed_reports"][row["html_url"]]["cases"] = {**record["cases"], "overlapping-edges": "skip"}
        partial = normalize_report(row, reviewed, source, repo, issue)
        self.assertEqual((partial["authority"], partial["outcome"], partial["opt_in"]), ("approved", "partial", False))
        self.assertEqual(coverage_cells(reviewed, [partial])[0]["state"], "partial")
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

def review_comment(task, source, report, ident, decision="approve", *, association="OWNER"):
    comment = structured_comment(task, source, ident, equipment=task["equipment"][0],
                                 actor_id=4321, association=association)
    digest = sha256(report["body"].replace("\r\n", "\n").encode()).hexdigest()
    comment["body"] = (f"PortBridge test review v1\nTask: {task['id']}\nReport: {report['html_url']}\n"
                       f"Body SHA-256: {digest}\nDecision: {decision}\n\nReviewed the public evidence.")
    return comment


class ThreadReviewTest(CatalogFixture):
    def setUp(self):
        super().setUp()
        self.task = next(task for task in TASKS if task["id"] == "xcl-2126-scratch-coverage")
        self.primary, self.linked = report_sources(self.task)
        self.report = structured_comment(self.task, self.linked, 1, equipment="intel")
        self.approval = review_comment(self.task, self.primary, self.report, 2)

    def read(self, primary, linked=None, *, cached=False):
        sources = {report_source(self.task, self.primary)[1]: primary,
                   report_source(self.task, self.linked)[1]: [self.report] if linked is None else linked}

        def request(url):
            data = sources[url.split("/comments?", 1)[0]]
            if isinstance(data, Exception):
                raise data
            return data, False

        if not cached:
            return scan_reports(self.task, request)
        with patch("portbridge.lab_reports._Sync._require_public"), \
                patch("portbridge.lab_reports._Sync._request", side_effect=lambda url, *_: (request(url)[0], {})):
            state = refresh_reports(self.catalog, [self.task])[self.task["id"]]
        return state["reports"]

    def test_latest_decision_controls_coverage_without_changing_adoption(self):
        revoke = review_comment(self.task, self.primary, self.report, 3, "revoke")
        older_edited = {**self.approval, "updated_at": "2026-11-25T03:00:00Z"}
        for cached in (True, False):
            with self.subTest(cached=cached):
                reports = self.read([self.approval], cached=cached)
                self.assertEqual(len(reports), 1)
                self.assertEqual(reports[0]["review"]["url"], self.approval["html_url"])
                self.assertEqual(reports[0]["author"], self.report["user"]["login"])
                self.assertEqual(coverage_cells(self.task, reports)[1]["state"], "covered")
                reports = self.read([revoke, older_edited], cached=cached)
                self.assertEqual(reports[0]["review"]["decision"], "revoke")
                self.assertEqual(coverage_cells(self.task, reports)[1]["state"], "reported")
        card = build_lab(self.catalog, task=self.task["id"])["tasks"][0]
        self.assertEqual(card["adoption"], "pending")
        self.assertEqual(card["report_sync"]["reports"], reports)

    def test_source_binding_identity_and_original_body_are_required(self):
        for approval in (
            {**self.approval, "author_association": "MEMBER"},
            {**self.approval, "user": {**self.approval["user"], "type": "Bot"}},
            {**self.approval, "minimized": True},
            {**self.approval, "html_url": self.report["html_url"]},
            {**self.approval, "body": self.approval["body"].replace(self.task["id"], "another-task")},
            {**self.approval, "body": "\n".join("> " + line for line in self.approval["body"].splitlines())},
            {**self.approval, "body": self.approval["body"].replace("Decision: approve", "Decision: approve\nDecision: revoke")},
            {**self.approval, "body": self.approval["body"].replace(self.report["html_url"],
                                                      "https://github.com/someone/else/issues/1#issuecomment-1")},
        ):
            with self.subTest(approval=approval["body"].splitlines()[1]):
                self.assertNotIn("review", self.read([approval])[0])
        other_thread = review_comment(self.task, self.linked, self.report, 3)
        self.assertNotIn("review", self.read([], [self.report, other_thread])[0])
        edited = {**self.report, "body": self.report["body"] + "\n\nOutput added."}
        self.assertNotIn("review", self.read([self.approval], [edited])[0])
        restored = {**self.report, "updated_at": "2026-11-25T03:00:00Z"}
        self.assertNotIn("review", self.read([self.approval], [restored])[0])

    def test_new_approval_cannot_promote_retained_evidence_until_source_is_checked(self):
        outage = Unavailable("temporary", http_status=503)
        with patch("portbridge.lab_reports.datetime") as clock:
            clock.now.return_value = datetime.fromisoformat("2026-11-25T02:00:01.5+00:00")
            self.assertNotIn("review", self.read([], cached=True)[0])
            clock.now.return_value = datetime.fromisoformat("2026-11-25T02:00:07+00:00")
            stale = self.read([self.approval], outage, cached=True)
            self.assertNotIn("review", stale[0])
            self.assertEqual(coverage_cells(self.task, stale)[1]["state"], "reported")
            clock.now.return_value = datetime.fromisoformat("2026-11-25T02:00:08+00:00")
            fresh = self.read([self.approval], cached=True)
            self.assertEqual(coverage_cells(self.task, fresh)[1]["state"], "covered")

    def test_cache_retains_temporarily_unavailable_review_and_clears_deleted_or_private_review(self):
        original = self.read([self.approval], cached=True)
        self.assertEqual(original, self.read(Unavailable("temporary", http_status=503), cached=True))
        self.assertNotIn("review", self.read([], cached=True)[0])
        self.assertEqual(original, self.read([self.approval], cached=True))
        self.assertNotIn("review", self.read(RepositoryNotPublic("no longer public"), cached=True)[0])
        self.assertEqual(original, self.read([self.approval], cached=True))
        hidden = Unavailable("no longer publicly readable", http_status=404)
        self.assertNotIn("review", self.read(hidden, cached=True)[0])
        self.assertEqual(self.read([self.approval], hidden, cached=True), [])
