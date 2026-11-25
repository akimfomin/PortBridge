import json
from pathlib import Path
import re
import unittest

from portbridge.github import API
from portbridge.lab import TASKS
from portbridge.lab_intake import ISSUE_PREFIX, REPOSITORY, classify_event, mapped_tasks
from portbridge.lab_reports import REVIEW_HEADER, report_sources
from test_lab_reports import structured_comment


def event_for(task, number, *, action="created", association="NONE"):
    source = f"{ISSUE_PREFIX}{number}"
    return {
        "action": action, "repository": {"full_name": REPOSITORY, "private": False},
        "issue": {"number": number, "html_url": source, "url": f"{API}/repos/{REPOSITORY}/issues/{number}"},
        "comment": structured_comment(task, source, 8, equipment=task["equipment"][0], association=association),
    }


class LabIntakeTest(unittest.TestCase):
    def test_report_receipt_uses_task_on_shared_issue_and_excludes_raw_input(self):
        task = mapped_tasks(9)[0]
        self.assertGreater(len(mapped_tasks(9)), 1)
        event = event_for(task, 9)
        event["comment"]["body"] += "\n\nExtra free text to exclude"
        receipt = classify_event(event)
        self.assertEqual(receipt["entries"], [
            {"task": task["id"], "kind": "report", "state": "observed", "authority": "community", "outcome": "pass"},
        ])
        self.assertNotIn("free text", json.dumps(receipt))
        self.assertEqual(receipt["comment"], f"{ISSUE_PREFIX}9#issuecomment-8")

    def test_markdown_report_header_still_counts_after_edit(self):
        task = mapped_tasks(54)[0]
        event = event_for(task, 54, action="edited")
        original = event["comment"]["body"]
        event["changes"] = {"body": {"from": original}}
        event["comment"]["body"] = original.replace("test report", "**test report**")
        receipt = classify_event(event)
        self.assertEqual([(entry["kind"], entry["state"]) for entry in receipt["entries"]],
                         [("report", "observed")])

    def test_review_receipt_requires_an_owner_in_the_designated_thread(self):
        task = mapped_tasks(54)[0]
        event = event_for(task, 54, association="OWNER")
        event["comment"]["body"] = "\n".join((
            REVIEW_HEADER, f"Task: {task['id']}", f"Report: {ISSUE_PREFIX}54#issuecomment-7",
            f"Body SHA-256: {'a' * 64}", "Decision: approve",
        ))
        receipt = classify_event(event)
        self.assertEqual(receipt["entries"], [
            {"task": task["id"], "kind": "review", "decision": "approve", "state": "observed"},
        ])
        event["comment"]["author_association"] = "MEMBER"
        self.assertIsNone(classify_event(event))

        task = mapped_tasks(4)[0]
        event = event_for(task, 4, association="OWNER")
        event["comment"]["body"] = "\n".join((
            REVIEW_HEADER, f"Task: {task['id']}", f"Report: {ISSUE_PREFIX}4#issuecomment-7",
            f"Body SHA-256: {'a' * 64}", "Decision: approve",
        ))
        self.assertNotEqual(report_sources(task)[0], f"{ISSUE_PREFIX}4")
        self.assertIsNone(classify_event(event))

    def test_changed_or_deleted_report_only_records_removal(self):
        task = mapped_tasks(54)[0]
        edited = event_for(task, 54, action="edited")
        edited["changes"] = {"body": {"from": edited["comment"]["body"]}}
        edited["comment"]["body"] = "Replaced"
        deleted = event_for(task, 54, action="deleted")
        for event in (edited, deleted):
            with self.subTest(action=event["action"]):
                self.assertEqual(classify_event(event)["entries"], [
                    {"task": task["id"], "kind": "report", "state": "removed"},
                ])

    def test_unmapped_private_pr_and_wrong_comment_identity_are_ignored(self):
        task = mapped_tasks(54)[0]
        self.assertIsNone(classify_event(event_for(task, 55)))
        for section, key, value in (
            ("repository", "full_name", "someone/PortBridge"),
            ("repository", "private", True),
            ("issue", "pull_request", {}),
            ("issue", "url", f"{API}/repos/{REPOSITORY}/issues/55"),
            ("comment", "html_url", f"{ISSUE_PREFIX}55#issuecomment-8"),
            ("comment", "user", {"type": "Bot"}),
            ("comment", "body", "Unstructured comment"),
        ):
            with self.subTest(section=section, key=key):
                event = event_for(task, 54)
                event[section][key] = value
                self.assertIsNone(classify_event(event))

    def test_workflow_prefilter_matches_current_local_report_threads(self):
        workflow = Path(__file__).resolve().parents[1] / ".github/workflows/lab-intake.yml"
        text = workflow.read_text(encoding="utf-8")
        workflow_numbers = set(json.loads(re.search(r"fromJSON\('(\[[0-9,]+\])'\)", text)[1]))
        mapped_numbers = {int(url.removeprefix(ISSUE_PREFIX)) for task in TASKS
                          for url in report_sources(task) if url.startswith(ISSUE_PREFIX)}
        self.assertEqual(workflow_numbers, mapped_numbers)
        for needle in (":", "=", REVIEW_HEADER.casefold()):
            self.assertIn(f"'{needle}'", text)
