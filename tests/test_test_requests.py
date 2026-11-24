from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from unittest import TestCase
from unittest.mock import Mock

from portbridge.lab import build_lab
from portbridge.test_requests import APPROVAL, BOT, REPO_PATH, GitHub, dispatch, parse_request


NOW = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
ISSUE = f"{REPO_PATH}/issues/42"
TASK = "pb-5-xcl-wave64"
REVISION = next(task["revisions"][0]["url"] for task in build_lab()["tasks"] if task["id"] == TASK)
REPORT = "https://github.com/example/public/pull/3#issuecomment-8"


def issue_body(task=TASK, equipment="amd", revision=REVISION, check="Compare both synthetic cases."):
    return "\n\n".join(("### Lab task", task, "### Equipment", equipment, "### Source commit", revision,
                         "### Requested check", check))


def tester(login, *capabilities, equipment="amd", rate="2026-11-24T10:00:00Z"):
    return {"login": login, "equipment": equipment, "capabilities": list(capabilities),
            "reported_at": rate, "hardware": "Radeon RX 9070 XT", "evidence_url": REPORT}


class TestRequestTests(TestCase):
    def setUp(self):
        self.issue = {"number": 42, "body": issue_body(), "state": "open", "labels": [{"name": APPROVAL}],
                      "user": {"login": "requester"}}
        self.event = {"repository": {"full_name": "akimfomin/PortBridge"}, "issue": self.issue,
                      "action": "labeled", "label": {"name": APPROVAL}, "sender": {"login": "Maintainer"}}
        self.github = Mock()
        self.github.get.side_effect = self.github_get
        self.github.comments.side_effect = self.github_comments
        self.current = deepcopy(self.issue)
        self.request_comments = []
        self.recent_comments = []
        self.permission = "write"

    def github_get(self, path, *, public=False):
        if path == ISSUE:
            return self.current
        if path.endswith("/permission"):
            return {"permission": self.permission}
        if public and path == "/repos/example/public":
            return {"private": False}
        if public and path == "/repos/example/public/commits/" + "a" * 40:
            return {"sha": "a" * 40}
        self.fail(f"Unexpected GitHub GET: {path}")

    def github_comments(self, path, *, since=None):
        if path == f"{ISSUE}/comments":
            self.assertIsNone(since)
            return self.request_comments
        self.assertEqual(path, f"{REPO_PATH}/issues/comments")
        self.assertEqual(since, "2026-11-17T12:00:00+00:00")
        return self.recent_comments

    def run_dispatch(self, testers):
        return dispatch(self.event, testers, self.github, now=NOW)

    def test_form_accepts_blank_task_and_rejects_extra_fields_links_or_mentions(self):
        self.assertEqual(parse_request(issue_body(task=""))["task"], "")
        self.assertEqual(parse_request(issue_body(task="_No response_").replace("\n", "\r\n"))["task"], "")
        self.assertEqual(parse_request(issue_body(task="custom"))["task"], "")
        for body in (
            issue_body(check="Ask @somebody to run a check."),
            issue_body(check="Read https://example.com before testing."),
            issue_body(equipment="amd, nvidia"),
            issue_body(revision="https://github.com/example/public/commit/main"),
            issue_body() + "\n\n### Destination\n\nother repository",
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_request(body)

    def test_authorization_requires_repository_write_and_approved_current_issue(self):
        candidate = tester("Volunteer", "d3d12-native-wave64")
        self.permission = "triage"
        with self.assertRaisesRegex(ValueError, "write access"):
            self.run_dispatch([candidate])
        self.permission = "write"
        self.current["labels"] = []
        self.assertIn("no longer", self.run_dispatch([candidate]))
        self.current = {**self.issue, "body": issue_body(check="Try the approved test again.")}
        self.assertIn("changed after approval", self.run_dispatch([candidate]))
        self.github.comment.assert_not_called()

    def test_one_notification_matches_capability_and_excludes_recent_testers(self):
        self.recent_comments = [
            {"user": {"login": BOT}, "body": "<!-- portbridge:test-invite:v1:12:Recent -->\n",
             "created_at": "2026-11-23T10:00:00Z"},
            {"user": {"login": "someone"}, "body": "<!-- portbridge:test-invite:v1:13:Volunteer -->\n",
             "created_at": "2026-11-23T10:00:00Z"},
        ]
        self.request_comments = [
            {"user": {"login": "requester"}, "body": "<!-- portbridge:test-invite:v1:42:Volunteer -->\n"},
        ]
        roster = [
            tester("WrongGPU", "d3d12-native-wave64", equipment="nvidia"),
            tester("WrongCapability", "win32-vulkan-1.3"),
            tester("Recent", "d3d12-native-wave64"),
            tester("Stale", "d3d12-native-wave64", rate="2026-06-01T00:00:00Z"),
            tester("Requester", "d3d12-native-wave64"),
            tester("Maintainer", "d3d12-native-wave64"),
            tester("Volunteer", "d3d12-native-wave64"),
        ]
        self.assertIn("Posted one", self.run_dispatch(roster))
        self.github.comment.assert_called_once()
        path, message = self.github.comment.call_args.args
        self.assertEqual(path, f"{ISSUE}/comments")
        self.assertIn("@Volunteer", message)
        self.assertIn("native Wave64 on D3D12", message)
        self.assertIn("take the check or decline here", message)
        self.assertIn(REPORT, message)
        self.assertIn("https://github.com/akimfomin/PortBridge/issues/5", message)
        self.assertNotIn("Compare both synthetic cases", message)
        self.request_comments.append({"user": {"login": BOT}, "body": message})
        self.assertIn("already", self.run_dispatch(roster))
        self.github.comment.assert_called_once()

    def test_rejects_known_task_with_wrong_pin_and_checks_custom_public_revision(self):
        custom = "https://github.com/example/public/commit/" + "a" * 40
        self.issue["body"] = issue_body(revision=custom)
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.run_dispatch([])
        self.github.comment.assert_not_called()
        self.issue["body"] = self.current["body"] = issue_body(task="custom", revision=custom)
        self.assertIn("Posted one", self.run_dispatch([tester("Volunteer")]))
        self.github.get.assert_any_call("/repos/example/public", public=True)
        self.github.get.assert_any_call("/repos/example/public/commits/" + "a" * 40, public=True)

    def test_control_revision_is_not_an_actionable_lab_pin(self):
        task = next(row for row in build_lab()["tasks"] if row["id"] == "pb-9-reforge-present")
        self.issue["body"] = issue_body(task=task["id"], revision=task["revisions"][1]["url"])
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.run_dispatch([tester("Volunteer", "win32-vulkan-1.3")])
        self.github.comment.assert_not_called()

    def test_manual_dispatch_needs_an_existing_approval_label(self):
        manual = {"repository": self.event["repository"], "sender": self.event["sender"],
                  "inputs": {"issue_number": "42"}}
        roster = [tester("Volunteer", "d3d12-native-wave64")]
        self.current["labels"] = []
        result = dispatch(manual, roster, self.github, event_name="workflow_dispatch", now=NOW)
        self.assertIn("no longer", result)
        self.github.comment.assert_not_called()
        self.current["labels"] = [{"name": APPROVAL}]
        result = dispatch(manual, roster, self.github, event_name="workflow_dispatch", now=NOW)
        self.assertIn("Posted one", result)
        self.github.comment.assert_called_once()

    def test_live_discovery_runs_for_known_capability_and_combines_with_curated_reports(self):
        discovery = Mock(return_value=[
            tester("LiveCandidate", "d3d12-native-wave64", rate="2026-11-24T11:00:00Z"),
            tester("Curated", "d3d12-native-wave64", rate="2026-11-24T09:30:00Z"),
        ])
        roster = [tester("Curated", "d3d12-native-wave64")]
        self.assertIn("Posted one", dispatch(self.event, roster, self.github, now=NOW, discover=discovery))
        discovery.assert_called_once_with("amd", ("d3d12-native-wave64",))
        body = self.github.comment.call_args.args[1]
        self.assertIn("@LiveCandidate", body)
        self.assertNotIn("@Curated", body)

    def test_fma_request_needs_rdna4_as_well_as_native_wave64(self):
        task = next(row for row in build_lab()["tasks"] if row["id"] == "xcl-1100-fma")
        request = issue_body(task=task["id"], revision=task["revisions"][0]["url"])
        self.issue["body"] = self.current["body"] = request
        roster = [tester("NativeOtherArchitecture", "d3d12-native-wave64")]
        discovery = Mock(return_value=[])
        self.assertIn("No matching tester", dispatch(self.event, roster, self.github, now=NOW, discover=discovery))
        discovery.assert_called_once_with("amd", ("d3d12-native-wave64-rdna4",))
        self.github.comment.assert_not_called()

    def test_labeled_request_checks_live_receiving_head_before_inviting(self):
        task = next(row for row in build_lab()["tasks"] if row["id"] == "xcl-1100-fma")
        request = issue_body(task=task["id"], revision=task["revisions"][0]["url"])
        self.issue["body"] = self.current["body"] = request
        candidate = tester("Volunteer", "d3d12-native-wave64-rdna4")
        current_sha = task["revisions"][0]["sha"]
        endpoint = "/repos/ivall/xcl/pulls/1100"
        receiving = {"state": "open", "head": {"sha": "f" * 40}}

        def get(path, *, public=False):
            if path == endpoint:
                self.assertTrue(public)
                return receiving
            return self.github_get(path, public=public)

        self.github.get.side_effect = get
        self.assertIn("changed or closed", self.run_dispatch([candidate]))
        receiving.update(state="closed", head={"sha": current_sha})
        self.assertIn("changed or closed", self.run_dispatch([candidate]))
        self.github.comment.assert_not_called()
        receiving["state"] = "open"
        self.assertIn("Posted one", self.run_dispatch([candidate]))
        self.github.comment.assert_called_once()

    def test_prior_public_handoffs_count_towards_the_same_cooldown(self):
        roster = [tester("Invited", "d3d12-native-wave64"), tester("Volunteer", "d3d12-native-wave64")]
        prior = [{"login": "INVITED", "sent_at": "2026-11-24T09:00:00Z", "evidence_url": REPORT},
                 {"login": "Volunteer", "sent_at": "2026-10-24T09:00:00Z", "evidence_url": REPORT}]
        self.assertIn("Posted one", dispatch(self.event, roster, self.github, now=NOW, prior_invites=prior))
        body = self.github.comment.call_args.args[1]
        self.assertIn("@Volunteer", body)
        self.assertNotIn("@Invited", body)

    def test_custom_model_requires_the_exact_recorded_model_not_just_vendor(self):
        custom = "https://github.com/example/public/commit/" + "a" * 40
        with self.assertRaisesRegex(ValueError, "Equipment field"):
            parse_request(issue_body(task="custom", revision=custom, check="Use a Radeon RX 9070 XT."))
        request = issue_body(task="custom", equipment="amd: RX 9070 XT", revision=custom)
        self.issue["body"] = self.current["body"] = request
        similar = {**tester("WrongModel"), "hardware": "AMD Radeon RX 9070"}
        self.assertIn("No matching", self.run_dispatch([similar]))
        self.github.comment.assert_not_called()
        exact = {**tester("ExactModel"), "hardware": "AMD Radeon RX 9070 XT"}
        discovery = Mock(return_value=[exact])
        self.assertIn("Posted one", dispatch(self.event, [similar], self.github, now=NOW, discover=discovery))
        discovery.assert_called_once_with("amd", ())
        self.assertIn("@ExactModel", self.github.comment.call_args.args[1])

    def test_custom_repositories_receive_no_token_and_cannot_be_written(self):
        github = GitHub("fixed-test-token")
        github.opener = Mock()
        response = Mock()
        response.__enter__ = Mock(return_value=BytesIO(b"{}"))
        response.__enter__.return_value.headers = {}
        response.__exit__ = Mock(return_value=False)
        github.opener.open.return_value = response
        github.get("/repos/example/public", public=True)
        self.assertIsNone(github.opener.open.call_args.args[0].get_header("Authorization"))
        with self.assertRaisesRegex(ValueError, "stay inside"):
            github.get("/repos/example/public")
        with self.assertRaisesRegex(ValueError, "cannot write"):
            github.request("/repos/example/public", public=True, body={"body": "unwanted"})
