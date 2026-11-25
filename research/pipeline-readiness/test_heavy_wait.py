import json
from pathlib import Path
import unittest

from heavy_wait import audit_wait


def sample_wait(*resolutions):
    return {
        "wait": {"producer": "worker", "command_list": "list", "begin_us": 0, "end_us": 100},
        "resolutions": list(resolutions),
    }


def resolve(begin, end, *phases, producer="worker", command_list="list", pipeline="pso"):
    return {
        "producer": producer,
        "command_list": command_list,
        "pipeline": pipeline,
        "begin_us": begin,
        "end_us": end,
        "phases": [
            {"kind": phase, "begin_us": start, "end_us": stop} for phase, start, stop in phases
        ],
    }


class HeavyWaitTests(unittest.TestCase):
    def test_minutes_scale_partition(self):
        path = Path(__file__).with_name("evidence") / "heavy-wait-synthetic.json"
        result = audit_wait(json.loads(path.read_text(encoding="utf-8")))
        phases = {"build_queue": 19, "translation": 23, "driver_admission": 14, "native_driver": 40}
        self.assertEqual(result, {
            "wait_us": 160_000_000,
            "resolution_us": 158_000_000,
            "outside_resolution_us": 2_000_000,
            "unattributed_resolution_us": 58_000_000,
            "overlapping_phases_us": 4_000_000,
            "phase_us": {kind: seconds * 1_000_000 for kind, seconds in phases.items()},
            "matched_resolutions": 3,
            "distinct_pipeline_keys": 3,
        })

    def test_same_phase_overlap_counts_once_and_preserves_pipeline_keys(self):
        result = audit_wait(sample_wait(
            resolve(0, 50, ("native_driver", 0, 50), pipeline="shader-a/state-a"),
            resolve(25, 75, ("native_driver", 25, 75), pipeline="shader-a/state-b"),
            resolve(75, 100, ("native_driver", 75, 100), pipeline="shader-a/state-a"),
        ))
        self.assertEqual(result["phase_us"]["native_driver"], 100)
        self.assertEqual(result["matched_resolutions"], 3)
        self.assertEqual(result["distinct_pipeline_keys"], 2)

    def test_shared_admission_two_passes_and_retry(self):
        result = audit_wait(sample_wait(resolve(
            0, 100, ("driver_admission", 0, 10), ("native_driver", 10, 30),
            ("native_driver", 30, 60), ("native_driver", 65, 100),
        )))
        self.assertEqual(result["phase_us"]["driver_admission"], 10)
        self.assertEqual(result["phase_us"]["native_driver"], 85)
        self.assertEqual(result["unattributed_resolution_us"], 5)
        self.assertEqual(result["distinct_pipeline_keys"], 1)

    def test_both_parts_of_release_path_must_match(self):
        phases = (("native_driver", 0, 100),)
        result = audit_wait(sample_wait(
            resolve(0, 100, *phases, command_list="unrelated"),
            resolve(0, 100, *phases, producer="unrelated"),
            resolve(100, 150, ("native_driver", 100, 150)),
        ))
        self.assertEqual(result["outside_resolution_us"], 100)
        self.assertEqual(result["resolution_us"], 0)
        self.assertEqual(result["phase_us"]["native_driver"], 0)

    def test_resolution_without_spans_does_not_imply_driver_delay(self):
        result = audit_wait(sample_wait(resolve(4, 95)))
        self.assertEqual(result["resolution_us"], 91)
        self.assertEqual(result["unattributed_resolution_us"], 91)
        self.assertEqual(set(result["phase_us"].values()), {0})

    def test_invalid_timestamps_and_phase_paths_are_rejected(self):
        cases = (
            (resolve(False, 10), "integer microseconds"),
            (resolve(0, 10, ("native_driver", 0, 11)), "inside its resolution"),
            (resolve(0, 10, ("other", 0, 10)), "unknown phase"),
            (resolve(0, 10, pipeline=""), "pipeline must be a nonempty string"),
        )
        for resolution, expected_error in cases:
            with self.subTest(resolution=resolution), self.assertRaisesRegex(ValueError, expected_error):
                audit_wait(sample_wait(resolution))


if __name__ == "__main__":
    unittest.main()
