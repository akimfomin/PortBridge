"""Plan parallel Test Lab checks for volunteers with public matching opt-in evidence."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from .activity import source_time
from .catalog import ReadOnlyCatalog, public_url
from .lab import build_lab
from .preflight import snapshot
from .radar import report_check, within
from .tester_discovery import LOGIN, REPORT_AGE


def latest_scoped_reports(tasks, target, equipment, now):
    """Keep the latest consent decision for each compatible hardware and OS scope."""
    profile = target.get("report_profile")
    systems = {system.casefold() for system in target["os"]}
    latest = {}
    for task in tasks:
        if not profile or task.get("report_profile") != profile:
            continue
        sync = task.get("report_sync", {})
        fresh = report_check(sync, now)["state"] == "fresh"
        for report in sync.get("reports", []):
            author, vendor, system = (report.get(key, "") or "" for key in ("author", "equipment", "os_family"))
            if (not isinstance(author, str) or not LOGIN.fullmatch(author) or vendor not in equipment
                    or not isinstance(system, str) or system.casefold() not in systems):
                continue
            reported = report.get("reported_at")
            updated = report.get("updated_at") or report.get("revised_at") or reported
            if not within(reported, now, REPORT_AGE) or not within(updated, now, REPORT_AGE):
                continue
            url = report.get("url")
            if not public_url(url):
                continue
            key = (author.casefold(), vendor, system.casefold())
            # An edit can revoke consent on an older report. On equal timestamps,
            # a refusal takes precedence over an affirmative report.
            order = (source_time(updated), report.get("opt_in") is not True, source_time(reported), url, fresh)
            if key not in latest or order > latest[key][0]:
                latest[key] = (order, fresh, report)
    return latest


def candidates_by_equipment(tasks, target, equipment, now):
    candidates = {vendor: {} for vendor in equipment}
    for (author, vendor, _), (order, fresh, report) in latest_scoped_reports(tasks, target, equipment, now).items():
        if not fresh or report.get("opt_in") is not True or report.get("authority") != "approved":
            continue
        if report.get("outcome") != "pass" or not report.get("hardware") or not report.get("os"):
            continue
        current = candidates[vendor].get(author)
        if current is None or order > current[0]:
            candidates[vendor][author] = (order, report)
    return {vendor: [report for _, report in sorted(rows.values(), key=lambda item: item[0], reverse=True)]
            for vendor, rows in candidates.items()}


def unique_assignments(candidates):
    """Match the most cells possible, with at most one cell per volunteer."""
    matched = {}

    def take(vendor, visited):
        for report in candidates[vendor]:
            author = report["author"].casefold()
            if author in visited:
                continue
            visited.add(author)
            if author not in matched or take(matched[author][0], visited):
                matched[author] = (vendor, report)
                return True
        return False

    for vendor in sorted(candidates, key=lambda kind: (len(candidates[kind]), kind)):
        take(vendor, set())
    return dict(matched.values())


def build_plan(lab, task_id, *, now=None):
    """Return proposal-only assignments from a read-only Lab snapshot."""
    now = now or datetime.now(timezone.utc)
    tasks = lab["tasks"]
    target = next((task for task in tasks if task["id"] == task_id), None)
    if target is None:
        raise ValueError("Task not found in this Test Lab snapshot.")
    checks = {cell["equipment"]: cell["state"] for cell in target.get("coverage", [])}
    pending = [vendor for vendor in target["equipment"] if checks.get(vendor) in {"missing", "partial"}]
    freshness = report_check(target.get("report_sync", {}), now)
    ready = target["status"] == "needs_run" and freshness["state"] == "fresh" and bool(pending)
    candidates = candidates_by_equipment(tasks, target, pending, now) if ready else {}
    matches = unique_assignments(candidates)
    if target.get("coverage_policy") != "all":
        matches = dict(list(sorted(matches.items()))[:1])

    return {
        "task_id": task_id,
        "target_url": target["result_url"],
        "status": target["status"],
        "freshness": freshness,
        "can_plan": ready,
        "cells": [{"equipment": vendor, "coverage": checks.get(vendor, "unknown"),
                   "eligible_volunteers": len(candidates.get(vendor, []))}
                  for vendor in target["equipment"]],
        "proposals": [{"equipment": vendor, "volunteer": report["author"], "hardware": report["hardware"],
                       "os": report["os"], "evidence_url": report["url"], "reported_at": report["reported_at"],
                       "state": "proposed"}
                      for vendor, report in sorted(matches.items())],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help="read-only catalog SQLite database; omit to use public Test Lab")
    parser.add_argument("--task", required=True, help="exact Test Lab task identifier")
    args = parser.parse_args(argv)
    try:
        lab = snapshot("lab") if args.db is None else build_lab(ReadOnlyCatalog(args.db))
        plan = build_plan(lab, args.task)
    except (OSError, sqlite3.Error, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(plan, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
