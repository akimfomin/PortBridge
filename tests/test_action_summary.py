import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
from urllib.error import URLError

from portbridge import action_summary


class ActionSummaryTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.event = root / "event.json"
        self.report = root / "summary.md"
        self.env = {
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(self.event),
            "GITHUB_STEP_SUMMARY": str(self.report),
        }
        self.title = "$(example) <script> [link] @everyone"
        self.source = "https://github.com/example/port/pull/42"
        self.event.write_text(json.dumps({"pull_request": {
            "title": self.title, "html_url": self.source,
            "body": "Secret body omitted from the summary and query",
        }}), encoding="utf-8")

    def test_appends_read_only_review_to_job_summary(self):
        response = {
            "catalog_status": "partial",
            "problems": [{"id": "PB-0001", "title": "Folded guard", "solutions": [
                {"project": "continued", "source_url": "https://github.com/example/continued/pull/20"},
            ]}],
            "matches": [{"right": {"title": "<img src=x>\n## Other @everyone", "url":
                                    "https://github.com/example/reforge/issues/21#issuecomment-2"}}],
            "observations": [{"title": "Host build", "url": "https://github.com/example/port/issues/4"},
                             {"title": "Private external link", "url": "https://example.invalid/hidden"}],
            "first_check": {"revision": "b077ec9", "platforms": ["Windows 11"],
                            "url": "https://github.com/example/reforge/actions/runs/34/job/56"},
            "next_step": "Reproduce the reported test in the target configuration.",
        }
        self.report.write_text("Existing summary content\n\n", encoding="utf-8")
        with mock.patch.object(action_summary, "public_preflight", return_value=response) as preflight:
            self.assertEqual(action_summary.main(self.env), 0)
        preflight.assert_called_once_with(q=self.title, url=self.source, limit=5)
        markdown = self.report.read_text(encoding="utf-8")
        self.assertTrue(markdown.startswith("Existing summary content\n\n## PortBridge"))
        self.assertIn("#/problems/PB-0001", markdown)
        self.assertIn("https://github.com/example/continued/pull/20", markdown)
        self.assertIn("https://github.com/example/reforge/issues/21#issuecomment-2", markdown)
        self.assertIn("https://github.com/example/port/issues/4", markdown)
        self.assertIn("https://github.com/example/reforge/actions/runs/34/job/56", markdown)
        self.assertIn("revision `b077ec9`, Windows 11", markdown)
        self.assertIn("The public snapshot may be incomplete", markdown)
        self.assertNotIn("<img", markdown)
        self.assertNotIn("@everyone", markdown)
        self.assertNotIn(self.title, markdown)
        self.assertNotIn("Secret body", markdown)
        self.assertNotIn("example.invalid", markdown)

    def test_unavailable_catalog_is_advisory(self):
        with mock.patch.object(action_summary, "public_preflight", side_effect=URLError("private error")):
            self.assertEqual(action_summary.main(self.env), 0)
        markdown = self.report.read_text(encoding="utf-8")
        self.assertIn("The public catalog is unavailable", markdown)
        self.assertNotIn("private error", markdown)

    def test_empty_snapshot_is_distinct_from_unavailable(self):
        response = {"problems": [], "matches": [], "observations": [], "catalog_status": "ok"}
        with mock.patch.object(action_summary, "public_preflight", return_value=response):
            self.assertEqual(action_summary.main(self.env), 0)
        self.assertIn("No related work was found", self.report.read_text(encoding="utf-8"))

    def test_successful_snapshot_reports_an_unindexed_pull_request(self):
        result = {"origin_url": self.source, "indexed": False, "catalog_status": "ok",
                  "problems": [], "matches": [], "observations": []}
        markdown = action_summary.render_report(result)
        self.assertIn("absent from the public index", markdown)
        self.assertIn("current details on GitHub", markdown)

    def test_privileged_event_and_non_github_url_never_scan(self):
        with mock.patch.object(action_summary, "public_preflight") as preflight:
            self.assertEqual(action_summary.main({**self.env, "GITHUB_EVENT_NAME": "pull_request_target"}), 0)
            self.event.write_text(json.dumps({"pull_request": {
                "title": "Valid title", "html_url": "https://github.com.invalid/example/port/pull/42",
            }}), encoding="utf-8")
            self.assertEqual(action_summary.main(self.env), 0)
        preflight.assert_not_called()
        markdown = self.report.read_text(encoding="utf-8")
        self.assertIn("runs on GitHub pull request events", markdown)
        self.assertIn("The pull request event could not be read", markdown)

    def test_oversized_event_and_missing_summary_do_not_scan(self):
        self.event.write_bytes(b"x" * (action_summary.EVENT_LIMIT + 1))
        with mock.patch.object(action_summary, "public_preflight") as preflight:
            self.assertEqual(action_summary.main(self.env), 0)
            self.assertEqual(action_summary.main({"GITHUB_EVENT_NAME": "pull_request"}), 0)
        preflight.assert_not_called()
        self.assertIn("The pull request event could not be read", self.report.read_text(encoding="utf-8"))
