from datetime import timedelta
import unittest

from audit.m6_autonomy import RECEIPT, measure, stamp


class ScheduledVerificationTest(unittest.TestCase):
    def test_attempts_and_verified_time_are_used_for_coverage(self):
        start = stamp("2026-11-26T21:07:00Z")
        now = stamp("2026-11-27T10:00:00Z")

        def run(ident, created, attempt=1):
            return {"id": ident, "event": "schedule", "head_branch": "main", "head_sha": "a" * 40,
                    "html_url": f"https://github.com/example/public/actions/runs/{ident}",
                    "created_at": created, "conclusion": "success", "run_attempt": attempt}

        def artifact(ident, run_id):
            return {"id": ident, "workflow_run": {"id": run_id}, "name": RECEIPT, "expired": False}

        def receipt(run_id, at, attempt=1):
            return {"GITHUB_RUN_ID": str(run_id), "GITHUB_RUN_ATTEMPT": str(attempt),
                    "GITHUB_SHA": "a" * 40, "SITE_SHA256": "b" * 64, "LAB_SHA256": "c" * 64,
                    "verified_at": at}

        runs = [run(1, "2026-11-27T00:34:00Z"), run(2, "2026-11-27T09:03:00Z", 2),
                run(3, "2026-11-27T09:33:00Z", 2)]
        artifacts = [artifact(12, 2), artifact(11, 2), artifact(10, 1), artifact(13, 3)]
        payloads = {10: receipt(1, "2026-11-27T00:42:42Z"), 11: receipt(2, "2026-11-27T09:10:59Z", 2),
                    12: receipt(2, "2026-11-27T09:09:00Z"), 13: receipt(3, "2026-11-27T09:39:00Z")}
        scored = measure(start, now, runs, artifacts, payloads)
        self.assertEqual([x["artifact_id"] for x in scored["verified_publications"]], [10, 11])
        self.assertEqual(scored["expected_slots_elapsed"], 26)
        self.assertEqual(scored["verified_per_24h"][0], 2)
        self.assertEqual(scored["longest_observed_gap_hours"], 8.47)
        self.assertEqual(scored["successful_run_with_listed_artifact_only"], [runs[2]["html_url"]])
        self.assertFalse(scored["seven_intervals_observed"])
        self.assertFalse(measure(start, start + timedelta(days=7), runs, artifacts)["verified_publications"])

        end = start + timedelta(days=7)
        late = measure(start, end + timedelta(minutes=10),
                       [run(4, (end - timedelta(minutes=3)).isoformat())], [artifact(14, 4)],
                       {14: receipt(4, (end + timedelta(minutes=2)).isoformat())})
        self.assertFalse(late["verified_publications"])
        self.assertEqual(late["verified_after_window"][0]["artifact_id"], 14)
