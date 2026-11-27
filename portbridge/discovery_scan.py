"""Run a bounded public Discovery search for recent catalog observations."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from .catalog import Catalog, public_url
from .community_sources import DATA, SCHEMA as PEOPLE_SCHEMA, actor, remember_discovery
from .consoles import console_families
from .discovery_search import SOURCE_FOUND, discover, discovery_index, key
from . import discovery_queue
from .discovery_terms import MAX_CUES, cues, stored_cue
from .github import (API, INSTRUCTION_LIMIT, PR_URL, SIGNATURE_LIMIT, TECHNICAL_TERM, URL, Unavailable,
                     _Sync, _text, _timestamp, refresh_references)
from .global_search import result_entry, RESULT_PATH
from .matching import current_repository, source_revision, source_url_aliases, subject_kind

PUBLIC_ORIGINS = 64
PRIORITY_PROJECTS = frozenset({
    "xcl-dev/xcl", "fxceless/victory-fork", "ubiquitarianism/leonida", "loopersalty/anyxboxx",
    "taynangt/vice-tay", "marvisak/victory", "kytyps5/kytyps5", "boykopovar/anyps5",
    "edsuuu/vi-br-port", "belobug/victory-belobug-amd", "dathinel/victory-4gb", "r0y00/xbox2windows",
})
FRESH_WINDOW = 24 * 3600
MAX_LOOKUPS = 5
PAGE_SIZE = 5
FETCH_SIZE = 15
TTL = discovery_queue.RESULT_TTL
FAILURE_TTL = 15 * 60
BATCH_SECONDS = 14
QUERY_VERSION = "m21-v2"
BROAD_FAILURE = re.compile(
    r"(?:0x[0-9a-f]+|dxgi_error_device_(?:hung|removed|reset)|vk_error_device_lost|device loss|status_access_violation)"
)

EXTERNAL = (
    "doitsujin/dxvk", "HansKristian-Work/vkd3d-proton", "KhronosGroup/Vulkan-ValidationLayers",
    "KhronosGroup/Vulkan-Docs", "KhronosGroup/SPIRV-Tools", "shadps4-emu/shadPS4",
    "xenia-project/xenia", "RPCS3/rpcs3", "microsoft/DirectXShaderCompiler",
    "GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator", "GPUOpen-LibrariesAndSDKs/D3D12MemoryAllocator",
    "llvm/llvm-project", "wine-mirror/wine", "gfx-rs/wgpu", "KhronosGroup/MoltenVK",
)
PS5_PEERS = ("boykopovar/AnyPS5", "KytyPS5/KytyPS5")
XBOX_PEERS = ("xcl-dev/xcl", "ubiquitarianism/leonida")
EXTERNAL_NAMES = {repo.lower() for repo in (*EXTERNAL, *PS5_PEERS, *XBOX_PEERS)}
SCHEMA = """
CREATE TABLE IF NOT EXISTS discovery_observation (
    url TEXT PRIMARY KEY, revision TEXT, query TEXT NOT NULL, seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery_query (
    query TEXT PRIMARY KEY, retrieved REAL NOT NULL, retry_at REAL NOT NULL, status TEXT NOT NULL, items TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery_lease (
    id INTEGER PRIMARY KEY, lease TEXT, expires REAL NOT NULL
);
"""


def subject(observation):
    title = URL.sub(" ", _text(observation["title"]))
    metadata = observation.get("metadata", {}).get("technical") or {}
    options = cues(title)
    # Old observations have a case-folded signals list and no discovery_cues.
    # The full bounded list can include 48 instructions before the API signals.
    for name, limit in (("discovery_cues", MAX_CUES), ("signals", INSTRUCTION_LIMIT + SIGNATURE_LIMIT)):
        values = metadata.get(name)
        if isinstance(values, list):
            options.extend(term.casefold() for term in values[:limit] if stored_cue(term))
    concrete = next((term for term in options if not BROAD_FAILURE.fullmatch(term)), "")
    if concrete:
        return concrete
    # Short fixed conjunctions match signs of the mechanism even when the title's
    # prose differs from documentation or an older tracker.
    tokens = set(re.findall(r"[a-z0-9]+", title.casefold()))
    for words in (("dxgi", "budget"), ("adapter", "performance"), ("compute", "subobject")):
        if set(words) <= tokens:
            return " ".join(words)
    if "budget" in tokens and ({"eviction", "evict", "clamping", "vram"} & tokens):
        return "memory budget"
    if {"sparse", "tiles"} <= tokens:
        return "sparse binding"
    # Multi-word mechanisms already retained by the GitHub normalizer can be
    # recovered from old rows without guessing a term from free-form prose.
    terms = metadata.get("terms")
    if isinstance(terms, list):
        concrete = next((term.casefold() for term in terms[:SIGNATURE_LIMIT] if isinstance(term, str)
                         and " " in term and TECHNICAL_TERM.fullmatch(term)
                         and not BROAD_FAILURE.fullmatch(term.casefold())), "")
        if concrete:
            return concrete
    return options[0] if options else ""


def source_repo(url):
    return "/".join(urlsplit(url).path.lower().split("/")[1:3])


def source_results(rows):
    seen = set()
    for raw in rows[:FETCH_SIZE]:
        row = result_entry(raw)
        if not row or (repo := source_repo(row["url"])) not in EXTERNAL_NAMES:
            continue
        url = key(row["url"])
        if url in seen:
            continue
        seen.add(url)
        yield {**row, "title": _text(row["title"]), "project": repo.split("/")[1],
               "id": url, "source": row["url"], "repository": repo, "evidence_status": SOURCE_FOUND,
               "match_level": "research", "consoles": console_families(row["url"],
                   default=("xbox-series",) if repo in XBOX_PEERS else ()),
               "author": actor(raw.get("user"))}


def cached_index(catalog, *, origin_urls=None):
    index = discovery_index()
    with catalog.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='discovery_observation'").fetchone():
            return index
        if origin_urls is None:
            selection, parameters = "ORDER BY observation.seen DESC, observation.url LIMIT ?", (PUBLIC_ORIGINS,)
        else:
            urls = tuple(sorted({alias for url in origin_urls if public_url(url)
                                 for alias in source_url_aliases(url)}))
            if not urls:
                return index
            selection = (f"WHERE observation.url IN ({','.join('?' for _ in urls)})"
                         " ORDER BY observation.seen DESC, observation.url")
            parameters = urls
        rows = db.execute("""
            SELECT observation.url, observation.revision, observation.query,
                   query.retrieved, query.status, query.items, saved.title, saved.metadata, saved.updated_at
            FROM discovery_observation AS observation LEFT JOIN discovery_query AS query USING (query)
            LEFT JOIN observations AS saved ON lower(saved.url) = observation.url AND saved.kind IN ('pr', 'issue')
        """ + selection, parameters).fetchall()
    now = time.time()
    automatic = {}
    for url, revision, query, retrieved, state, items, title, metadata, updated in rows:
        if key(url) in automatic:
            continue
        term = query.split(":", 2)[-1]
        status, _, reason = (state or "no_subject").partition(":")
        if title is not None:
            row = {"title": title, "metadata": json.loads(metadata)}
            current_term = subject(row)
            if current_term != term or revision != (source_revision(row) or updated):
                automatic[key(url)] = {"subject": current_term, "status": "not_scanned" if current_term else "no_subject",
                                       "matches": []}
                continue
        if retrieved is None:
            automatic[key(url)] = {"subject": term, "status": status, "matches": []}
            continue
        if retrieved + TTL <= now and status in {"available", "partial"}:
            status = "stale"
        checked_at = datetime.fromtimestamp(retrieved, timezone.utc)
        checked_on = checked_at.date().isoformat()
        matches = [
            {**item, "retrieved_on": checked_on, "retrieved_at": checked_at.isoformat(timespec="seconds"),
             "retrieval_status": status} for item in json.loads(items)
            if key(item["url"]) != key(url)
        ]
        automatic[key(url)] = {"status": status, "reason": reason or None, "subject": term,
                               "matches": matches[:PAGE_SIZE] if origin_urls is None else matches}
    return {**index, "automatic": automatic} if automatic else index


def acquire(db, lease):
    with db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT expires FROM discovery_lease WHERE id=1").fetchone()
        if existing and existing[0] > time.time():
            return False
        db.execute("REPLACE INTO discovery_lease VALUES (1,?,?)", (lease, time.time() + BATCH_SECONDS + 15))
    return True


def fetch(client, term, *, family="xbox-series"):
    targets = XBOX_PEERS if family=="ps5" else PS5_PEERS
    qualifier = " ".join(f"repo:{repo}" for repo in (*EXTERNAL,*targets))
    literal = f'"{term}"' if term not in {"dxgi budget", "adapter performance", "compute subobject"} else term
    query = f"{literal} is:public {qualifier}"
    data, _ = client._request(f"{API}/search/issues?{urlencode({'q': query, 'per_page': FETCH_SIZE})}", "search", None)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise Unavailable("Invalid Discovery search response", reason="invalid_payload")
    return ("partial" if data.get("incomplete_results") else "available"), list(source_results(data["items"]))


def lookup_plan(observations, known, *, requested_url=None, scheduled=False):
    plan = {}
    for observation in observations:
        url = observation["url"]
        explicit = requested_url is not None and url == requested_url
        if (not public_url(url) or not RESULT_PATH.fullmatch(urlsplit(url).path)
                or (not explicit and (observation["status"] != "open" or source_repo(url) not in known))):
            continue
        term = subject(observation)
        if explicit or (term and (not scheduled or not BROAD_FAILURE.fullmatch(term))):
            plan.setdefault(url.lower(), (source_revision(observation) or observation.get("updated_at"), term))
    return plan


def query_for(url, term):
    family = "ps5" if "ps5" in console_families(url) else "xbox-series"
    return f"{QUERY_VERSION}:{family}:{term}"


def project_priority(url, updated_at, now):
    if source_repo(url) not in PRIORITY_PROJECTS:
        return 0
    changed = _timestamp(updated_at)
    return max(discovery_queue.FRESH_PRIORITY, changed) if now - FRESH_WINDOW <= changed <= now else 1


def scan(catalog, observations, *, online=False, max_lookups=MAX_LOOKUPS, requested_url=None, scheduled=False):
    if type(max_lookups) is not int or not 1 <= max_lookups <= MAX_LOOKUPS:
        raise ValueError(f"Use 1 to {MAX_LOOKUPS} Discovery lookups per batch")
    known = {row["repo"].lower() for row in catalog.projects()}
    if scheduled:
        observations = list(observations)
    plan = lookup_plan(observations, known, requested_url=requested_url, scheduled=scheduled)
    report = {"status": "offline" if not online else "complete", "eligible": sum(bool(term) for _, term in plan.values()),
              "lookups": 0, "cache_hits": 0, "origins": []}
    if not online:
        return report
    with catalog.connect() as db:
        db.execute("PRAGMA busy_timeout=650")
        db.executescript(SCHEMA + PEOPLE_SCHEMA + discovery_queue.SCHEMA)
        lease = uuid4().hex
        if not acquire(db, lease):
            return {**report, "status": "busy"}
        try:
            client = _Sync(db, False, anonymous=True, time_budget=BATCH_SECONDS)
            policy = json.loads((DATA / "people_policy.json").read_bytes())
            if scheduled:
                now = time.time()
                updated = {row["url"].lower(): row.get("updated_at") for row in observations}
                jobs = {url: (revision, query_for(url, term), project_priority(url, updated.get(url), now))
                        for url, (revision, term) in plan.items()}
                discovery_queue.schedule(db, jobs, now)
                report["queue_metrics"] = {"before": discovery_queue.metrics(db, now)}
                batch = discovery_queue.ready(db, now, max_lookups)
            else:
                batch = ((url, revision, query_for(url, term)) for url, (revision, term) in plan.items())
            for url, revision, query in batch:
                _, family, term = query.split(":", 2)
                prior = db.execute("SELECT retrieved,retry_at,status,items FROM discovery_query WHERE query=?",
                                   (query,)).fetchone()
                now = time.time()
                reason = None
                if not term:
                    status, items = "no_subject", []
                elif prior and prior["retry_at"] > now:
                    status, _, reason = prior["status"].partition(":")
                    items = json.loads(prior["items"])
                    report["cache_hits"] += 1
                elif report["lookups"] >= max_lookups or time.monotonic() >= client.deadline:
                    report["status"] = "budget"
                    break
                else:
                    report["lookups"] += 1
                    try:
                        status, items = fetch(client, term, family=family)
                    except Unavailable as error:
                        if not error.attempted:
                            report["lookups"] -= 1
                        items = json.loads(prior["items"]) if prior else []
                        status = "stale" if items else "unavailable"
                        reason = report["status"] = error.reason
                    finished = time.time()
                    retrieved = prior["retrieved"] if status == "stale" else finished
                    with db:
                        db.execute("REPLACE INTO discovery_query VALUES (?,?,?,?,?)",
                                   (query, retrieved, finished + (TTL if status == "available" else FAILURE_TTL),
                                    f"{status}:{reason}" if reason else status, json.dumps(items)))
                with db:
                    db.execute("""
                        INSERT INTO discovery_observation VALUES (?,?,?,?)
                        ON CONFLICT(url) DO UPDATE SET revision=excluded.revision, query=excluded.query, seen=excluded.seen
                        WHERE revision IS NOT excluded.revision OR query != excluded.query
                    """, (url, revision, query, now))
                    items = [item for item in items if key(item["url"]) != key(url)]
                    if status in {"available", "partial"}:
                        remember_discovery(db, url, items, now, policy)
                report["origins"].append({"url": url, "revision": revision, "query": term, "status": status,
                                          "reason": reason or None, "matches": [item["url"] for item in items]})
                if report["status"] not in {"complete", "budget"}:
                    break
            if scheduled:
                now = time.time()
                report["queue"] = discovery_queue.counts(db, now)
                report["queue_metrics"]["after"] = discovery_queue.metrics(db, now)
                if report["status"] == "complete" and report["queue"]["ready"]:
                    report["status"] = "budget"
        finally:
            with db:
                db.execute("DELETE FROM discovery_lease WHERE id=1 AND lease=?", (lease,))
    return report


def link_result(catalog, observation):
    """Search one normalized observation; a user-selected PR may already be merged."""
    url = observation["url"]
    term = subject(observation)
    batch = scan(catalog, [observation], online=True, max_lookups=1, requested_url=url)
    origin = next(iter(batch["origins"]), None)
    index = cached_index(catalog, origin_urls=[url])
    # Ignore a prior revision's automatic results if this attempt never ran.
    if not origin:
        index = {**index, "automatic": {}}
    report = discover(origin_url=url, index=index, limit=PAGE_SIZE)
    if term and not report["case"] and not origin:
        report = discover(term, origin_url=url, index=index, limit=PAGE_SIZE)
    primary, lexical = [], []
    for row in report["matches"]:
        target = primary if row["match"]["exact"] or row in report["technical_recommendations"] else lexical
        target.append((row, "catalog"))
    external = [(row, "github") for row in report["automatic_matches"]]
    found = {}
    for row, route in primary + external + lexical:
        source = row["source"]
        if key(source) != key(url):
            found.setdefault(key(source), {"url": source, "title": row["title"], "route": route,
                                         "evidence_status": row["evidence_status"]})
    status = origin["status"] if origin else batch["status"]
    issue = origin.get("reason") if origin else status
    if status == "no_subject":
        explanation = "No supported technical subject was found in the PR title or stored metadata. No external search ran."
    elif status == "available":
        explanation = ("Open each source to compare the mechanism and revision." if found else
                       "The indexed corpus and first bounded GitHub page yielded no other source for this subject.")
    elif status == "partial":
        explanation = "GitHub returned an incomplete search page. A missing match is inconclusive."
    else:
        explanation = f"The external search is {issue or status}. Any retained results need a freshness check."
    from . import code_search
    code = (code_search.report(code_search.projection(catalog), code_search.observation_query(observation), origin_url=url)
            if subject_kind(observation.get("title", "")) == "implementation" else {"status": "not_technical", "matches": []})
    if code["matches"]:
        explanation += " Pinned code candidates require source review."
    return {"url": url, "revision": source_revision(observation), "subject": term, "status": status,
            "search_issue": issue, "lookups": batch["lookups"], "cache_hits": batch["cache_hits"],
            "top5": list(found.values())[:PAGE_SIZE], "explanation": explanation, "source_code": code}


def search_link(catalog, url):
    """Resolve an explicitly supplied public PR; never expand catalog subscriptions."""
    if isinstance(url, str):
        url = url.removesuffix("/")
    if not isinstance(url, str) or len(url) > 500 or not PR_URL.fullmatch(url):
        raise ValueError("Provide a public GitHub pull request URL")
    owner, name, _, number = urlsplit(url).path.strip("/").split("/")
    repo = current_repository(f"{owner}/{name}")
    projects = catalog.projects()
    tracked = next((project for project in projects if project["repo"].casefold() == repo.casefold()), None)
    project = tracked or {"repo": repo, "slug": repo.casefold()}
    source = f"https://github.com/{project['repo']}/pull/{number}"
    checked = refresh_references(projects if tracked else [*projects, project], catalog.path, [source], anonymous=True)
    if checked["references"] or not checked["items"]:
        failure = next(iter(checked["references"]), {})
        reason = failure.get("reason") or "unavailable"
        retry = failure.get("retry_at")
        detail = (f" Retry after {retry}." if retry else "")
        return {"url": source, "revision": None, "subject": "", "status": reason, "retry_at": retry, "lookups": 0,
                "cache_hits": 0, "top5": [], "explanation":
                f"Public PR metadata could not be read ({reason}). No external search ran.{detail}"}
    if tracked:
        catalog.record_sync(checked, update_health=False)
    return link_result(catalog, checked["items"][0])


def main():
    from .__main__ import DEFAULT_DB, DEFAULT_SEED

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--online", action="store_true", help="allow bounded anonymous GitHub reads")
    parser.add_argument("--limit", type=int, default=MAX_LOOKUPS)
    parser.add_argument("--url", help="look up previous work for one public GitHub PR using --online")
    args = parser.parse_args()
    if not 1 <= args.limit <= MAX_LOOKUPS:
        parser.error(f"--limit must be between 1 and {MAX_LOOKUPS}")
    if args.url and not args.online:
        parser.error("--url needs --online to read the public PR")
    catalog = Catalog(args.db, DEFAULT_SEED)
    try:
        report = (search_link(catalog, args.url) if args.url else
                  scan(catalog, catalog.observations(limit=None), online=args.online, max_lookups=args.limit, scheduled=True))
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
