"""Build a public view of work observed across the tracked projects."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

from .matching import canonical_url, source_revision, source_url_aliases
from .preflight import english_text


WINDOW_DAYS = 7
EVENTS_PER_KIND = 10
OPPORTUNITY_LIMIT = 6
COUNT_FOR = {
    "merged_pr": "merged", "open_pr": "open", "revision_change": "changed",
    "status_change": "changed", "verified_result": "verified",
}
HANDOFFS = Path(__file__).with_name("data") / "handoffs.json"
ORIGINAL_RESEARCH = HANDOFFS.with_name("research.json")
HANDOFF_STAGES = {
    "delivered_url": "delivered", "independent_url": "independently_reproduced",
    "review_url": "formally_reviewed", "adopted_url": "adopted",
}


def source_time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def public_text(title, en_title=None, *, summary=None, en_summary=None, next_step=None, en_next_step=None):
    fields = {key: value for key, value in (("title", title), ("summary", summary), ("next_step", next_step))
              if value is not None}
    english = {key: value for key, value in (("title", en_title), ("summary", en_summary), ("next_step", en_next_step))
               if value is not None}
    if english:
        fields["translations"] = {"en": english}
    return fields


def is_test_result(evidence):
    return (evidence["kind"] in {"independent", "automated_test"}
            and evidence.get("outcome") in {"passed", "failed", "mixed"}
            and all(evidence.get(key) for key in ("observed", "revision", "platforms")))


def pull_events(observations):
    for row in observations:
        if row["kind"] != "pr" or row["status"] not in {"open", "merged"}:
            continue
        status = row["status"]
        merged = status == "merged"
        # A later comment can update a merged PR, so use GitHub's merge date.
        date = row["metadata"].get("merged_at") if merged else row["updated_at"]
        yield {
            "id": f"pr:{row['project']}:{row['source_id']}:{status}",
            "kind": "merged_pr" if merged else "open_pr", "project": row["project"], "status": status,
            "title": row["title"], "url": row["url"], "at": date,
            "date_basis": "merged_at" if merged else "updated_at",
            "revision": source_revision(row), "draft": not merged and row["metadata"].get("draft") is True,
        }


def change_events(changes, titles):
    for change in changes:
        url = change["url"]
        previous, current = change["previous_revision"], change["revision"]
        revision_changed = previous and current and previous != current
        yield {
            "id": f"change:{change['id']}", "kind": "revision_change" if revision_changed else "status_change",
            "project": change["project"], "source_kind": change["kind"], "title": titles.get(canonical_url(url), url),
            "url": url, "at": change["observed_at"], "date_basis": "observed_at", "status": change["status"],
            "previous_status": change["previous_status"], "revision": current, "previous_revision": previous,
        }


def test_events(cards):
    seen = set()
    for card in cards:
        for solution in card["solutions"]:
            project = solution["project"]
            for evidence in solution["evidence"]:
                if not is_test_result(evidence):
                    continue
                date = evidence.get("reported_at")
                url, revision = evidence["url"], evidence["revision"]
                key = (project, url, revision, evidence["kind"], evidence["outcome"])
                if not source_time(date) or key in seen:
                    continue
                seen.add(key)
                ident = sha256("\n".join(key).encode("utf-8")).hexdigest()[:20]
                yield {
                    "id": f"test:{ident}", "kind": "verified_result", "project": project, "status": "reviewed",
                    "url": url, "at": date, "date_basis": "reported_at", "problem_id": card["id"],
                    "outcome": evidence["outcome"], "revision": revision, "platforms": evidence["platforms"],
                    "evidence_kind": evidence["kind"],
                    **public_text(evidence["title"], english_text(evidence, "title"), summary=evidence["observed"],
                                  en_summary=english_text(evidence, "observed")),
                }


def current_opportunities(cards, drafts):
    reviewed = {card["id"]: card for card in cards if card["status"] != "resolved"}
    found = []
    for draft in drafts:
        card = reviewed.get(draft["problem_id"])
        if card is None or draft["target_status"] != "open":
            continue
        project = draft["source_project"]
        target = draft["target_url"]
        comparison = draft["mode"] == "comparison"
        evidence = [entry for solution in card["solutions"] if solution["project"] == project
                    for entry in solution["evidence"] if is_test_result(entry)
                    and any(canonical_url(url) == canonical_url(target) for url in entry.get("check_for", ()))
                    and (not comparison or entry["outcome"] == "passed")]
        if not evidence:
            continue
        result = max(evidence, key=lambda row: source_time(row.get("reported_at")) or datetime.min.replace(tzinfo=timezone.utc))
        step = ("Повторите тот же тест в открытой ветке и укажите ревизию и результат." if comparison else
                "Сверьте исходную проверку с открытой веткой и опишите, что удалось воспроизвести.")
        en_step = ("Repeat this test on the open branch and record the revision and result." if comparison else
                   "Compare the reviewed check with the open branch and report what you can reproduce.")
        found.append({
            "id": draft["id"], "kind": "reuse_test" if comparison else "review_prior_work",
            "projects": [project, draft["target_project"]], "problem_id": card["id"], "url": target,
            "source_url": result["url"], "target_url": target, "revision": result["revision"],
            "outcome": result["outcome"], "platforms": result["platforms"],
            **public_text(card["title"], english_text(card, "title"), summary=result["observed"],
                          en_summary=english_text(result, "observed"), next_step=step, en_next_step=en_step),
        })
        if len(found) == OPPORTUNITY_LIMIT:
            break
    return found


def handoff_summary(cards, projects, observations, as_of):
    """Count only reviewed contributions with explicit public proof for each stage."""
    cases = {card["id"]: card for card in cards}
    repos = {project["slug"]: project["repo"] for project in projects}
    merged_heads = {
        (row["project"], canonical_url(row["url"])): source_revision(row)
        for row in observations
        if row["kind"] == "pr" and row["status"] == "merged"
        and (merged_at := source_time(row["metadata"].get("merged_at"))) and merged_at <= as_of
    }
    counts = dict.fromkeys(HANDOFF_STAGES.values(), 0)
    items, seen = [], set()
    for row in json.loads(HANDOFFS.read_text(encoding="utf-8")):
        case = cases.get(row["problem_id"])
        repo = repos.get(row["project"])
        if case is None or repo is None:
            continue
        if not any(solution["project"] == row["project"] for solution in case["solutions"]):
            raise ValueError(f"Handoff project is missing from case: {case['id']}")
        delivery = row["delivered_url"]
        revision = row["revision"]
        repo_urls = "|".join(map(re.escape, source_url_aliases(f"https://github.com/{repo}")))
        prefix = f"(?:{repo_urls})/"
        subject = r"(?:pull|issues)/[1-9][0-9]*"
        if not isinstance(delivery, str) or not re.fullmatch(prefix + subject, delivery, re.I):
            raise ValueError(f"Invalid handoff delivery: {case['id']}")
        if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError(f"Invalid handoff revision: {case['id']}")
        identity = canonical_url(delivery)
        if identity in seen:
            raise ValueError(f"Duplicate handoff delivery: {case['id']}")
        seen.add(identity)
        delivery_urls = "|".join(map(re.escape, source_url_aliases(delivery)))
        proofs = {"independent_url": f"(?:{delivery_urls})" + r"#issuecomment-[1-9][0-9]*",
                  "review_url": f"(?:{delivery_urls})" + r"#pullrequestreview-[1-9][0-9]*",
                  "branch_implementation_url": prefix + r"commit/[0-9a-f]{40}",
                  "adopted_url": prefix + rf"(?:{subject}(?:#issuecomment-[1-9][0-9]*)?|commit/[0-9a-f]{{40}})"}
        item = {"problem_id": case["id"], "project": row["project"], "delivered_url": delivery, "revision": revision,
                **public_text(case["title"], english_text(case, "title"))}
        for key, pattern in proofs.items():
            if key in row:
                value = row[key]
                if not isinstance(value, str) or not re.fullmatch(pattern, value, re.I):
                    raise ValueError(f"Invalid handoff proof ({key}): {case['id']}")
                item[key] = value
        if "adopted_url" not in item and merged_heads.get((row["project"], canonical_url(delivery))) == revision:
            item["adopted_url"] = delivery
        for field, stage in HANDOFF_STAGES.items():
            if field in item:
                counts[stage] += 1
        items.append(item)
    return {"counts": counts, "items": items}


def showcased_research(cards, observations, handoffs):
    latest = {canonical_url(row["url"]): row for row in observations}
    by_case = {row["problem_id"]: row for row in handoffs["items"]}
    items = []
    for card in cards:
        if not card.get("showcase"):
            continue
        handoff = by_case.get(card["id"], {})
        solution = next((row for row in card["solutions"] if row["project"] == handoff.get("project")),
                        card["solutions"][0])
        subject = solution["source_refs"][0]["url"]
        evidence = solution["evidence"][0]
        source = latest.get(canonical_url(subject))
        item = {"problem_id": card["id"], "project": solution["project"],
                "at": card["recorded_at"], "delivered_url": evidence["url"], "source_url": subject,
                **public_text(card["title"], english_text(card, "title"), summary=card["summary"],
                              en_summary=english_text(card, "summary"))}
        if source:
            item["source_state"] = "draft" if source["metadata"].get("draft") else source["status"]
            item["checked_at"] = source["fetched_at"]
            item["current_revision"] = source_revision(source)
        for key in ("independent_url", "branch_implementation_url", "adopted_url"):
            if link := handoff.get(key):
                item[key] = link
        items.append(item)
    return sorted(items, key=lambda row: (row["at"], row["problem_id"]), reverse=True)


def build_activity(catalog, *, now=None, projects=None, cards=None, observations=None, health=None, drafts=None):
    from .lab import build_lab
    from .radar import build_radar

    as_of = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    start = as_of - timedelta(days=WINDOW_DAYS)
    projects = catalog.projects() if projects is None else projects
    cards = catalog.problems() if cards is None else cards
    observations = catalog.observations(limit=None) if observations is None else observations
    health = catalog.health() if health is None else health
    drafts = catalog.outreach() if drafts is None else drafts
    counts = dict.fromkeys(COUNT_FOR.values(), 0)
    per_project = {
        row["slug"]: {"slug": row["slug"], "name": row["name"], "url": row["url"], "status": row["sync_status"],
                      "last_success": row["last_success"], "last_activity": None, "counts": counts.copy()}
        for row in projects
    }
    titles = {canonical_url(row["url"]): row["title"] for row in observations}
    matching = []
    # The default source_changes limit is for paginated readers. This summary counts all events in its window.
    changes = catalog.source_changes(limit=-1)
    for source in (pull_events(observations), change_events(changes, titles), test_events(cards)):
        for event in source:
            date = source_time(event["at"])
            project = per_project.get(event["project"])
            if date is None or not start <= date <= as_of or project is None:
                continue
            event["at"] = date.isoformat(timespec="seconds")
            matching.append(event)
            key = COUNT_FOR[event["kind"]]
            counts[key] += 1
            project["counts"][key] += 1

    events = []
    displayed = Counter()
    for event in sorted(matching, key=lambda row: (row["at"], row["id"]), reverse=True):
        project = per_project[event["project"]]
        if project["last_activity"] is None:
            project["last_activity"] = event
        kind = event["kind"]
        if displayed[kind] < EVENTS_PER_KIND:
            displayed[kind] += 1
            events.append(event)

    opportunities = current_opportunities(cards, drafts)
    radar = build_radar(projects, observations, changes, build_lab(catalog), opportunities, as_of)
    handoffs = handoff_summary(cards, projects, observations, as_of)
    return {"as_of": as_of.isoformat(), "refreshed_at": health["refresh_at"], "health": health["status"],
            "window_days": WINDOW_DAYS, "window_start": start.isoformat(),
            "counts": {**counts, "projects": len(per_project)}, "projects": list(per_project.values()),
            "handoffs": handoffs, "research": showcased_research(cards, observations, handoffs),
            "original_research": json.loads(ORIGINAL_RESEARCH.read_text(encoding="utf-8")),
            "events": events, "opportunities": opportunities, "radar": radar}
