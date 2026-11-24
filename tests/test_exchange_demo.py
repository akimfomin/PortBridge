import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from portbridge.exchange_demo import REFERENCE, SIMULATION_REVISION, run_demo, simulate_geometry


class ExchangeDemoTests(TestCase):
    def test_cpu_fixture_checks_six_orders(self):
        self.assertEqual(simulate_geometry(), (6, 6))

    def test_two_agents_share_only_the_accepted_simulation(self):
        with TemporaryDirectory() as directory:
            result = run_demo(temp_root=directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

        self.assertEqual(result["mode"], "simulation")
        self.assertEqual(result["transport"], "loopback HTTP API")
        self.assertEqual(result["problem_id"], "PB-0001")
        self.assertEqual(result["actors"], ["TEST Continued Vulkan", "TEST VIctory D3D12", "TEST Human Reviewer"])
        self.assertTrue(result["claim_visible_to_other_agent"])
        self.assertTrue(result["pending_result_visible_to_reviewer"])
        self.assertTrue(result["unauthorized_review_denied"])
        self.assertEqual(result["unauthorized_review_http_status"], 403)
        self.assertEqual(result["events_before_review"], 0)
        self.assertEqual(result["evidence_before_review"], 0)
        self.assertEqual(result["preflight_reports_before_review"], 0)
        self.assertEqual(result["review_status"], "accepted")
        self.assertEqual(result["events_after_advancing_cursor"], 0)

        check = result["known_public_check"]
        self.assertEqual(check["project"], "victory")
        self.assertEqual(check["url"], REFERENCE)
        self.assertEqual(check["revision"], "cee702eb4797a2288a2519b4cbda61720cfb7db4")
        self.assertTrue(result["lookup_comparison"]["same_source_and_revision"])
        self.assertGreaterEqual(result["lookup_comparison"]["raw_catalog"], 0)
        self.assertGreaterEqual(result["lookup_comparison"]["preflight"], 0)

        poll = result["received"]
        event, = poll["events"]
        self.assertEqual(event["kind"], "result_accepted")
        self.assertEqual(event["id"], poll["next_cursor"])
        report = event["result"]
        self.assertEqual(report["evidence_kind"], "simulation")
        self.assertEqual(report["outcome"], "passed")
        self.assertEqual(report["revision"], SIMULATION_REVISION)
        self.assertEqual(result["accepted_evidence_ids"], [report["id"]])
        self.assertEqual(result["preflight_reports_after_review"], [report["id"]])
        self.assertNotEqual(report["revision"], check["revision"])
        self.assertIn("SIMULATION: 6/6", report["summary"])
        self.assertEqual(result["new_topic"]["reports_before_review"], 0)
        fresh, = result["new_topic"]["reports_after_review"]
        self.assertEqual(fresh["problem_id"], result["new_topic"]["topic"]["id"])
        self.assertEqual(fresh["outcome"], "unknown")
        self.assertNotIn('"token"', json.dumps(result))
