import unittest

from readiness import Limits, Pipeline, Request, replay
from replay_cases import report


class ReadinessTest(unittest.TestCase):
    def test_worker_only_misses_estimated_memory_contention(self):
        results = report()["cases"]["combined-memory-pressure"]["policies"]
        worker = results["reserved-worker"]["result"]
        protected = results["reserved-worker-and-memory"]["result"]
        self.assertEqual(worker["first_frame_ready_us"], 92_000)
        self.assertEqual(protected["first_frame_ready_us"], 20_000)
        self.assertGreater(protected["all_completed_us"], worker["all_completed_us"])

    def test_undersized_reservation_does_not_overspend_or_preempt(self):
        work = [Pipeline("warm", 50, 3), Pipeline("required", 10, 6)]
        arrivals = [Request(0, "warm"), Request(2, "required", True)]
        result = replay(work, arrivals, Limits(2, 8, protected_workers=1, protected_mib=4))
        self.assertEqual(result.first_frame_ready_us, 60)
        self.assertEqual(result.peak_estimated_mib, 6)
        self.assertEqual(result.required_wait_us, (58,))

    def test_correct_warmup_can_beat_reservation_and_phase_arming(self):
        cases = report()["cases"]
        accurate = cases["accurate-early-warmup"]["policies"]
        late = cases["late-phase-signal"]["policies"]
        self.assertEqual(accurate["reserved-worker"]["result"]["first_frame_ready_us"], 100_000)
        self.assertEqual(accurate["reserved-worker-and-memory"]["result"]["first_frame_ready_us"], 124_000)
        self.assertEqual(accurate["phase-armed-reservation"]["result"]["first_frame_ready_us"], 100_000)
        self.assertEqual(late["phase-armed-reservation"]["result"]["first_frame_ready_us"], 132_000)
        self.assertEqual(late["reserved-worker-and-memory"]["result"]["first_frame_ready_us"], 52_000)

    def test_simultaneous_requests_prioritize_demand_and_compile_once(self):
        pipelines = [Pipeline("warm", 30, 4), Pipeline("need", 5, 4)]
        requests = [Request(0, "warm"), Request(0, "need"), Request(0, "need", True),
                    Request(1, "need", True), Request(9, "need", True)]
        result = replay(pipelines, requests, Limits(1, 4))
        self.assertEqual(tuple(job.key for job in result.compilations), ("need", "warm"))
        self.assertEqual(result.required_wait_us, (5, 4, 0))
        self.assertEqual(result.first_frame_ready_us, 9)
        self.assertEqual(result.all_completed_us, 35)

    def test_demand_joins_existing_background_compilation(self):
        work = [Pipeline("a", 10, 2)]
        result = replay(work, [Request(0, "a"), Request(1, "a", True), Request(10, "a", True)], Limits(2, 4))
        self.assertEqual(len(result.compilations), 1)
        self.assertFalse(result.compilations[0].required_at_start)
        self.assertEqual(result.required_wait_us, (9, 0))

    def test_promoted_work_joins_the_tail_of_existing_demand(self):
        work = [Pipeline("busy", 20, 2), Pipeline("earlier-hint", 5, 2), Pipeline("actual-first", 5, 2)]
        requests = [Request(0, "busy"), Request(0, "earlier-hint"), Request(1, "actual-first", True),
                    Request(2, "earlier-hint", True), Request(3, "actual-first", True)]
        result = replay(work, requests, Limits(1, 2))
        self.assertEqual(tuple(job.key for job in result.compilations), ("busy", "actual-first", "earlier-hint"))
        self.assertEqual(result.required_wait_us, (24, 28, 22))

    def test_impossible_limits_and_unrecognized_key_fail(self):
        with self.assertRaises(ValueError):
            replay([Pipeline("a", 20, 2)], [Request(0, "a", True)], Limits(2, 1))
        with self.assertRaises(ValueError):
            replay([Pipeline("a", 20, 1)], [Request(0, "unknown", True)], Limits(2, 1))

    def test_invalid_numeric_trace_cannot_stall_the_event_loop(self):
        with self.assertRaises(ValueError):
            replay([Pipeline("a", float("nan"), 1)], [Request(0, "a", True)], Limits(2, 1))
        with self.assertRaises(ValueError):
            replay([Pipeline("a", 20, 1)], [Request(float("nan"), "a", True)], Limits(2, 1))
        with self.assertRaises(ValueError):
            replay([Pipeline("a", 20, 1)], [Request(0, "a", True)], Limits(True, 1))

    def test_failed_required_compile_returns_no_frame_and_releases_budget(self):
        work = [Pipeline("broken", 10, 4, fails=True), Pipeline("warmup", 20, 4)]
        requests = [Request(0, "warmup"), Request(1, "broken", True), Request(2, "broken", True)]
        result = replay(work, requests, Limits(2, 4, protected_workers=1, protected_mib=4))
        self.assertIsNone(result.first_frame_ready_us)
        self.assertEqual(result.required_wait_us, (10, 9))
        self.assertEqual(result.failed_keys, ("broken",))
        self.assertEqual(result.all_completed_us, 31)

    def test_workers_memory_no_omission_and_no_advance_before_request(self):
        for case in report()["cases"].values():
            work = {item["key"]: item for item in case["pipelines"]}
            requested = {item["key"] for item in case["requests"]}
            for policy in case["policies"].values():
                result = policy["result"]
                jobs = result["compilations"]
                self.assertCountEqual((job["key"] for job in jobs), requested)
                for job in jobs:
                    key = job["key"]
                    self.assertGreaterEqual(job["start_us"], min(
                        req["at_us"] for req in case["requests"] if req["key"] == key))
                    self.assertEqual(job["finish_us"] - job["start_us"], work[key]["compile_us"])
                    at = job["start_us"]
                    active = [other for other in jobs if other["start_us"] <= at < other["finish_us"]]
                    self.assertLessEqual(len(active), policy["limits"]["workers"])
                    self.assertLessEqual(sum(work[other["key"]]["estimated_mib"] for other in active),
                                         policy["limits"]["estimated_mib"])


if __name__ == "__main__":
    unittest.main()
