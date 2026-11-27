from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import Mock

from portbridge.volunteer_requests import hub_comments, match_request

NOW = datetime(2026, 11, 27, 4, tzinfo=timezone.utc)
SCOPE = "windows-11-ltsc-d3d12"
OPT_IN = f"PortBridge volunteer v1 | {SCOPE} | amd: RX 6700 XT | yes"
ISSUE = {
    "title": "Test request: synthetic pipeline reload",
    "state": "open",
    "user": {"login": "owner"},
    "body": ("### Lab task\n\n_No response_\n\n### Equipment\n\namd: RX 6700 XT\n\n"
             "### Source commit\n\nhttps://github.com/example/project/commit/" + "a" * 40
             + "\n\n### Requested check\n\nRun the test. [Context](https://github.com/example/project/issues/1)"),
}


def comment(body, number=1, login="tester", at="2026-11-27T03:00:00Z", kind="User"):
    return {"body": body, "id": number, "user": {"login": login, "type": kind}, "updated_at": at}


class VolunteerRequestTests(TestCase):
    def test_explicit_exact_hardware_and_os_only(self):
        rows = [comment(OPT_IN), comment(OPT_IN.replace("6700", "6750"), 2, "wrong-gpu"),
                comment(OPT_IN.replace(SCOPE, "windows-d3d12"), 3, "wrong-os"),
                comment("Windows 11 | RX 6700 XT | self-select only", 4, "read-only"),
                comment(OPT_IN, 5, "owner"), comment(OPT_IN, 6, "robot", kind="Bot"),
                comment(OPT_IN, 7, "old", at="2026-07-01T00:00:00Z")]
        self.assertEqual(match_request(ISSUE, rows, SCOPE, now=NOW),
                         [{"login": "tester", "consent_url": "https://github.com/akimfomin/PortBridge/issues/112#issuecomment-1"}])

    def test_latest_edit_pause_and_scope_change_cancel_prior_consent(self):
        for replacement in ("PortBridge volunteer v1 | paused", OPT_IN.replace("yes", "no"),
                            OPT_IN.replace(SCOPE, "windows-d3d12")):
            with self.subTest(replacement=replacement):
                rows = [comment(replacement, 2, "Tester", "2026-11-27T03:10:00Z"), comment(OPT_IN)]
                self.assertEqual(match_request(ISSUE, rows, SCOPE, now=NOW), [])

    def test_equal_timestamp_revocation_wins_and_closed_request_is_rejected(self):
        self.assertEqual(match_request(ISSUE, [comment(OPT_IN, 2), comment("PortBridge volunteer v1 | paused")],
                                       SCOPE, now=NOW), [])
        with self.assertRaises(ValueError):
            match_request({**ISSUE, "state": "closed"}, [], SCOPE, now=NOW)

    def test_pagination_reads_the_fixed_public_hub_without_writes(self):
        github = Mock()
        github.request.side_effect = [([comment(OPT_IN)], True), ([comment("PortBridge volunteer v1 | paused", 2)], False)]
        self.assertEqual(match_request(ISSUE, hub_comments(github), SCOPE, now=NOW), [])
        self.assertTrue(all(call.kwargs == {"public": True} for call in github.request.call_args_list))
        github.comment.assert_not_called()
