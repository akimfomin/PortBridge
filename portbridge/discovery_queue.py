"""Persist bounded Discovery work across independent scheduler invocations."""

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


def ready(db, now):
    # Oldest runnable work wins. Priority breaks ties within an intake cohort.
    # An origin with unchanged terms can reuse a different origin's cached reply.
    return db.execute("""
        SELECT job.url,job.revision,job.query
        """ + JOIN + " WHERE " + DUE + """
        ORDER BY CASE WHEN result.url IS NULL THEN job.queued ELSE coalesce(cache.retry_at, job.queued) END,
                 job.priority DESC, job.url
        LIMIT ?
    """, (now, LOCAL_BATCH)).fetchall()


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
