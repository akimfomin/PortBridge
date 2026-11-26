import csv
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "audit" / "cbv_ab.py"
FIELDS = ("Application", "ProcessID", "SwapChainAddress", "TimeInSeconds", "MsBetweenPresents")


class CBVCaptureTest(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.captures = [Path(self.folder.name) / f"run{i}.csv" for i in range(6)]

    def make_capture(self, path, *, seconds=90, mixed=None, diagnostics=True):
        with path.open("w", newline="", encoding="utf8") as stream:
            writer = csv.writer(stream)
            writer.writerow(FIELDS)
            for index in range(seconds * 20 + 1):
                pid = 1 if mixed == "process" and index == 100 else 42
                chain = "0x1" if mixed == "swapchain" and index == 100 else "0x2"
                interval = 90 if mixed == "gap" and index == 100 else 50
                writer.writerow(("sample.exe", pid, chain, index / 20, interval))
        if diagnostics:
            path.with_suffix(".log").write_text(
                "CBV snapshots since last frame report hits=75 misses=25 bytes_avoided=3072 invalidated=4\n",
                encoding="utf8",
            )

    def run_analyzer(self):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, self.captures)],
                              capture_output=True, text=True, check=False)

    def test_valid_alternating_series(self):
        for path in self.captures:
            self.make_capture(path)
        result = self.run_analyzer()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["paired_median_on_minus_off_ms"], [0, 0, 0])
        self.assertEqual(report["runs"][0]["seconds"], 90)
        self.assertEqual(report["runs"][1]["eligible_reuse_percent"], 75)
        self.assertNotIn("eligible_reuse_percent", report["runs"][0])

    def test_rejects_incomplete_or_mixed_series(self):
        for path in self.captures:
            self.make_capture(path, diagnostics=False)
        for alterations, message in [
            ({"seconds": 10}, "90 seconds"),
            ({"mixed": "process"}, "one identified process and swapchain"),
            ({"mixed": "swapchain"}, "one identified process and swapchain"),
            ({"mixed": "gap"}, "discontinuous timestamps"),
            ({"diagnostics": False}, "run1.log"),
        ]:
            with self.subTest(alterations=alterations):
                self.make_capture(self.captures[1], **alterations)
                result = self.run_analyzer()
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
                self.assertEqual(result.stdout, "")
                self.captures[1].with_suffix(".log").unlink(missing_ok=True)
