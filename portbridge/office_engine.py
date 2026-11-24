"""Advance reviewed plans and propose a bounded next experiment from indexed evidence."""

import time
from urllib.parse import urlsplit

from .discussion import post_notice
from .matching import RelatedIndex, canonical_url, source_revision
from .office import (PLANS, check_sources, create_plan, dependencies, read_plan, reassign_revoked,
                     source_repo, step_for, watched_revisions)


PLAN_BASES = {"technical_signal", "instruction_variants", "shared_revision", "reference"}
EXTERNAL_CHECK_LIMIT = 12


def refresh_external_sources(exchange):
    """Read only exact GitHub sources selected in plans for reviewed candidates."""
    from .github import public_source_revisions

    with exchange._connect() as db:
        watched = {row["url"]: row["checked_at"] for row in db.execute("SELECT * FROM office_external_revisions")}
        approved = {row["repo"] for row in db.execute("SELECT repo FROM office_projects WHERE state='compare'")}
        rows = db.execute("""SELECT p.origin_url, p.comparison_url FROM office_plans p
            WHERE p.phase IN ('active', 'draft', 'done') AND EXISTS (
                SELECT 1 FROM topic_subscriptions s LEFT JOIN revoked_principals r ON r.principal_id=s.principal_id
                WHERE s.problem_id=p.problem_id AND r.principal_id IS NULL)""")
        wanted = {url for row in rows for url in row if source_repo(url) in approved}
    targets = sorted(wanted, key=lambda url: (watched.get(url, 0), url))[:EXTERNAL_CHECK_LIMIT]
    if not targets:
        return
    revisions = public_source_revisions(exchange.path, targets)
    with exchange._connect() as db:
        checked_at = int(time.time())
        db.executemany("""INSERT INTO office_external_revisions VALUES (?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET revision=excluded.revision, checked_at=excluded.checked_at""",
                       ((url, source_repo(url), revision, checked_at) for url, revision in revisions.items()))


def best_comparison(index, urls):
    matches = []
    for origin in sorted(map(canonical_url, urls)):
        if origin not in index.rows or index.rows[origin]["kind"] not in {"pr", "commit"}:
            continue
        for target, score, basis, signals in index.candidates(origin):
            if basis in PLAN_BASES and index.rows[target]["kind"] in {"pr", "commit"}:
                matches.append((-score, origin, target, basis, signals))
    return min(matches, default=None)


def source_scope(urls, index):
    """An issue may cite a PR in the same project before a revision can be pinned."""
    candidates = set(urls)
    for url in urls:
        canonical = canonical_url(url)
        row = index.rows.get(canonical)
        if row is None or row["kind"] != "issue":
            continue
        repo = urlsplit(canonical).path.rsplit("/", 2)[0]
        tech = row["metadata"].get("technical", {})
        candidates.update(canonical_url(ref) for ref in tech.get("references", [])
                          if urlsplit(canonical_url(ref)).path.startswith(f"{repo}/pull/"))
    return candidates


def advance_office(db, topics, curated, records, now):
    """Reconcile active scopes and propose only one current automatic plan per topic."""
    index = None
    revisions = watched_revisions(db, now) | {canonical_url(row["url"]): source_revision(row)
                                           for row in records if row["kind"] in {"pr", "commit"}}
    # Refresh prerequisites before calculating readiness, including plans whose original subscribers left.
    known = set(curated) | {row["id"] for row in db.execute("SELECT id FROM exchange_topics WHERE decision='accepted'")}
    scoped = set()
    for topic in topics:
        for row in db.execute("SELECT id FROM office_plans WHERE problem_id=? AND phase IN ('draft','active','done')",
                              (topic["problem_id"],)):
            scoped.add(row["id"])
            scoped.update(dep["id"] for dep in dependencies(db, row["id"]))
    notices = 0
    for ident in sorted(scoped):
        plan = read_plan(db, ident)
        if plan["problem_id"] not in known and plan["phase"] in {"draft", "active", "done"}:
            db.execute("UPDATE office_plans SET phase='superseded', source_ready=0 WHERE id=?", (ident,))
            notices += post_notice(db, plan["problem_id"], f"plan:{ident}:retired",
                                   f"Карточка плана №{ident} отозвана. История сохранена.", now)
        else:
            notices += check_sources(db, plan, revisions, now)
            if plan["claimed_by"] and plan["phase"] == "active":
                notices += reassign_revoked(db, read_plan(db, ident), now)
    for topic in topics:
        problem_id = topic["problem_id"]
        urls = [topic["source_url"]] if topic["source_url"] else curated.get(problem_id, [])
        plans = db.execute(PLANS + " WHERE p.problem_id=? ORDER BY p.id DESC", (problem_id,)).fetchall()
        if problem_id not in known:
            continue
        current = False
        for plan in plans:
            if plan["phase"] in {"draft", "active", "done"}:
                current = True
            if plan["phase"] != "active":
                continue
            needs = dependencies(db, plan["id"])
            state = step_for(plan, needs)
            if state == "decision":
                notices += post_notice(db, problem_id, f"plan:{plan['id']}:decision:{plan['result_id']}",
                                       f"Отчёт плана №{plan['id']} одобрен. Обсудите, что можно переиспользовать.", now)
            if state == "ready" and needs:
                notices += post_notice(db, problem_id, f"plan:{plan['id']}:unblocked",
                                       f"Зависимости плана №{plan['id']} выполнены. Проверку можно взять в работу.", now)
        if current or (plans and plans[0]["phase"] == "declined"):
            continue
        if not urls:
            continue
        if index is None:
            index = RelatedIndex(records)
        match = best_comparison(index, source_scope(urls, index))
        if not match:
            continue
        _, origin, target, basis, signals = match
        focus = f" Область сравнения — {', '.join(signals[:3])}." if signals else ""
        objective = "Сверить исходные версии и воспроизвести один проверяемый результат на принимающей стороне." + focus
        ident, created = create_plan(db, problem_id, objective, origin, target, basis, None, now)
        notices += int(created) + check_sources(db, read_plan(db, ident), revisions, now)
    return notices
