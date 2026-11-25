"""Build a read-only research queue from the catalog and Test Lab."""

from collections import Counter, defaultdict
from datetime import timedelta
from hashlib import sha256
import re

from .activity import source_time
from .catalog import public_url, source_sync_failed
from .github import WORK_URL
from .matching import canonical_url, source_revision, subject_kind


FRESH_FOR = timedelta(hours=2)
RECENT_CHANGE = timedelta(days=7)
QUEUE_LIMIT = 24
CROSS_LIMIT = 6
PRIORITY_RANK = {"high": 0, "normal": 1, "exploratory": 2}
SYMBOL = re.compile(r"[a-z][a-z0-9_]{3,95}", re.I)


def within(value, now, span):
    date = source_time(value)
    return date is not None and now - span <= date <= now


def identify(kind, *identity):
    digest = sha256("\n".join(identity).encode("utf-8")).hexdigest()[:24]
    return f"{kind}:{digest}"


def proof(role, url, revision=None):
    return {"role": role, "url": url, "revision": revision}


def observation_check(row, projects, now):
    if row is None:
        return {"state": "unknown", "checked_at": None}
    checked = row.get("fetched_at")
    if source_sync_failed(projects.get(row["project"], {}), row["url"]):
        state = "stale" if checked else "unknown"
    else:
        state = "fresh" if within(checked, now, FRESH_FOR) else "stale" if checked else "unknown"
    return {"state": state, "checked_at": checked}


def report_check(sync, now):
    checked = sync.get("checked_at")
    fresh = sync.get("state") == "fresh" and within(checked, now, FRESH_FOR)
    return {"state": "fresh" if fresh else "stale" if checked else "unknown", "checked_at": checked}


def lab_action(task, kind, priority, confidence, check, action, criteria, *,
               equipment=(), extra_sources=(), subject=None):
    target = task["result_url"] if subject is None else subject["url"]
    revision = source_revision(subject) if subject is not None else None
    task_proofs = [proof("procedure", task["procedure_url"]), *extra_sources]
    return {
        "id": identify(kind, task["id"], canonical_url(target)), "kind": kind,
        "state": kind if check["state"] == "fresh" else "verify_sources",
        "priority": priority, "confidence": confidence, "freshness": check,
        "task_id": task["id"], "projects": task["projects"], "equipment": sorted(equipment),
        "target_url": target, "target_revision": revision,
        "sources": [proof("target", target, revision), *task_proofs],
        "demand": "test_lab_task", "effort": "hardware_run" if equipment else "source_review",
        "impact": "pinned_check",
        "title": task.get("translations", {}).get("ru", {}).get("title", task["title"]),
        "next_step": action[0], "criterion": criteria[0],
        "translations": {"en": {"title": task["title"], "next_step": action[1], "criterion": criteria[1]}},
    }


def previous_pin(current, pins, changes, now):
    """Follow the observed head changes back to a revision on the task card."""
    for change in sorted(changes, key=lambda item: (item["observed_at"], item.get("id", 0)), reverse=True):
        observed = source_time(change["observed_at"])
        if observed is None or observed > now or change["revision"] != current:
            continue
        current = change["previous_revision"]
        if current in pins:
            return current
    return None


def revision_action(task, rows, changes, projects, now):
    pins = {entry["sha"].lower(): entry["url"] for entry in task["revisions"]}
    for url in dict.fromkeys((task["source_url"], task["result_url"])):
        key = canonical_url(url)
        row = rows.get(key)
        if row is None or row["kind"] != "pr" or row["status"] != "open" or row["metadata"].get("draft"):
            continue
        current = source_revision(row)
        if current is None or current in pins:
            continue
        if old := previous_pin(current, pins, changes.get(key, ()), now):
            return lab_action(task, "recheck_revision", "high", "indexed_change",
                              observation_check(row, projects, now),
                              ("Сверьте изменения после закреплённой версии и определите, нужен ли новый прогон.",
                               "Inspect changes since the tested revision and determine whether a rerun is needed."),
                              ("Отметьте применимость теста к новой версии или приложите повторный результат.",
                               "Record why the existing test still applies, or attach a result on the new revision."),
                              extra_sources=[proof("tested_revision", pins[old], old)], subject=row)
    return None


def lab_actions(tasks, rows, changes, projects, now):
    for task in tasks:
        if task["status"] == "blocked" or task.get("adoption") == "adopted":
            continue
        if recheck := revision_action(task, rows, changes, projects, now):
            yield recheck
            continue

        target = rows.get(canonical_url(task["result_url"]))
        if target and (target["status"] != "open" or target["metadata"].get("draft")):
            continue
        sync = task.get("report_sync")
        check = report_check(sync, now) if sync is not None else observation_check(target, projects, now)
        reports = sync.get("reports", []) if sync is not None else []
        coverage = {cell["equipment"]: cell["state"] for cell in task.get("coverage", [])}
        review_needed = task["status"] == "awaiting_review" or bool(
            {"reported", "contradicted"}.intersection(coverage.values()))
        evidence = [proof("report", report["url"], report.get("revision"))
                    for report in reports[-4:] if public_url(report.get("url"))]
        if review_needed and evidence:
            yield lab_action(task, "review_report", "high", "submitted_report", check,
                             ("Сверьте результаты и стенды с условиями проверки.",
                              "Compare the reported setups and outcomes with the check requirements."),
                             ("Зафиксируйте, какое покрытие подтверждено и какие проверки ещё нужны.",
                              "Record the coverage accepted for review and the remaining gaps."),
                             extra_sources=evidence)
        equipment = {vendor for vendor in task["equipment"] if coverage.get(vendor, "missing") in {"missing", "partial"}}
        pending_review = review_needed and evidence and task.get("coverage_policy", "any") != "all"
        if task["status"] == "needs_run" and equipment and not pending_review:
            yield lab_action(task, "cover_hardware", "normal", "curated_check", check,
                             ("Откройте задачу и выберите совместимый стенд для закреплённого теста.",
                              "Open the task and select a compatible setup for the pinned check."),
                             ("Отчёт содержит точную версию, сведения о стенде и итоги всех обязательных случаев.",
                              "The report names the exact revision, the setup, and all required case outcomes."),
                             equipment=equipment, extra_sources=[
                                 proof("pinned_revision", entry["url"], entry["sha"]) for entry in task["revisions"]
                             ])


def technical_symbols(row):
    values = (row["metadata"].get("technical") or {}).get("signals", ())
    return {value.casefold() for value in values if isinstance(value, str) and SYMBOL.fullmatch(value)}


def public_comparison(row, projects):
    project = projects.get(row["project"], {})
    source = project.get("sources", {}).get(row["kind"], {})
    return "unavailable" not in (project.get("sync_status"), source.get("sync_status"))


def comparison_actions(rows, projects, excluded, now):
    seen = set()
    live, held = [], []
    # Only recently observed direct references are compared. A shared symbol alone
    # is insufficient and there is no all-pairs pass over the full index.
    for target_key, target in sorted(rows.items(), key=lambda entry: (
            entry[1].get("fetched_at") or "", entry[0]), reverse=True):
        if (target_key in excluded or target["status"] != "open" or target["kind"] not in {"issue", "pr"}
                or target["metadata"].get("draft") or subject_kind(target["title"]) != "implementation"
                or not within(target.get("fetched_at"), now, RECENT_CHANGE)
                or not public_comparison(target, projects)):
            continue
        symbols = technical_symbols(target)
        if not symbols:
            continue
        for reference in (target["metadata"].get("technical") or {}).get("references", ()):
            if not public_url(reference):
                continue
            source_key = canonical_url(reference)
            source = rows.get(source_key)
            if (source is None or source["project"] == target["project"] or source["metadata"].get("draft")
                    or source["status"] not in {"open", "merged", "closed"}
                    or subject_kind(source["title"]) != "implementation" or not public_comparison(source, projects)):
                continue
            source_revision_sha, target_revision_sha = source_revision(source), source_revision(target)
            if (source_revision_sha and source_revision_sha == target_revision_sha
                    or source["status"] == "closed" and not source_revision_sha):
                continue
            shared = sorted(symbols & technical_symbols(source))
            pair = tuple(sorted((target_key, source_key)))
            if not shared or pair in seen:
                continue
            seen.add(pair)
            target_check = observation_check(target, projects, now)
            source_check = observation_check(source, projects, now)
            if target_check["state"] == source_check["state"] == "fresh":
                check = min((target_check, source_check), key=lambda item: source_time(item["checked_at"]))
            else:
                check = target_check if target_check["state"] != "fresh" else source_check
            scope = ", ".join(shared[:4])
            criterion = "Укажите различия в реализации и опишите один проверяемый общий случай."
            item = {
                "id": identify("compare_sources", *pair), "kind": "compare_sources",
                "state": "compare_sources" if check["state"] == "fresh" else "verify_sources",
                "priority": "exploratory", "confidence": "direct_reference_with_symbols", "freshness": check,
                "projects": [source["project"], target["project"]], "equipment": [],
                "demand": "citing_discussion", "effort": "source_review", "impact": "cross_project_check",
                "target_url": target["url"], "target_revision": target_revision_sha,
                "sources": [{**proof("target", target["url"], target_revision_sha), "freshness": target_check},
                            {**proof("comparison", source["url"], source_revision_sha),
                             "freshness": source_check, "status": source["status"]}],
                "signals": shared[:4], "criterion": criterion,
                "translations": {"en": {
                    "title": target["title"],
                    "summary": f"The receiving discussion links the other project and both mention {scope}.",
                    "next_step": "Check what behavior the two sources actually share before proposing a test.",
                    "criterion": "Record implementation differences and one common check you can reproduce.",
                }},
                "title": target["title"],
                "summary": f"В открытой задаче есть ссылка на другой проект. В обоих источниках упоминается {scope}.",
                "next_step": "Сверьте, что именно можно проверить одинаковым тестом в двух проектах.",
            }
            if check["state"] == "fresh":
                live.append(item)
            elif len(held) < CROSS_LIMIT:
                held.append(item)
            if len(live) == CROSS_LIMIT:
                return live
    return (live + held)[:CROSS_LIMIT]


def build_radar(projects, observations, source_changes, lab, opportunities, now):
    """Derive the current queue without creating claims, decisions, or messages."""
    project_map = {row["slug"]: row for row in projects}
    rows = {canonical_url(row["url"]): row for row in observations if WORK_URL.fullmatch(row["url"])}
    changes = defaultdict(list)
    for change in source_changes:
        if change.get("previous_revision"):
            changes[canonical_url(change["url"])].append(change)
    excluded = {canonical_url(item["target_url"]) for item in opportunities}
    excluded.update(canonical_url(task["result_url"]) for task in lab["tasks"])
    actions = [*lab_actions(lab["tasks"], rows, changes, project_map, now),
               *comparison_actions(rows, project_map, excluded, now)]
    actions.sort(key=lambda item: (item["state"] == "verify_sources", PRIORITY_RANK[item["priority"]], item["id"]))
    return {"actions": actions[:QUEUE_LIMIT], "counts": dict(Counter(item["kind"] for item in actions))}
