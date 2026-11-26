from subprocess import CompletedProcess
import unittest
from unittest.mock import patch

from portbridge.merge_check import changed_paths, compare, report


URL = "https://github.com/LooperSalty/AnyXboxX/pull/433"
TARGET = "a" * 40


class MergeCheckTest(unittest.TestCase):
    def test_rejects_untrusted_url_and_abbreviated_target_before_requests(self):
        bad = [("https://example.org/a/b/pull/1", TARGET),
               ("https://github.com/a/b/pull/1?x=2", TARGET),
               (URL, "--upload-pack=invalid"), (URL, "abc")]
        with patch("portbridge.merge_check.subprocess.run") as git:
            for url, target in bad:
                with self.subTest(url=url, target=target), self.assertRaises(ValueError):
                    compare(url, target)
            git.assert_not_called()

    def test_rejects_a_pr_that_moved_after_fetch_while_using_public_git(self):
        head = "b" * 40
        other = "c" * 40
        ref = "refs/pull/433/head"

        def run(args, **kwargs):
            stdout = b""
            if "rev-parse" in args:
                stdout = f"{head}\n{TARGET}\n".encode()
            if "ls-remote" in args:
                stdout = f"{other}\t{ref}\n".encode()
            return CompletedProcess(args, 0, stdout=stdout, stderr=b"")

        with patch("portbridge.merge_check.subprocess.run", side_effect=run) as git:
            result = compare(URL, TARGET)
        self.assertEqual(result["status"], "unverified")
        self.assertIn("moved", result["reason"])
        self.assertTrue(any(f"+{ref}:refs/compare/head" in call.args[0] for call in git.call_args_list))
        self.assertFalse(any("merge-tree" in call.args[0] for call in git.call_args_list))

    def test_linked_test_survives_the_changed_file_display_limit(self):
        raw = b"\0".join([f"src/file{n:02}.rs".encode() for n in range(26)] + [b"tests/test_regression.py"])
        displayed, tests = changed_paths(raw)
        self.assertEqual(len(displayed), 25)
        self.assertEqual(tests, ["tests/test_regression.py"])

    def test_keeps_conflict_result_if_public_catalog_fails(self):
        outcome = {"status": "conflict", "head": "b" * 40,
                   "receiving_commit_url": "https://github.com/LooperSalty/AnyXboxX/commit/" + TARGET,
                   "conflicts": ["src/draw.rs"], "changed_files": ["src/draw.rs", "src/cut_tables_tests.rs"],
                   "changed_tests": ["src/cut_tables_tests.rs"]}
        with patch("portbridge.merge_check.compare", return_value=outcome), \
             patch("portbridge.merge_check.public_preflight", side_effect=OSError):
            result = report(URL, TARGET)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["catalog_status"], "unavailable")
        self.assertTrue(result["test_files"][0].endswith("/src/cut_tables_tests.rs"))
        self.assertIn("negative control", result["next_test"])

    def test_unverified_comparison_does_not_add_a_test_verdict(self):
        result = {"status": "unverified", "reason": "The PR moved"}
        with patch("portbridge.merge_check.compare", return_value=result), \
             patch("portbridge.merge_check.public_preflight") as preflight:
            self.assertEqual(report(URL, TARGET), result)
            preflight.assert_not_called()
