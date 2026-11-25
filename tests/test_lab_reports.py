import json
from unittest.mock import patch

from portbridge.catalog import ReadOnlyCatalog
from portbridge.export import export
from portbridge.github import API, RepositoryNotPublic, Unavailable
from portbridge.lab import FRAMELAB_HANDOFF_HEAD, FRAMELAB_RESULTS, TASKS, build_lab
from portbridge.lab_reports import FRAMELAB_TASK, FRAMELAB_TESTER_ID, refresh_reports
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
        with patch("portbridge.lab_reports._Sync._require_public") as public_check, \
                patch("portbridge.lab_reports._Sync._request", side_effect=responses) as request:
            if private:
                public_check.side_effect = RepositoryNotPublic("not public")
            states = refresh_reports(self.catalog, TASKS)
            public_check.assert_called_once_with(REPO, verify_anonymous=True)
            if not private:
                self.assertEqual(request.call_args_list[0].args[0], f"{ISSUE}/comments?per_page=30&page=1")
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
        self.assertEqual((wait["state"], wait["checked_at"], wait["reports"]), ("unavailable", None, []))
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
