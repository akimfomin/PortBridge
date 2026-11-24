"""Private conversations and updates for subscribed exchange participants."""

from hashlib import sha256
import re
import time

from .catalog import PROBLEM_ID
from .exchange_fields import Conflict, MAX_SQL_INTEGER, PermissionDenied, TOKEN, _integer, _source, _text, _timestamp


MAX_WAIT_SECONDS = 15
MAX_SUBSCRIPTIONS = 100
MAX_MESSAGE_CHARS = 1600
MESSAGE_KEY = re.compile(r"[A-Za-z0-9_-]{8,80}")

DISCUSSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS topic_subscriptions (
    principal_id INTEGER NOT NULL REFERENCES principals(id), problem_id TEXT NOT NULL,
    start_after INTEGER NOT NULL, PRIMARY KEY (principal_id, problem_id)
);
CREATE TABLE IF NOT EXISTS discussion_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, problem_id TEXT NOT NULL,
    author_id INTEGER REFERENCES principals(id), client_id TEXT NOT NULL,
    text TEXT NOT NULL, source_url TEXT, reply_to INTEGER REFERENCES discussion_messages(id),
    posted_at INTEGER NOT NULL, UNIQUE(author_id, client_id)
);
CREATE INDEX IF NOT EXISTS discussion_messages_by_topic ON discussion_messages(problem_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS discussion_system_keys ON discussion_messages(problem_id, client_id)
    WHERE author_id IS NULL;
CREATE TABLE IF NOT EXISTS discussion_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, problem_id TEXT NOT NULL,
    message_id INTEGER UNIQUE REFERENCES discussion_messages(id),
    report_event_id INTEGER UNIQUE REFERENCES exchange_events(id),
    CHECK ((message_id IS NULL) <> (report_event_id IS NULL))
);
CREATE INDEX IF NOT EXISTS discussion_updates_by_topic ON discussion_updates(problem_id, id);
CREATE TABLE IF NOT EXISTS discussion_links (
    problem_id TEXT NOT NULL, origin_url TEXT NOT NULL, related_url TEXT NOT NULL,
    revision TEXT NOT NULL, active INTEGER NOT NULL, generation INTEGER NOT NULL,
    PRIMARY KEY (problem_id, origin_url, related_url)
);
CREATE TRIGGER IF NOT EXISTS discussion_message_posted AFTER INSERT ON discussion_messages
BEGIN
    INSERT INTO discussion_updates(problem_id, message_id) VALUES (NEW.problem_id, NEW.id);
END;
CREATE TRIGGER IF NOT EXISTS discussion_report_changed AFTER INSERT ON exchange_events
BEGIN
    INSERT INTO discussion_updates(problem_id, report_event_id)
        SELECT problem_id, NEW.id FROM results WHERE id=NEW.result_id;
END;
"""

MESSAGE_COLUMNS = """m.id, m.problem_id, m.text, m.source_url, m.reply_to, m.posted_at,
    coalesce(a.name, 'PortBridge') AS author,
    CASE WHEN m.author_id IS NULL THEN 'portbridge' ELSE 'participant' END AS author_kind"""
MESSAGES = f"SELECT {MESSAGE_COLUMNS} FROM discussion_messages m LEFT JOIN principals a ON a.id=m.author_id"
MESSAGE_FIELDS = {"problem_id", "client_id", "text"}


def message_data(row):
    return {**dict(row), "posted_at": _timestamp(row["posted_at"])}


def discussion_text(value):
    if not isinstance(value, str) or len(value) > MAX_MESSAGE_CHARS:
        raise ValueError("invalid message length")
    value = value.replace("\r\n", "\n")
    _text(value.replace("\n", " "), "message", MAX_MESSAGE_CHARS)
    return value.strip()


def require_subscription(db, actor, problem):
    if db.execute("SELECT 1 FROM topic_subscriptions WHERE principal_id=? AND problem_id=?",
                  (actor["id"], problem)).fetchone() is None:
        raise PermissionDenied("subscribe to the topic before reading or writing its discussion")


def page(cursor, key, rows):
    return {key: rows, "next_cursor": rows[-1]["id"] if rows else cursor}


def post_notice(db, problem_id, key, text, now, *, source_url=None):
    message_key = sha256(key.encode("utf-8")).hexdigest()
    return db.execute("""INSERT INTO discussion_messages(problem_id, author_id, client_id, text, source_url, posted_at)
        VALUES (?, NULL, ?, ?, ?, ?) ON CONFLICT DO NOTHING""", (problem_id, message_key, text, source_url, now)).rowcount


class DiscussionStore:
    def __init__(self, exchange):
        self.exchange = exchange

    def subscriptions(self, token):
        with self.exchange._connect() as db:
            actor = self.exchange._principal(db, token, "read")
            return [row[0] for row in db.execute(
                "SELECT problem_id FROM topic_subscriptions WHERE principal_id=? ORDER BY problem_id", (actor["id"],)
            )]

    def subscribe(self, token, problem_id, enabled):
        if (type(enabled) is not bool or not isinstance(problem_id, str) or len(problem_id) > 64
                or not PROBLEM_ID.fullmatch(problem_id)):
            raise ValueError("provide a PortBridge topic ID and an enabled flag")
        with self.exchange._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            actor = self.exchange._principal(db, token, "read")
            key = (actor["id"], problem_id)
            if enabled:
                self.exchange._problem(db, problem_id)
                existing = db.execute("SELECT 1 FROM topic_subscriptions WHERE principal_id=? AND problem_id=?", key)
                if existing.fetchone() is None:
                    subscribed = db.execute("SELECT count(*) FROM topic_subscriptions WHERE principal_id=?",
                                            (actor["id"],)).fetchone()[0]
                    if subscribed >= MAX_SUBSCRIPTIONS:
                        raise Conflict("subscription limit reached")
                    db.execute("""INSERT INTO topic_subscriptions
                        SELECT ?, ?, coalesce(max(id), 0) FROM discussion_updates""", key)
            else:
                db.execute("DELETE FROM topic_subscriptions WHERE principal_id=? AND problem_id=?", key)
        return {"problem_id": problem_id, "enabled": enabled}

    def add_message(self, token, payload):
        if (not isinstance(payload, dict) or not MESSAGE_FIELDS <= payload.keys()
                or payload.keys() - MESSAGE_FIELDS - {"source_url", "reply_to"}):
            raise ValueError("expected a topic ID, client message ID, text and optional source or reply")
        client_id = payload["client_id"]
        if not isinstance(client_id, str) or not MESSAGE_KEY.fullmatch(client_id) or TOKEN.search(client_id):
            raise ValueError("client_id must be an opaque message key")
        text = discussion_text(payload["text"])
        source = _source(payload["source_url"]) if "source_url" in payload else None
        reply = _integer(payload["reply_to"], "reply_to", 1, MAX_SQL_INTEGER) if "reply_to" in payload else None
        with self.exchange._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            actor = self.exchange._principal(db, token, "contribute")
            if "read" not in actor["scopes"]:
                raise PermissionDenied("read scope required for discussions")
            problem = self.exchange._problem(db, payload["problem_id"])
            require_subscription(db, actor, problem)
            existing = db.execute(MESSAGES + " WHERE m.author_id=? AND m.client_id=?",
                                  (actor["id"], client_id)).fetchone()
            if existing:
                if (existing["problem_id"], existing["text"], existing["source_url"], existing["reply_to"]) != (
                        problem, text, source, reply):
                    raise Conflict("client_id already used with different message content")
                return message_data(existing)
            if reply is not None and db.execute(
                    "SELECT 1 FROM discussion_messages WHERE id=? AND problem_id=?", (reply, problem)
            ).fetchone() is None:
                raise LookupError("reply target is absent from this discussion")
            ident = db.execute("""INSERT INTO discussion_messages
                (problem_id, author_id, client_id, text, source_url, reply_to, posted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", (problem, actor["id"], client_id, text, source, reply,
                                                  int(time.time()))).lastrowid
            return message_data(db.execute(MESSAGES + " WHERE m.id=?", (ident,)).fetchone())

    def thread(self, token, problem_id, *, after=0, limit=50):
        after = _integer(after, "after", 0, MAX_SQL_INTEGER)
        limit = _integer(limit, "limit", 1, 100)
        with self.exchange._connect() as db:
            db.execute("BEGIN")
            actor = self.exchange._principal(db, token, "read")
            require_subscription(db, actor, problem_id)
            rows = db.execute(MESSAGES + " WHERE m.problem_id=? AND m.id>? ORDER BY m.id LIMIT ?",
                              (problem_id, after, limit))
            return page(after, "messages", [message_data(row) for row in rows])

    def coordination_links(self, token, problem_id):
        with self.exchange._connect() as db:
            db.execute("BEGIN")
            actor = self.exchange._principal(db, token, "read")
            require_subscription(db, actor, problem_id)
            rows = db.execute("""SELECT origin_url, related_url, revision, active FROM discussion_links
                WHERE problem_id=? AND active=1 ORDER BY origin_url, related_url""", (problem_id,))
            return [{key: row[key] for key in ("origin_url", "related_url", "revision")} for row in rows]

    def updates(self, token, *, after=0, limit=50, wait_seconds=0):
        after = _integer(after, "after", 0, MAX_SQL_INTEGER)
        limit = _integer(limit, "limit", 1, 100)
        wait_seconds = _integer(wait_seconds, "wait_seconds", 0, MAX_WAIT_SECONDS)
        deadline = time.monotonic() + wait_seconds
        while True:
            events = self._updates(token, after, limit)
            remaining = deadline - time.monotonic()
            if events or remaining <= 0:
                return page(after, "events", events)
            # Release the database between checks so other clients can post or revoke a key.
            time.sleep(min(0.25, remaining))

    def _updates(self, token, after, limit):
        with self.exchange._connect() as db:
            db.execute("BEGIN")
            actor = self.exchange._principal(db, token, "read")
            rows = db.execute(f"""SELECT u.id AS cursor, u.problem_id AS topic,
                   {MESSAGE_COLUMNS}, e.kind AS report_kind, e.result_id
                FROM topic_subscriptions s
                JOIN discussion_updates u ON u.problem_id=s.problem_id AND u.id>s.start_after AND u.id>?
                LEFT JOIN discussion_messages m ON m.id=u.message_id
                LEFT JOIN principals a ON a.id=m.author_id
                LEFT JOIN exchange_events e ON e.id=u.report_event_id
                WHERE s.principal_id=? ORDER BY u.id LIMIT ?""", (after, actor["id"], limit))
            events = []
            for row in rows:
                event = {"id": row["cursor"], "problem_id": row["topic"]}
                if row["report_kind"]:
                    event.update(kind=row["report_kind"], result_id=row["result_id"])
                else:
                    fields = ("id", "problem_id", "text", "source_url", "reply_to", "posted_at", "author", "author_kind")
                    event.update(kind="message", message=message_data({field: row[field] for field in fields}))
                events.append(event)
            return events
