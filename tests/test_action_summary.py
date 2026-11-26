import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
from io import BytesIO
from urllib.error import HTTPError, URLError

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
        resolver = mock.patch.object(action_summary, "public_pr_head", return_value="b" * 40)
        self.resolve = resolver.start()
        self.addCleanup(resolver.stop)
        self.event.write_text(json.dumps({"repository": {"private": False}, "pull_request": {
            "base": {"repo": {"private": False}}, "head": {"sha": "a" * 40},
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
            "observations": [
                {"title": "Unrelated D3D12 adapter selection", "url": "https://github.com/LeonidaReforge/Leonida/pull/135"},
                {"title": "Unrelated multi-warp barrier", "url": "https://github.com/ivall/xcl/commit/0c02b87b267142801e6843563988bf7ac5f6a2e7"},
            ],
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
        self.assertNotIn("Other public observations", markdown)
        for observation in response["observations"]:
            self.assertNotIn(observation["url"], markdown)
        self.assertIn("https://github.com/example/reforge/actions/runs/34/job/56", markdown)
        self.assertIn("revision `b077ec9`, Windows 11", markdown)
        self.assertIn("The public snapshot may be incomplete", markdown)
        self.assertNotIn("<img", markdown)
        self.assertNotIn("@everyone", markdown)
        self.assertNotIn(self.title, markdown)
        self.assertNotIn("Secret body", markdown)

    def test_manual_run_uses_the_selected_public_pull_request(self):
        self.event.write_text(json.dumps({"inputs": {"pull_request_url": " " + self.source + " "}}), encoding="utf-8")
        env = {**self.env, "GITHUB_EVENT_NAME": "workflow_dispatch"}
        response = {"problems": [], "matches": [], "catalog_status": "ok"}
        with mock.patch.object(action_summary, "public_preflight", return_value=response) as preflight:
            self.assertEqual(action_summary.main(env), 0)
        preflight.assert_called_once_with(q="", url=self.source, limit=5)
        self.assertIn("No related work was found", self.report.read_text(encoding="utf-8"))

    def test_manual_run_rejects_invalid_and_missing_inputs_without_a_scan(self):
        env = {**self.env, "GITHUB_EVENT_NAME": "workflow_dispatch"}
        with mock.patch.object(action_summary, "public_preflight") as preflight:
            for event in ({}, {"inputs": {"pull_request_url": "https://github.com.invalid/example/port/pull/42"}},
                          {"inputs": {"pull_request_url": 42}}):
                self.event.write_text(json.dumps(event), encoding="utf-8")
                self.assertIn("Enter a public GitHub pull request URL", action_summary.summary(env))
        preflight.assert_not_called()

    def test_only_unscoped_observations_do_not_suggest_a_next_step(self):
        response = {"problems": [], "matches": [], "observations": [
            {"title": "Unrelated D3D12 adapter selection", "url": "https://github.com/LeonidaReforge/Leonida/pull/135"},
        ], "next_step": "Investigate the result"}
        markdown = action_summary.render_report(response)
        self.assertIn("No related work was found", markdown)
        self.assertNotIn("Investigate the result", markdown)

    def test_unavailable_catalog_is_advisory(self):
        with mock.patch.object(action_summary, "public_preflight", side_effect=URLError("private error")):
            self.assertEqual(action_summary.main(self.env), 0)
        markdown = self.report.read_text(encoding="utf-8")
        self.assertIn("The public catalog is unavailable", markdown)
        self.assertNotIn("private error", markdown)

    def test_report_prefers_reviewed_english_editorial_text(self):
        result = {"problems": [{"id": "PB-0001", "title": "Original title", "solutions": [],
                                "translations": {"en": {"title": "Translated title"}}}],
                  "matches": [], "observations": [], "first_check": {
                      "url": "https://github.com/example/port/pull/42", "observed": "Original observation",
                      "outcome": "passed", "translations": {"en": {"observed": "Translated observation"}},
                  }}
        markdown = action_summary.render_report(result)
        self.assertIn("Translated title", markdown)
        self.assertIn("Translated observation", markdown)
        self.assertNotIn("Original", markdown)

    def test_empty_snapshot_is_distinct_from_unavailable(self):
        response = {"problems": [], "matches": [], "observations": [], "catalog_status": "ok"}
        with mock.patch.object(action_summary, "public_preflight", return_value=response):
            self.assertEqual(action_summary.main(self.env), 0)
        self.assertIn("No related work was found", self.report.read_text(encoding="utf-8"))

    def test_unknown_receiver_gets_a_bounded_health_note_and_reason(self):
        result = {"origin_url": self.source, "catalog_status": "ok", "indexed": False,
                  "problems": [], "matches": [], "source_coverage": [{"slug": str(i)} for i in range(100)],
                  "discovery": {"empty_reason": "There is no saved external search for this link."}}
        markdown = action_summary.render_report(result)
        self.assertIn(self.source, markdown)
        self.assertIn("data/health.json", markdown)
        self.assertIn("no saved external search", markdown)
        self.assertLess(len(markdown), 700)

    def test_runner_outputs_and_privileged_event_with_explicit_input(self):
        output = self.report.parent / "outputs"
        env = {**self.env, "GITHUB_OUTPUT": str(output), "PORTBRIDGE_PR_URL": self.source}
        with mock.patch.object(action_summary, "public_preflight", side_effect=[
                URLError("unavailable"), {"problems": [], "matches": []}]) as preflight:
            for overrides in ({"GITHUB_EVENT_NAME": "pull_request_target"}, {"PORTBRIDGE_PR_URL": "wrong"},
                              {"GITHUB_STEP_SUMMARY": ""}, {}, {}):
                self.assertEqual(action_summary.main({**env, **overrides}), 0)
            self.assertEqual(preflight.call_count, 2)
        self.assertEqual(output.read_text(encoding="utf-8").splitlines(), [
            "status=skipped", "status=invalid_input", "status=summary_unavailable", "status=unavailable", "status=reported"])

    def test_replay_uses_the_original_event_revision_and_url(self):
        revision = "a" * 40
        event = json.loads(self.event.read_text(encoding="utf-8"))
        event["pull_request"]["head"]["sha"] = revision
        self.event.write_text(json.dumps(event), encoding="utf-8")
        report = {"origin_url": "https://github.com/legacy/alias/pull/42", "problems": [], "matches": []}
        with mock.patch.object(action_summary, "public_preflight", return_value=report):
            first = action_summary.summary(self.env)
            self.assertEqual(first, action_summary.summary(self.env))
            manual = action_summary.summary({**self.env, "PORTBRIDGE_PR_URL": self.source})
        self.assertIn(self.source, first)
        self.assertNotIn("legacy/alias", first)
        self.assertIn(revision, first)
        self.assertNotIn("PR event head", manual)
        self.assertIn("Public PR head: `" + "b" * 40, manual)
        self.resolve.assert_called_once_with(self.source)

    def test_private_and_unpinned_events_do_not_access_the_catalog(self):
        event = json.loads(self.event.read_text(encoding="utf-8"))
        with mock.patch.object(action_summary, "public_preflight") as preflight:
            for key, value in ((("repository", "private"), True),
                               (("pull_request", "base", "repo", "private"), None),
                               (("pull_request", "head", "sha"), "bad")):
                modified = json.loads(json.dumps(event))
                field = modified
                for word in key[:-1]:
                    field = field[word]
                field[key[-1]] = value
                self.event.write_text(json.dumps(modified), encoding="utf-8")
                status, message = action_summary.summary_result(self.env)
                self.assertEqual(status, "invalid_input")
                self.assertNotIn(self.source, message)
                self.assertNotIn(self.title, message)
        preflight.assert_not_called()
        self.resolve.assert_not_called()

    def test_missing_public_pr_is_distinct_from_rate_limit_and_empty_result(self):
        self.resolve.side_effect = [HTTPError(self.source, code, "", {}, None) for code in (404, 403)]
        env = {**self.env, "PORTBRIDGE_PR_URL": self.source}
        with mock.patch.object(action_summary, "public_preflight") as preflight:
            self.assertEqual(action_summary.summary_result(env)[0], "origin_missing")
            self.assertEqual(action_summary.summary_result(env)[0], "origin_unverified")
        preflight.assert_not_called()

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


class PublicHeadTest(TestCase):
    def test_public_metadata_needs_the_same_pr_and_public_repository(self):
        url = "https://github.com/example/port/pull/42"
        data = {"number": 42, "base": {"repo": {"private": False}}, "head": {"sha": "a" * 40}, "html_url": url}
        with mock.patch.object(action_summary, "build_opener") as opener:
            open_url = opener.return_value.open
            open_url.side_effect = [BytesIO(json.dumps(obj).encode()) for obj in (
                data, {**data, "number": 2}, {**data, "base": {"repo": {"private": True}}})]
            self.assertEqual(action_summary.public_pr_head(url), "a" * 40)
            for _ in range(2):
                with self.assertRaises(ValueError):
                    action_summary.public_pr_head(url)
        req = open_url.call_args.args[0]
        self.assertEqual(req.full_url, "https://api.github.com/repos/example/port/pulls/42")
        self.assertFalse(req.has_header("Authorization"))
