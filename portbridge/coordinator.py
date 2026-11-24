"""Maintain verified links and post local coordination notices for joined teams."""

from collections import defaultdict
import time
from urllib.parse import urlsplit

from . import PROJECT_LINK
from .discussion import post_notice
from .matching import canonical_url, source_revision


MAX_LINKS_PER_TOPIC = 3
COORDINATION_INTERVAL = 5


def outreach_drafts(links):
    drafts = []
    for link in links:
        origin, related, revision = (link[key] for key in ("origin_url", "related_url", "revision"))
        if "/pull/" not in origin and "/issues/" not in origin:
            continue
        drafts.append({
            "target_url": origin,
            "source_url": related,
            "message": (f"{PROJECT_LINK} found the same published revision ({revision}) at {related}. "
                        "Has anyone checked whether the result applies "
                        "to this project's current build and configuration?"),
        })
    return drafts


def same_revision_links(origins, sources, revisions):
    pairs = set()
    links = {}
    for origin in sorted(origins):
        if origin not in sources:
            continue
        row = sources[origin]
        revision = source_revision(row)
        if not revision:
            continue
        for other in revisions[revision]:
            pair = tuple(sorted((origin, other)))
            if pair in pairs or sources[other]["project"] == row["project"]:
                continue
            pairs.add(pair)
            links[origin, other] = revision
            if len(links) == MAX_LINKS_PER_TOPIC:
                return links
    return links


def update_links(db, problem_id, desired, now):
    rows = db.execute("SELECT * FROM discussion_links WHERE problem_id=?", (problem_id,))
    previous = {(row["origin_url"], row["related_url"]): row for row in rows}
    notices = 0
    for origin, related in sorted(desired.keys() | previous.keys()):
        last = previous.get((origin, related))
        revision = desired.get((origin, related))
        if last and bool(last["active"]) == bool(revision) and (not revision or last["revision"] == revision):
            continue
        generation = last["generation"] + 1 if last else 1
        stored_revision = revision if revision else last["revision"]
        db.execute("""INSERT INTO discussion_links VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(problem_id, origin_url, related_url) DO UPDATE SET revision=excluded.revision,
            active=excluded.active, generation=excluded.generation""",
                   (problem_id, origin, related, stored_revision, bool(revision), generation))
        text = (f"Оба источника сейчас указывают на одну ревизию {revision}. "
                "Результат нужно проверить в сборке своей команды." if revision else
                f"Совпадение по ревизии {stored_revision} больше не подтверждается текущими данными. "
                "Ссылка остаётся в истории обсуждения.")
        notices += post_notice(db, problem_id, f"link:{origin}:{related}:{generation}", text, now, source_url=related)
    return notices


def run_coordination(catalog, exchange, *, office=False):
    """Run one pass on stored data. Machine notices are committed with their updated state."""
    with exchange._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        topics = db.execute("""SELECT DISTINCT s.problem_id, t.source_url
            FROM topic_subscriptions s
            LEFT JOIN exchange_topics t ON t.id=s.problem_id AND t.decision='accepted'
            LEFT JOIN revoked_principals r ON r.principal_id=s.principal_id
            WHERE r.principal_id IS NULL ORDER BY s.problem_id""").fetchall()
        if not topics:
            return 0
        curated = {card["id"]: [ref["url"] for solution in card["solutions"] for ref in solution["source_refs"]
                                 if not urlsplit(ref["url"]).fragment] for card in catalog.problems()}
        sources, revisions = {}, defaultdict(list)
        records = catalog.observations(limit=None)
        for row in records:
            if row["kind"] not in {"pr", "commit"}:
                continue
            source = canonical_url(row["url"])
            sources[source] = row
            if revision := source_revision(row):
                revisions[revision].append(source)
        for urls in revisions.values():
            urls.sort()
        now = int(time.time())
        notices = 0
        active_work = defaultdict(list)
        for row in db.execute("""SELECT w.problem_id, w.id FROM work w
            LEFT JOIN revoked_principals r ON r.principal_id=w.actor_id
            WHERE w.expires_at>? AND r.principal_id IS NULL ORDER BY w.id""", (now,)):
            active_work[row["problem_id"]].append(row["id"])
        for topic in topics:
            ident = topic["problem_id"]
            urls = [topic["source_url"]] if topic["source_url"] else curated.get(ident, [])
            links = same_revision_links({canonical_url(url) for url in urls}, sources, revisions)
            notices += update_links(db, ident, links, now)
            registrations = active_work[ident]
            if urls and len(registrations) > 1:
                scope = ",".join(map(str, registrations))
                text = (f"По этой задаче отметились {len(registrations)} участников. "
                        "Сверьте проверки в обсуждении, чтобы распределить работу.")
                notices += post_notice(db, ident, f"work:{scope}", text, now)
        if office:
            from .office_engine import advance_office

            notices += advance_office(db, topics, curated, records, now)
        return notices
