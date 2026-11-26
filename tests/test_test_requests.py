from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import re
from unittest import TestCase
from unittest.mock import Mock, patch

from portbridge.lab import TASKS, build_lab
from portbridge.lab_reports import FRAMELAB_TASK
from portbridge.test_requests import APPROVAL, BOT, REPO_PATH, GitHub, dispatch, load_testers, parse_request


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
    def test_invitation_workflow_requires_manual_dispatch(self):
        workflow = Path(__file__).resolve().parents[1] / ".github/workflows/test-requests.yml"
        settings = workflow.read_text(encoding="utf-8").split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual(re.findall(r"^  ([\w-]+):", settings, re.MULTILINE), ["workflow_dispatch"])

    def setUp(self):
        # Exercise the original monitored request while the real legacy card awaits a new pin.
        active = tuple({**task, "status": "needs_run", "receiving_url": None} if task["id"] == TASK else task
                       for task in TASKS)
        patcher = patch("portbridge.lab.TASKS", active)
        self.addCleanup(patcher.stop)
        patcher.start()
        self.issue = {"number": 42, "body": issue_body(), "state": "open", "labels": [{"name": APPROVAL}],
                      "user": {"login": "requester"}}
        self.event = {"repository": {"full_name": "akimfomin/PortBridge"}, "issue": self.issue,
                      "action": "labeled", "label": {"name": APPROVAL}, "sender": {"login": "Maintainer"}}
        self.github = Mock()
        self.github.get.side_effect = self.github_get
        self.github.comments.side_effect = self.github_comments
        self.github.request.return_value = ([], False)
        self.current = deepcopy(self.issue)
        self.request_comments = []
        self.recent_comments = []
        self.permission = "write"

    def github_get(self, path, *, public=False):
        if path == ISSUE:
            return self.current
        if path.endswith("/permission"):
            return {"permission": self.permission}
        if public and path in {"/repos/akimfomin/PortBridge/issues/5", "/repos/xcl-dev/xcl/issues/1100",
                                "/repos/LooperSalty/AnyXboxX/issues/133"}:
            return {"state": "open"}
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

    def test_duplicate_scope_from_another_request_avoids_a_second_invitation(self):
        sha = REVISION.rsplit("/", 1)[1]
        self.recent_comments = [{
            "user": {"login": BOT},
            "body": f"<!-- portbridge:test-invite:v2:12:Another:{TASK}:{sha}:amd -->" + chr(10),
            "created_at": "2026-11-23T10:00:00Z",
        }]
        with self.subTest("same cell"):
            self.assertIn("hardware cell already", self.run_dispatch([tester("Different", "d3d12-native-wave64")]))
            self.github.comment.assert_not_called()
        self.recent_comments[0]["body"] = self.recent_comments[0]["body"].replace(":amd -->", ":intel -->")
        with self.subTest("different cell"):
            self.assertIn("Posted one", self.run_dispatch([tester("Different", "d3d12-native-wave64")]))

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

    @patch("portbridge.test_requests.scan_reports")
    def test_monitored_task_checks_coverage_before_rechecking_approval(self, scan):
        task = build_lab(task=FRAMELAB_TASK)["tasks"][0]
        request = issue_body(task=task["id"], revision=task["revisions"][0]["url"])
        self.issue["body"] = self.current["body"] = request
        base_get = self.github_get
        self.github.get.side_effect = lambda path, public=False: (
            {"state": "open"} if public and path.endswith("/issues/15") else base_get(path, public=public))
        scan.return_value = [{"hardware": "AMD Radeon 860M", "outcome": "pass",
                              "equipment": "amd", "authority": "approved"}]
        candidate = tester("Volunteer")
        self.assertIn("already reported", self.run_dispatch([candidate]))
        self.github.comment.assert_not_called()

        def revoked(*args):
            self.current["labels"] = []
            return []

        scan.side_effect = revoked
        self.assertIn("no longer", self.run_dispatch([candidate]))
        self.github.comment.assert_not_called()

    def test_control_revision_is_not_an_actionable_lab_pin(self):
        task = next(row for row in build_lab()["tasks"] if row["id"] == "scarlett-commons-continued-add-basic")
        self.issue["body"] = issue_body(task=task["id"], equipment="cpu", revision=task["revisions"][1]["url"])
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.run_dispatch([tester("Volunteer", "python-cpu", equipment="cpu")])
        self.github.comment.assert_not_called()

    def test_blocked_lab_task_cannot_invite_a_tester(self):
        task = next(row for row in build_lab()["tasks"] if row["id"] == "pb-9-reforge-present")
        self.issue["body"] = issue_body(task=task["id"], revision=task["revisions"][0]["url"])
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

    @patch("portbridge.test_requests.build_lab")
    def test_fma_request_needs_rdna4_as_well_as_native_wave64(self, lab):
        task = next(row for row in build_lab()["tasks"] if row["id"] == "xcl-1100-fma")
        lab.return_value = {"tasks": [{**task, "status": "needs_run"}]}
        request = issue_body(task=task["id"], revision=task["revisions"][0]["url"])
        self.issue["body"] = self.current["body"] = request
        roster = [tester("NativeOtherArchitecture", "d3d12-native-wave64")]
        discovery = Mock(return_value=[])
        self.assertIn("No matching tester", dispatch(self.event, roster, self.github, now=NOW, discover=discovery))
        discovery.assert_called_once_with("amd", ("d3d12-native-wave64-rdna4",))
        self.github.comment.assert_not_called()

    @patch("portbridge.test_requests.build_lab")
    def test_labeled_request_checks_live_receiving_head_before_inviting(self, lab):
        task = next(row for row in build_lab()["tasks"] if row["id"] == "xcl-1100-fma")
        lab.return_value = {"tasks": [{**task, "status": "needs_run"}]}
        request = issue_body(task=task["id"], revision=task["revisions"][0]["url"])
        self.issue["body"] = self.current["body"] = request
        candidate = tester("Volunteer", "d3d12-native-wave64-rdna4")
        current_sha = task["revisions"][0]["sha"]
        endpoint = "/repos/xcl-dev/xcl/pulls/1100"
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

    def test_completed_fma_request_cannot_invite_another_tester(self):
        task = build_lab(task="xcl-1100-fma")["tasks"][0]
        self.issue["body"] = self.current["body"] = issue_body(task=task["id"], revision=task["revisions"][0]["url"])
        with self.assertRaisesRegex(ValueError, "does not match the open test"):
            self.run_dispatch([tester("Volunteer", "d3d12-native-wave64-rdna4")])
        self.github.comment.assert_not_called()

    @patch("portbridge.test_requests.build_lab")
    def test_native_carry_invites_only_the_qualified_reporter_at_the_open_head(self, lab):
        task = next(row for row in build_lab()["tasks"] if row["id"] == "anyxboxx-133-native-carry")
        head = "e2af2d38e48b5a0019dae5c78aa398cc71c42c8d"
        revision_url = f"https://github.com/LooperSalty/AnyXboxX/commit/{head}"
        lab.return_value = {"tasks": [{**task, "status": "needs_run", "result_url": task["source_url"],
                                      "revisions": [{"sha": head, "url": revision_url}]}]}
        self.issue["body"] = self.current["body"] = issue_body(task=task["id"], revision=revision_url)
        roster = load_testers()
        generic = [row for row in roster if row["login"] != "Lyrnc"]
        discovery = Mock(return_value=[tester("GenericAMD", "d3d12-native-wave64")])
        self.assertIn("No matching tester", dispatch(self.event, generic, self.github, now=NOW, discover=discovery))
        discovery.assert_called_once_with("amd", ("amd-rdna2-native-isa-hip",))
        self.github.comment.assert_not_called()

        receiving = {"state": "open", "head": {"sha": "f" * 40}}

        def get(path, *, public=False):
            if path == "/repos/LooperSalty/AnyXboxX/pulls/133":
                self.assertTrue(public)
                return receiving
            return self.github_get(path, public=public)

        self.github.get.side_effect = get
        self.assertIn("changed or closed", self.run_dispatch(roster))
        receiving.update(state="closed", head={"sha": head})
        self.assertIn("changed or closed", self.run_dispatch(roster))
        self.github.comment.assert_not_called()
        receiving["state"] = "open"
        self.assertIn("Posted one", self.run_dispatch(roster))
        self.github.comment.assert_called_once()
        body = self.github.comment.call_args.args[1]
        self.assertIn("@Lyrnc", body)
        self.assertIn("native AMD RDNA2 instructions through HIP", body)
        self.assertIn("https://github.com/Marvisak/VIctory/pull/605#issuecomment-7123302580", body)
        self.assertIn(task["source_url"], body)
        lab.assert_called_with(equipment="amd", status="needs_run")

    def test_native_carry_with_report_no_longer_invites_a_tester(self):
        revision_url = "https://github.com/LooperSalty/AnyXboxX/commit/e2af2d38e48b5a0019dae5c78aa398cc71c42c8d"
        self.issue["body"] = self.current["body"] = issue_body(task="anyxboxx-133-native-carry", revision=revision_url)
        with self.assertRaisesRegex(ValueError, "does not match the open test"):
            self.run_dispatch(load_testers())
        self.github.comment.assert_not_called()

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
