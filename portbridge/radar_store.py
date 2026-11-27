"""Durable Radar and Lab records, with explicit public projections."""

from datetime import datetime, timezone
import json
import re

from .discovery_queue import RESULT_TTL
from .identity import stable_id

SCHEMA = """
CREATE TABLE IF NOT EXISTS radar_seen (
    url TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, checked INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS radar_candidates (
    id TEXT PRIMARY KEY, origin TEXT NOT NULL, peer TEXT NOT NULL, generation TEXT NOT NULL,
    state TEXT NOT NULL, payload TEXT NOT NULL, updated INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS radar_origins ON radar_candidates(origin, peer);
CREATE INDEX IF NOT EXISTS radar_peers ON radar_candidates(peer);
CREATE TABLE IF NOT EXISTS radar_tasks (
    id TEXT PRIMARY KEY, candidate TEXT NOT NULL REFERENCES radar_candidates(id), generation TEXT NOT NULL,
    state TEXT NOT NULL, round INTEGER NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS radar_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL REFERENCES radar_tasks(id), generation TEXT NOT NULL, round INTEGER NOT NULL,
    actor TEXT NOT NULL, opened INTEGER NOT NULL, expires INTEGER NOT NULL, ended INTEGER, reason TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS radar_one_claim ON radar_claims(task, generation, round) WHERE ended IS NULL;
CREATE TABLE IF NOT EXISTS radar_reports (
    id TEXT PRIMARY KEY, task TEXT NOT NULL REFERENCES radar_tasks(id), generation TEXT NOT NULL,
    round INTEGER NOT NULL, actor TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL,
    submitted INTEGER NOT NULL, reviewer TEXT, reviewed INTEGER, note TEXT
);
CREATE INDEX IF NOT EXISTS radar_reports_task ON radar_reports(task, generation, round);
CREATE TABLE IF NOT EXISTS radar_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, task TEXT, candidate TEXT,
    actor TEXT NOT NULL, action TEXT NOT NULL, recorded INTEGER NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS radar_patch_cache (
    revision TEXT PRIMARY KEY, digest TEXT, checked INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS radar_preferences (
    actor TEXT PRIMARY KEY, payload TEXT NOT NULL
);
"""
CONFIDENCE = ("high", "review", "research")
STATES = ("candidate", "queued", "claimed", "investigated", "tested", "rejected", "delivered",
          "adopted", "stale", "withdrawn")
TASK_TYPES = ("source-only", "hardware", "reproduction", "patch", "radar", "performance",
              "negative", "port", "documentation")
SOURCE_TTL = 6 * 3600
DIGEST_LIMIT = 24
KEY = re.compile(r"^[a-z0-9-]{1,80}$")


def encode(data):
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def timestamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def epoch(value):
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        return int(parsed.timestamp()) if parsed.tzinfo else 0
    except (TypeError, ValueError, AttributeError):
        return 0


def present(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='radar_candidates'").fetchone() is not None


def event(db, *, actor, action, now, task=None, candidate=None, details=None, request=None):
    payload = details or {}
    identifier = stable_id("radar-event", actor, action, task, candidate,
                           request if request else (now, encode(payload)))
    db.execute("""INSERT OR IGNORE INTO radar_events(id, task, candidate, actor, action, recorded, payload)
                  VALUES(?,?,?,?,?,?,?)""", (identifier, task, candidate, actor, action, now, encode(payload)))
    return identifier


def phase(db, task, status, now):
    db.execute("UPDATE radar_tasks SET state=? WHERE id=?", (status, task["id"]))
    db.execute("UPDATE radar_candidates SET state=?,updated=? WHERE id=?", (status, now, task["candidate"]))


def recent(candidate, now):
    tracked = [x for x in candidate["sources"] if x["role"] != "historical"]
    if not tracked or any(not x.get("fresh") or epoch(x.get("checked_at")) < now - SOURCE_TTL for x in tracked):
        return False
    # Pinned historical revisions are immutable. A search result without a pin can age out.
    return all(epoch(x.get("checked_at")) > now - RESULT_TTL for x in candidate["sources"]
               if x["role"] == "historical" and not x.get("revision"))


def report_count(db, task):
    rows = db.execute("SELECT state,count(*) FROM radar_reports WHERE task=? AND generation=? GROUP BY state",
                      (task["id"], task["generation"]))
    return dict(rows)


def active_claim(db, task, now):
    return db.execute("""SELECT * FROM radar_claims WHERE task=? AND generation=? AND round=?
                      AND ended IS NULL AND expires>?""",
                      (task["id"], task["generation"], task["round"], now)).fetchone()


def public_task_rows(db, now):
    candidates = db.execute("""SELECT t.*,c.payload AS candidate_payload
        FROM radar_tasks AS t JOIN radar_candidates AS c ON t.candidate=c.id
        WHERE t.state NOT IN ('withdrawn') ORDER BY t.id LIMIT 240""").fetchall()
    for task in candidates:
        card, record = json.loads(task["payload"]), json.loads(task["candidate_payload"])
        state = task["state"]
        if state == "claimed" and not active_claim(db, task, now):
            state = "queued"
        if state in {"draft", "queued", "claimed", "investigated"} and not recent(record, now):
            state = "stale"
        yield {**card, "workflow_state": state, "round": task["round"], "age_state": "fresh" if recent(record, now) else "stale",
               "status": {"draft": "awaiting_review", "queued": "needs_run", "claimed": "needs_run",
                          "investigated": "awaiting_review", "stale": "needs_revision"}.get(state, "blocked"),
               "report_counts": report_count(db, task)}


def public_tasks(catalog, now):
    with catalog.connect() as db:
        return list(public_task_rows(db, now)) if present(db) else []


def radar_view(catalog, now, *, include_catalog=False, **filters):
    with catalog.connect() as db:
        if not present(db):
            return filter_radar({"candidates": [], "external_delivery": False}, **filters)
        rows = db.execute("""SELECT c.id,c.state,c.payload,c.updated,t.id AS task_id,t.generation AS task_generation,
                    c.generation, EXISTS(SELECT 1 FROM radar_claims claim WHERE claim.task=t.id AND
                    claim.generation=t.generation AND claim.round=t.round AND claim.ended IS NULL AND claim.expires>?)
                    AS live_claim
            FROM radar_candidates c LEFT JOIN radar_tasks t ON t.candidate=c.id
            WHERE c.state != 'withdrawn' ORDER BY c.updated DESC,c.id LIMIT 360""", (now,)).fetchall()
    result = []
    for row in rows:
        card = json.loads(row["payload"])
        status = "queued" if row["state"]=="claimed" and not row["live_claim"] else row["state"]
        if status in {"candidate", "queued", "claimed", "investigated"} and not recent(card, now):
            status = "stale"
        result.append({**card, "state": status, "age_state": "fresh" if recent(card, now) else "stale",
                       "task_id": row["task_id"] if row["generation"] == row["task_generation"] else None,
                       "updated_at": timestamp(row["updated"])})
    ranks = {value: pos for pos, value in enumerate(CONFIDENCE)}
    result.sort(key=lambda card: (card["state"] == "stale", ranks[card["confidence"]], -epoch(card["updated_at"]), card["id"]))
    payload = {"candidates": result, "external_delivery": False, "checked_at": timestamp(now)}
    processed = filter_radar(payload, **filters)
    return {**processed, "catalog": result} if include_catalog else processed


def filter_radar(payload, *, confidence="", state="", console="", limit=DIGEST_LIMIT, after=0, muted=False):
    if (confidence and confidence not in CONFIDENCE or state and state not in STATES or
            type(limit) is not int or not 1 <= limit <= DIGEST_LIMIT or type(after) is not int or after < 0):
        raise ValueError("Invalid Radar confidence, state, limit or cursor")
    result = [card for card in payload.get("catalog", payload["candidates"]) if not muted
              and (not confidence or confidence == card["confidence"]) and (not state or state == card["state"])
              and (not console or console in card.get("consoles", ())) ]
    return {"candidates": result[after:after+limit], "next": after+limit if len(result)>after+limit else None,
            "total": len(result), "external_delivery": False, "checked_at": payload.get("checked_at")}



def reviewed_snapshot(catalog, *, lab=None):
    from .identity import lab_report_id
    from .lab import TASKS
    from .lab_reports import conflicting_public_reports, independent_owner_review, read_report_states
    from .matching import canonical_url

    with catalog.connect() as db:
        rows = db.execute("""SELECT c.origin,c.peer,c.payload,c.state AS candidate_state,r.id,r.state,r.payload AS report,r.reviewed
            FROM radar_candidates c JOIN radar_tasks t ON t.candidate=c.id
            JOIN radar_reports r ON r.task=t.id AND r.generation=c.generation
            WHERE r.state IN ('reviewed','reproduced') AND c.state NOT IN ('stale','withdrawn')
            AND json_extract(r.payload,'$.share_public')=1
            ORDER BY r.reviewed DESC,r.id LIMIT 100""").fetchall() if present(db) else []
    finds = []
    for row in rows:
        report = json.loads(row["report"])
        candidate = json.loads(row["payload"])
        finds.append({"origin": row["origin"], "peer": row["peer"], "id": row["id"], "status": row["state"],
                      "contested": row["candidate_state"] == "investigated" and report["outcome"] in {"PASS", "FAIL"},
                      "reviewed_at": timestamp(row["reviewed"]) if row["reviewed"] else None,
                      "title": candidate["sources"][0]["title"], "consoles": candidate.get("consoles", []),
                      "target_url": candidate["sources"][0]["url"], "peer_url": candidate["sources"][1]["url"],
                      **{key: report[key] for key in ("source_url", "revisions", "outcome", "observed", "limitations")}})
    if lab is None:
        states = read_report_states(catalog, TASKS)
        tasks = ({**task, "report_sync": states.get(task["id"], {})} for task in TASKS)
    else:
        tasks = lab["tasks"]
    for task in tasks:
        sync = task.get("report_sync", {})
        reports = sync.get("reports", [])
        disputed = conflicting_public_reports(reports)
        for report in reports:
            review = independent_owner_review(report)
            if not review or report.get("outcome") not in {"pass", "fail"}:
                continue
            url = report["url"]
            target, thread = task["source_url"], url.split("#")[0]
            finds.append({"id": lab_report_id(url), "status": "reviewed", "contested": url in disputed,
                          "reviewed_at": review["reported_at"], "title": task["title"],
                          "consoles": task.get("consoles", ["xbox-series"]),
                          "origin": canonical_url(target), "peer": canonical_url(thread),
                          "target_url": target, "peer_url": thread, "source_url": url,
                          "review_url": review["url"], "revisions": report["revisions"],
                          "outcome": report["outcome"].upper(),
                          "observed": report["hardware"] + " test reported " + report["outcome"].upper(),
                          "source_state": sync.get("state"), "checked_at": sync.get("checked_at"),
                          "limitations": "Owner-reviewed public report for the listed hardware and revisions."
                              + (" Source refresh pending." if sync.get("state") != "fresh" else "")})
    return sorted(finds, key=lambda row: (row["reviewed_at"] or "", row["id"]), reverse=True)


def filter_findings(rows, *, url="", query="", limit=5):
    from .matching import canonical_url

    normalized = canonical_url(url) if url else None
    q = query.strip().casefold()
    return [item for item in rows if ((normalized and normalized in (item["origin"], item["peer"]))
             or (not normalized and q and q in item["title"].casefold()))][:limit]


def public_outcome_receipts(catalog):
    """Expose checked receiving-project events for current, shared Lab evidence."""
    with catalog.connect() as db:
        if not present(db):
            return []
        rows = db.execute("""
            SELECT e.action,e.recorded,e.payload,t.id AS task,c.payload AS candidate
            FROM radar_events e JOIN radar_tasks t ON e.task=t.id
            JOIN radar_candidates c ON c.id=t.candidate AND c.generation=t.generation
            WHERE e.action IN ('deliver','adopt') AND t.state IN ('delivered','adopted')
              AND EXISTS (SELECT 1 FROM radar_reports r WHERE r.task=t.id AND r.generation=t.generation
                          AND r.state IN ('reviewed','reproduced') AND r.reviewed<=e.recorded
                          AND json_extract(r.payload,'$.share_public')=1)
              AND NOT EXISTS (SELECT 1 FROM radar_events change WHERE change.candidate=c.id
                              AND change.action='revision_changed' AND change.seq>e.seq)
            ORDER BY e.seq
        """).fetchall()
    return [{"step": row["action"], "at": timestamp(row["recorded"]), "task": row["task"],
             "proof": json.loads(row["payload"])["result"]["evidence_url"],
             "candidate": json.loads(row["candidate"])} for row in rows]
