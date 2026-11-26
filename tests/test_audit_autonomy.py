from datetime import timedelta
import unittest

from audit.m6_autonomy import RECEIPT, measure, stamp


class AutonomyAuditTest(unittest.TestCase):
    def test_delivery_uses_receipt_time_and_requires_the_scheduled_revision(self):
        start = stamp("2026-11-26T21:07:13Z")
        day = timedelta(days=1)
        minute = timedelta(minutes=1)

        def run(identifier, date, event="schedule"):
            return {"id": identifier, "created_at": date.isoformat(), "event": event, "head_branch": "main",
                    "head_sha": "a" * 40, "html_url": f"run-{identifier}", "conclusion": "success"}

        def receipt(identifier, run_id, date, *, sha="a" * 40):
            return {"id": identifier, "name": RECEIPT, "created_at": date.isoformat(),
                    "expired": False, "workflow_run": {"id": run_id, "head_sha": sha}}

        runs = [run(1, start + day - minute), run(2, start + day + minute, "workflow_dispatch"),
                run(3, start + day + minute), run(4, start + 7 * day - minute)]
        artifacts = [receipt(11, 1, start + day + minute), receipt(12, 1, start + day * 2),
                     receipt(21, 2, start + day + 2 * minute),
                     receipt(31, 3, start + day + 2 * minute, sha="b" * 40),
                     receipt(41, 4, start + 7 * day + minute)]

        report = measure(start, start + 8 * day, runs, artifacts)
        self.assertEqual(report["verified_per_24h"], [0, 1, 0, 0, 0, 0, 0])
        self.assertEqual(report["verified_publications"], [
            {"at": (start + day + minute).isoformat(), "run_started_at": runs[0]["created_at"],
             "url": "run-1", "sha": "a" * 40, "artifact_id": 11},
        ])
        self.assertEqual(report["scheduled_without_success_receipt"], ["run-3", "run-4"])
        self.assertFalse(report["seven_intervals_observed"])
