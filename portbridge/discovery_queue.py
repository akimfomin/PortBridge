"""Persist bounded Discovery work across independent scheduler invocations."""

from itertools import islice

SCHEMA = """
CREATE TABLE IF NOT EXISTS discovery_jobs (
    url TEXT PRIMARY KEY,
    revision TEXT,
    query TEXT NOT NULL,
    queued REAL NOT NULL,
    priority INTEGER NOT NULL
);
"""

JOIN = """
FROM discovery_jobs AS job
LEFT JOIN discovery_observation AS result
    ON result.url=job.url AND result.revision IS job.revision AND result.query=job.query
LEFT JOIN discovery_query AS cache ON cache.query=job.query
"""
DUE = "(result.url IS NULL OR cache.retry_at IS NULL OR cache.retry_at<=?)"
READY_SINCE = "CASE WHEN result.url IS NULL THEN job.queued ELSE coalesce(cache.retry_at, job.queued) END"
FRESH_PRIORITY = 2
LOCAL_BATCH = 120
RESULT_TTL = 24 * 3600


def schedule(db, jobs, now):
    """Reconcile the tracked snapshot under the search lease, retaining first queued time."""
    with db:
        db.execute("CREATE TEMP TABLE IF NOT EXISTS active_discovery_jobs (url TEXT PRIMARY KEY)")
        db.execute("DELETE FROM active_discovery_jobs")
        db.executemany("INSERT INTO active_discovery_jobs VALUES (?)", ((url,) for url in jobs))
        db.execute("DELETE FROM discovery_jobs WHERE url NOT IN (SELECT url FROM active_discovery_jobs)")
        db.executemany("""
            INSERT INTO discovery_jobs VALUES (?,?,?,?,?)
            ON CONFLICT(url) DO UPDATE SET
                revision=excluded.revision, query=excluded.query, priority=excluded.priority,
                queued=CASE WHEN discovery_jobs.revision IS excluded.revision
                            AND discovery_jobs.query=excluded.query THEN discovery_jobs.queued ELSE excluded.queued END
            WHERE discovery_jobs.revision IS NOT excluded.revision OR discovery_jobs.query!=excluded.query
                OR discovery_jobs.priority!=excluded.priority
        """, ((url, revision, query, now, priority) for url, (revision, query, priority) in jobs.items()))


def ready(db, now, max_lookups):
    """Reserve one remote topic for the oldest work and use spare slots for fresh work."""
    rows = db.execute(f"""
        SELECT job.url,job.revision,job.query,job.priority,{READY_SINCE} AS ready_since,
               coalesce(cache.retry_at,0)>? AS cached
        {JOIN} WHERE {DUE}
        ORDER BY ready_since,job.priority DESC,job.url
    """, (now, now)).fetchall()
    oldest, fresh, cached = {}, {}, []
    for row in rows:
        query = row["query"]
        if row["cached"]:
            cached.append(row)
            continue
        oldest.setdefault(query, row)
        if row["priority"] >= FRESH_PRIORITY:
            if query not in fresh or row["priority"] > fresh[query]["priority"]:
                fresh[query] = row
    topics = dict(islice(oldest.items(), 1))
    for row in sorted(fresh.values(), key=lambda row: (-row["priority"], row["ready_since"], row["url"])):
        topics.setdefault(row["query"], row)
    for query, row in oldest.items():
        topics.setdefault(query, row)
    anchors = list(islice(topics.values(), max_lookups))
    chosen_queries = {row["query"] for row in anchors}
    chosen_urls = {row["url"] for row in anchors}
    cached = cached[:LOCAL_BATCH - len(anchors)]
    remaining = LOCAL_BATCH - len(anchors) - len(cached)
    shared = (row for row in rows if row["query"] in chosen_queries and row["url"] not in chosen_urls)
    return [row[:3] for row in (*cached, *anchors, *islice(shared, remaining))]


def metrics(db, now):
    row = db.execute(f"""
        WITH ready_jobs AS (
            SELECT job.query,job.priority,{READY_SINCE} AS ready_since,
                   coalesce(cache.retry_at,0)>? AS cached
            {JOIN} WHERE {DUE}
        )
        SELECT count(*) AS ready_origins,
               count(DISTINCT query) AS ready_topics,
               count(DISTINCT CASE WHEN NOT cached THEN query END) AS remote_topics,
               count(CASE WHEN cached THEN 1 END) AS cache_ready_origins,
               count(CASE WHEN priority>=? THEN 1 END) AS fresh_leading_origins,
               count(DISTINCT CASE WHEN priority>=? AND NOT cached THEN query END) AS fresh_leading_remote_topics,
               min(ready_since) AS oldest,
               min(CASE WHEN NOT cached THEN ready_since END) AS oldest_remote
        FROM ready_jobs
    """, (now, now, FRESH_PRIORITY, FRESH_PRIORITY)).fetchone()
    result = dict(row)
    for name in ("oldest", "oldest_remote"):
        since = result.pop(name)
        result[name + "_ready_seconds"] = max(0, int(now - since)) if since is not None else None
    return result


def fresh_results(db, now):
    """Let Radar discover changed search output even after the originating batch has finished."""
    return db.execute("""
        SELECT result.url,result.revision,cache.items,cache.retrieved
        FROM discovery_observation AS result JOIN discovery_query AS cache USING (query)
        WHERE cache.status IN ('available','partial') AND cache.retrieved>?
            AND cache.items!='[]'
    """, (now,)).fetchall()


def counts(db, now):
    row = db.execute("""
        SELECT count(*) AS jobs, count(CASE WHEN """ + DUE + """ THEN 1 END) AS ready,
               count(CASE WHEN result.url IS NULL OR coalesce(cache.status,'')!='available' OR cache.retry_at<=?
                          THEN 1 END) AS pending
        """ + JOIN, (now, now)).fetchone()
    return dict(row)
