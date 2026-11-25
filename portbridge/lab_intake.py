"""Classify GitHub issue comment events for reviewed local Test Lab threads."""
import json
import os
from pathlib import Path

from .github import API
from .lab import TASKS
from .lab_report_formats import REPORT_HEADER
from .lab_reports import (REVIEW_HEADER, monitored, normalize_report, normalize_thread_review,
                          report_source, report_sources)
from .tester_discovery import MAX_BODY, report_lines


REPOSITORY = "akimfomin/PortBridge"
ISSUE_PREFIX = f"https://github.com/{REPOSITORY}/issues/"


def mapped_tasks(number, tasks=TASKS):
    source = f"{ISSUE_PREFIX}{number}"
    return [task for task in tasks if monitored(task) and source in report_sources(task)]


def _matches(value, expected):
    return isinstance(value, str) and value.casefold() == expected.casefold()


def _classify(comment, task, source, repo, issue):
    body = comment.get("body")
    if not isinstance(body, str) or len(body) > MAX_BODY:
        return None
    marker_text = body.casefold()
    if (REVIEW_HEADER.casefold() in marker_text
            and (review := normalize_thread_review(comment, task, source, repo, issue))):
        return {"kind": "review", "decision": review["review_decision"]}
    if any(line.strip().casefold() == REPORT_HEADER for line in report_lines(body)):
        if report := normalize_report(comment, task, source, repo, issue):
            return {"kind": "report", "authority": report["authority"], "outcome": report["outcome"]}
    return None


def classify_event(event, tasks=TASKS):
    """Extract a receipt from an Actions event. Scheduled scans verify current evidence."""
    if not isinstance(event, dict) or event.get("action") not in ("created", "edited", "deleted"):
        return None
    repository, issue, comment = (event.get(key) for key in ("repository", "issue", "comment"))
    if not all(isinstance(item, dict) for item in (repository, issue, comment)):
        return None
    if (not _matches(repository.get("full_name"), REPOSITORY)
            or repository.get("private") is not False or "pull_request" in issue):
        return None
    number, ident = issue.get("number"), comment.get("id")
    if any(type(item) is not int or item < 1 for item in (number, ident)):
        return None
    source = f"{ISSUE_PREFIX}{number}"
    issue_url = f"{API}/repos/{REPOSITORY}/issues/{number}"
    if not _matches(issue.get("html_url"), source) or not _matches(issue.get("url"), issue_url):
        return None

    previous = None
    if event["action"] == "edited":
        changes = event.get("changes")
        body_change = changes.get("body") if isinstance(changes, dict) else None
        if isinstance(body_change, dict) and isinstance(body_change.get("from"), str):
            previous = {**comment, "body": body_change["from"]}

    entries = []
    for task in mapped_tasks(number, tasks):
        repo, issue_api = report_source(task, source)
        current = _classify(comment, task, source, repo, issue_api)
        before = _classify(previous, task, source, repo, issue_api) if previous else None
        if before and current and before["kind"] == current["kind"]:
            before = None
        if before:
            entries.append({"task": task["id"], "kind": before["kind"], "state": "removed"})
        if current and event["action"] == "deleted":
            entries.append({"task": task["id"], "kind": current["kind"], "state": "removed"})
        elif current:
            entries.append({"task": task["id"], "state": "observed", **current})
    if not entries:
        return None
    return {"version": 1, "action": event["action"], "comment": f"{source}#issuecomment-{ident}", "entries": entries}


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    receipt = classify_event(event)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        print(f"recognized={str(receipt is not None).lower()}", file=output)
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
        print("## Test Lab report intake", file=summary)
        if receipt is None:
            print("No structured report or authorized review matched a task on this issue.", file=summary)
            return
        print(f"Event: {receipt['action']} · [Source comment]({receipt['comment']})", file=summary)
        for entry in receipt["entries"]:
            print(f"- `{entry['task']}` — {entry['kind']} {entry['state']}", file=summary)
        print("\nThe next scheduled or maintainer-triggered scan checks the current source before publication.",
              file=summary)
    Path("report-intake.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
