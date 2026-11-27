"""Compare old and new policy on the same scheduled public checkpoint."""

import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from time import perf_counter

from portbridge import discovery_queue as queue
from portbridge.catalog import ReadOnlyCatalog
from portbridge.discovery_scan import PRIORITY_PROJECTS, lookup_plan, project_priority, query_for, source_repo

PATH=Path(".portbridge/deep-scheduled-catalog.sqlite3")
CAPTURED=int(datetime.fromisoformat("2026-11-27T09:10:22+00:00").timestamp())
START=CAPTURED+1800
INTERVAL=1800
LOOKUPS=5
ROUNDS=16
OLD_PRIORITIES=PRIORITY_PROJECTS-{
    "edsuuu/vi-br-port","belobug/victory-belobug-amd","dathinel/victory-4gb","r0y00/xbox2windows"
}


def old_ready(db, now):
    return db.execute(f"""
        SELECT job.url,job.revision,job.query
        {queue.JOIN}
        WHERE {queue.DUE}
        ORDER BY {queue.READY_SINCE},job.priority DESC,job.url
        LIMIT ?
    """, (now,queue.LOCAL_BATCH)).fetchall()


def replay(src, facts, resolver):
    db=sqlite3.connect(":memory:")
    src.backup(db)
    db.row_factory=sqlite3.Row
    now=START
    results=[]
    baseline=resolver is old_ready
    expected=set()
    newest=[]
    for i in range(ROUNDS):
        jobs={url:(revision,query,int(source_repo(url) in OLD_PRIORITIES) if baseline
                                else project_priority(url,updated,now))
              for url,(revision,query,updated) in facts.items()}
        queue.schedule(db,jobs,now)
        if not i:
            before=queue.metrics(db,now)
            recent_rows=[row for row in db.execute(f"""
                SELECT job.url, job.query {queue.JOIN}
                WHERE {queue.DUE} AND coalesce(cache.retry_at,0)<=?
                """,(now,now)) if project_priority(row["url"], facts[row["url"]][2], now)>=queue.FRESH_PRIORITY]
            newest=list(dict.fromkeys(row["query"] for row in sorted(
                recent_rows, key=lambda row: (-project_priority(row["url"],facts[row["url"]][2],now),row["url"]))))[:20]
            expected={row["query"] for row in recent_rows}
        started=perf_counter()
        rows=resolver(db,now) if baseline else resolver(db,now,LOOKUPS)
        planning_ms=(perf_counter()-started)*1e3
        searched=[]
        completed=0
        for url,revision,query in rows:
            prior=db.execute("SELECT retry_at FROM discovery_query WHERE query=?",(query,)).fetchone()
            if not prior or prior[0]<=now:
                if len(searched)>=LOOKUPS:
                    break
                db.execute("REPLACE INTO discovery_query VALUES (?,?,?,?,?)",
                           (query,now,now+queue.RESULT_TTL,"available","[]"))
                searched.append(query)
            db.execute("REPLACE INTO discovery_observation VALUES (?,?,?,?)",(url,revision,query,now))
            completed+=1
        after=queue.metrics(db,now)
        results.append({"at":datetime.fromtimestamp(now,timezone.utc).isoformat(),
                        "remote_queries":len(searched),"fresh_leader_queries":len(set(searched)&expected),
                        "origins_processed":completed,"oldest_remote_ready_seconds":after["oldest_remote_ready_seconds"],
                        "planning_ms":round(planning_ms,2),"topics":searched})
        now+=INTERVAL
    first_seen={query:i+1 for i in reversed(range(len(results))) for query in results[i]["topics"]}
    return {"newest_20_first_batch":[first_seen.get(query) for query in newest],
            "newest_20_topics":newest,"expected_fresh_leading_remote_topics":len(expected), "before":before,"batches":results,
            "fresh_leader_queries":sum(x["fresh_leader_queries"] for x in results),
            "origins_processed":sum(x["origins_processed"] for x in results)}


def main():
    catalog=ReadOnlyCatalog(PATH)
    observations=catalog.observations(limit=None)
    known={row["repo"].lower() for row in catalog.projects()}
    updates={row["url"].lower():row.get("updated_at") for row in observations}
    plan=lookup_plan(observations,known,scheduled=True)
    facts={url:(revision,query_for(url,term),updates.get(url)) for url,(revision,term) in plan.items()}
    with catalog.connect() as db:
        captured=queue.metrics(db,CAPTURED)
        actual_jobs=queue.counts(db,CAPTURED)
        old=replay(db,facts,old_ready)
        new=replay(db,facts,queue.ready)
    print(json.dumps({"checkpoint":"45970589550 / artifact 15184528001","observations":len(observations),
                      "captured":captured,"actual_jobs":actual_jobs,"old":old,"new":new},indent=2))


if __name__=="__main__":
    main()
