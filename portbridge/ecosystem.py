"""Find source leads and publish reviewed, narrowly scoped capability evidence."""

from collections import defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.client import HTTPException
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from .catalog import public_url
from .discovery import SEARCH_FOCUS, SEARCH_INTERVAL, mentions, repository
from .github import NoRedirect, find_public_projects


SOURCES = {
    "six-on-pc": ("Six on PC", "https://sixonpc.com/data.json"),
    "portwatch-vi": ("PortWatch VI", "https://portwatch-vi.xyz/data/tracker.json"),
    "pc-race": ("GTA VI PC Race", "https://vuyp.github.io/gta6-pc-race/"),
    "github-search": ("GitHub Search", "https://github.com/search?type=repositories&q=Xbox+Series+compatibility"),
}
AREAS = {
    "shaders": ("Shader translation", "Трансляция шейдеров"),
    "rdna2-wave64": ("RDNA2 and Wave64", "RDNA2 и Wave64"),
    "graphics": ("Graphics", "Графические подсистемы"),
    "gpu-sync": ("GPU synchronization", "Синхронизация GPU"),
    "memory": ("Memory management", "Управление памятью"),
    "frames": ("Frame rendering", "Отрисовка кадров"),
    "ray-tracing": ("Ray tracing", "Трассировка лучей"),
    "audio": ("Audio", "Звук"),
    "performance": ("Performance", "Производительность"),
    "hardware": ("Hardware testing", "Аппаратное тестирование"),
}
EVIDENCE_KINDS = {"source", "reported", "tested", "merged"}
EVIDENCE_FILE = Path(__file__).with_name("data") / "capabilities.json"
MAX_FEED_BYTES = 512 * 1024
MAX_REPOS_PER_SOURCE = 100
MAX_LEADS = 60


def _repo(value):
    try:
        return repository(value)
    except ValueError:
        return None


class _RaceLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.repos = []
        self.standings = False

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if fields.get("id") == "standings":
            self.standings = True
        if self.standings and fields.get("id") in {"updates", "forecast", "method"}:
            self.standings = False
        if not self.standings or tag != "a" or "name" not in (fields.get("class") or "").split():
            return
        try:
            url = urlsplit(fields.get("href") or "")
        except ValueError:
            return
        if url.scheme == "https" and url.netloc == "github.com" and not (url.query or url.fragment):
            self.repos.append(url.path.strip("/"))


def _project_names(source, raw):
    if source == "pc-race":
        parser = _RaceLinks()
        parser.feed(raw.decode("utf-8"))
        parser.close()
        if not parser.repos:
            raise ValueError("standings repository links missing")
        names = parser.repos
    else:
        groups = ("projects",) if source == "six-on-pc" else ("efforts", "candidates")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not all(isinstance(payload.get(key), list) for key in groups):
            raise ValueError("repository list missing")
        names = [row.get("repo") for key in groups for row in payload[key] if isinstance(row, dict)]
    repos = sorted({name for value in names if (name := _repo(value))})
    if not repos:
        raise ValueError("tracker has no valid project repository links")
    return repos[:MAX_REPOS_PER_SOURCE]


def _fetch_tracker(source, etag):
    accept = "text/html" if source == "pc-race" else "application/json"
    headers = {"Accept": accept, "User-Agent": "PortBridge/1.0"}
    if etag:
        headers["If-None-Match"] = etag
    request = Request(SOURCES[source][1], headers=headers)
    try:
        with build_opener(NoRedirect()).open(request, timeout=6) as response:
            payload = response.read(MAX_FEED_BYTES + 1)
            if len(payload) > MAX_FEED_BYTES:
                raise ValueError("tracker response too large")
            etag = response.headers.get("ETag")
        etag = etag if etag and len(etag) <= 300 and "\r" not in etag and "\n" not in etag else None
        return _project_names(source, payload), etag
    except HTTPError as exc:
        with exc:
            if exc.code == 304 and etag:
                return None, etag
            raise


def _cached(catalog):
    with catalog.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='ecosystem_sources' AND type='table'").fetchone():
            return {}
        return {row["source"]: row for row in db.execute("SELECT * FROM ecosystem_sources")}


def refresh_ecosystem(catalog):
    """Refresh each fixed source independently while retaining its last usable response."""
    cached = _cached(catalog)
    now = time.time()
    for source in SOURCES:
        old = cached.get(source)
        if old and now - old["attempt_at"] < SEARCH_INTERVAL:
            continue
        names, etag, last_success, state = "[]", None, None, "failed"
        if old:
            names, etag, last_success = old["repositories"], old["etag"], old["success_at"]
        try:
            if source == "github-search":
                queries = {focus: query for focus, (query, _) in SEARCH_FOCUS.items()}
                found = find_public_projects(catalog.path, queries)
                if found.keys() != queries.keys():
                    raise ValueError("incomplete GitHub search")
                candidates = sorted({name for repos in found.values() for value in repos if (name := _repo(value))})
            else:
                candidates, etag = _fetch_tracker(source, etag)
            if candidates is not None:
                names = json.dumps(candidates)
            last_success, state = now, "ok"
        except (OSError, HTTPException, ValueError, RecursionError):
            state = "cached" if last_success is not None else "failed"
        with catalog.connect() as db:
            db.execute("""INSERT INTO ecosystem_sources VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET repositories=excluded.repositories, etag=excluded.etag,
                    attempt_at=excluded.attempt_at, success_at=excluded.success_at, state=excluded.state
                WHERE excluded.attempt_at>=ecosystem_sources.attempt_at""",
                       (source, names, etag, now, last_success, state))


def _utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds") if epoch is not None else None


def capability_evidence(projects):
    known = {project["slug"] for project in projects}
    rows = json.loads(EVIDENCE_FILE.read_text(encoding="utf-8"))
    records = []
    for row in rows:
        if row["project"] not in known:
            continue
        if row["area"] not in AREAS or row["kind"] not in EVIDENCE_KINDS or not public_url(row["evidence"]):
            raise ValueError("invalid capability evidence")
        records.append(row)
    return records


def build_ecosystem(catalog, *, projects=None, observations=None):
    projects = catalog.projects() if projects is None else projects
    tracked = {repository(project["repo"]) for project in projects}
    observations = catalog.observations(limit=None) if observations is None else observations
    source_map = defaultdict(list)
    cached = _cached(catalog)
    sources = []
    for key, (label, url) in SOURCES.items():
        row = cached.get(key)
        names = {repository(name) for name in json.loads(row["repositories"])} if row else set()
        for name in names:
            source_map[name].append(key)
        sources.append({"id": key, "name": label, "url": url,
                        "state": row["state"] if row else "pending",
                        "last_attempt": _utc(row["attempt_at"]) if row else None,
                        "last_success": _utc(row["success_at"]) if row else None, "repositories": len(names)})
    linked = {item["repo"]: item for item in mentions(projects, observations)}
    candidates = (source_map.keys() | linked.keys()) - tracked
    ranked = sorted(candidates, key=lambda repo: (-len(source_map.get(repo, [])),
                                                  -linked.get(repo, {}).get("project_count", 0), repo))
    evidence = capability_evidence(projects)
    return {
        "sources": sources,
        "areas": [{"id": key, "name": {"en": title[0], "ru": title[1]}} for key, title in AREAS.items()],
        "capabilities": evidence,
        "leads": [{"repo": name, "url": f"https://github.com/{name}", "sources": source_map.get(name, []),
                   "references": linked.get(name, {}).get("references", []), "state": "needs_review"}
                  for name in ranked[:MAX_LEADS]],
        "counts": {"tracked": len(tracked), "lead_repositories": len(candidates), "capability_evidence": len(evidence)},
    }
