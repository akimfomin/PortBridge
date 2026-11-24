"""Follow public repository references into a reviewed coordination queue."""

from collections import defaultdict
import json
import time

from .exchange_fields import Conflict, OWNER, PermissionDenied, REPOSITORY, _source, _text, _timestamp
from .github import find_public_projects
from .matching import current_repository
from .office import source_repo


DISCOVERY_SCHEMA = """
CREATE TABLE IF NOT EXISTS office_projects (
    repo TEXT PRIMARY KEY, evidence_url TEXT NOT NULL, next_step TEXT NOT NULL,
    author_id INTEGER NOT NULL REFERENCES principals(id), nominated_at INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'nominated', reviewer_id INTEGER REFERENCES principals(id),
    reviewed_at INTEGER
);
CREATE TABLE IF NOT EXISTS office_external_revisions (
    url TEXT PRIMARY KEY, repo TEXT NOT NULL REFERENCES office_projects(repo),
    revision TEXT, checked_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS office_project_search (
    focus TEXT PRIMARY KEY, projects TEXT NOT NULL, checked_at INTEGER NOT NULL
);
"""
SEARCH_INTERVAL = 6 * 60 * 60
SEARCH_FOCUS = {
    "shaders": ('"Xbox Series" "shader recompiler"', "Шейдеры Xbox Series"),
    "linux": ('"Xbox Series" "SPIR-V" in:description,readme', "Шейдеры Xbox Series на Vulkan"),
    "windows": ('"Xbox Series" "compatibility" "D3D12" in:description,readme', "Совместимость Xbox Series на Windows"),
}


def repository(value):
    if not isinstance(value, str) or len(value) > 140:
        raise ValueError("use a GitHub owner/repository name")
    owner, _, name = value.partition("/")
    if not OWNER.fullmatch(owner) or not REPOSITORY.fullmatch(name) or name in {".", ".."}:
        raise ValueError("use a GitHub owner/repository name")
    return current_repository(value).casefold()


def mentions(projects, records):
    connected = {current_repository(project["repo"]).casefold() for project in projects}
    cues = defaultdict(dict)
    for record in records:
        if record["kind"] not in {"issue", "pr", "commit"}:
            continue
        technical = record["metadata"].get("technical") or {}
        candidates = technical.get("external_repositories", []) if isinstance(technical, dict) else []
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            try:
                repo = repository(candidate)
            except ValueError:
                continue
            if repo not in connected:
                cues[repo][record["url"]] = record["project"]
    ranked = sorted(cues.items(), key=lambda pair: (-len(set(pair[1].values())), -len(pair[1]), pair[0]))
    return [{"repo": repo, "url": f"https://github.com/{repo}", "state": "mentioned",
             "source_count": len(sources), "project_count": len(set(sources.values())),
             "references": [{"url": source, "project": project} for source, project in list(sources.items())[:3]]}
            for repo, sources in ranked[:60]]


def refresh_project_leads(exchange):
    """Periodically look beyond current catalog links, retaining the last complete search."""
    now = int(time.time())
    with exchange._connect() as db:
        recent = {row[0] for row in db.execute("SELECT focus FROM office_project_search WHERE checked_at>?",
                                               (now - SEARCH_INTERVAL,))}
    queries = {key: query for key, (query, _) in SEARCH_FOCUS.items() if key not in recent}
    if not queries:
        return
    found = find_public_projects(exchange.path, queries)
    with exchange._connect() as db:
        db.executemany("""INSERT INTO office_project_search VALUES (?, ?, ?)
            ON CONFLICT(focus) DO UPDATE SET projects=excluded.projects, checked_at=excluded.checked_at
            WHERE excluded.checked_at>=office_project_search.checked_at""",
                       ((key, json.dumps(names), now) for key, names in found.items()))


def searched_projects(rows, excluded):
    found = {}
    for row in rows:
        if row["focus"] not in SEARCH_FOCUS:
            continue
        for name in json.loads(row["projects"]):
            try:
                repo = repository(name)
            except ValueError:
                continue
            if repo not in excluded:
                project = found.setdefault(repo, {"repo": repo, "url": f"https://github.com/{repo}", "state": "found",
                                                   "search_focus": []})
                project["search_focus"].append(SEARCH_FOCUS[row["focus"]][1])
    return sorted(found.values(), key=lambda project: -len(project["search_focus"]))


PROJECTS = """SELECT n.*, a.name AS author, r.name AS reviewer FROM office_projects n
              JOIN principals a ON a.id=n.author_id LEFT JOIN principals r ON r.id=n.reviewer_id"""


def project_view(row):
    return {key: row[key] for key in ("repo", "evidence_url", "next_step", "state", "author", "reviewer")} | {
        "url": f"https://github.com/{row['repo']}", "nominated_at": _timestamp(row["nominated_at"]),
        "reviewed_at": _timestamp(row["reviewed_at"]),
    }


class DiscoveryStore:
    def __init__(self, exchange):
        self.exchange = exchange

    def projects(self, token, catalog):
        with self.exchange._connect() as db:
            actor = self.exchange._principal(db, token, "read")
            tracked = [project_view(row) for row in db.execute(PROJECTS + """ ORDER BY
                CASE n.state WHEN 'compare' THEN 0 WHEN 'nominated' THEN 1 ELSE 2 END,
                n.nominated_at DESC, n.repo LIMIT 60""")]
            searched = db.execute("SELECT * FROM office_project_search ORDER BY focus").fetchall()
        known = {entry["repo"] for entry in tracked}
        connected = catalog.projects()
        suggestions = [entry for entry in mentions(connected, catalog.observations(limit=None))
                       if entry["repo"] not in known]
        excluded = known | {current_repository(entry["repo"]).casefold() for entry in suggestions + connected}
        candidates = searched_projects(searched, excluded)
        return {"projects": (tracked + suggestions + candidates)[:60],
                "viewer": {"name": actor["name"], "scopes": actor["scopes"]}}

    def nominate(self, token, payload, catalog):
        if payload.keys() != {"repo", "evidence_url", "next_step"}:
            raise ValueError("invalid project nomination fields")
        repo, url = repository(payload["repo"]), _source(payload["evidence_url"])
        if (current_repository(source_repo(url)) != repo
                or repo in {current_repository(project["repo"]).casefold() for project in catalog.projects()}):
            raise ValueError("provide a source in a repository outside the connected catalog")
        next_step = _text(payload["next_step"], "next_step", 400)
        with self.exchange._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            actor = self.exchange._principal(db, token, "contribute")
            if "read" not in actor["scopes"]:
                raise PermissionDenied("read scope required")
            existing = db.execute(PROJECTS + " WHERE n.repo=?", (repo,)).fetchone()
            if existing:
                if existing["evidence_url"] != url or existing["next_step"] != next_step:
                    raise Conflict("this repository already has another proposal")
                return project_view(existing)
            db.execute("""INSERT INTO office_projects(repo, evidence_url, next_step, author_id, nominated_at)
                       VALUES (?, ?, ?, ?, ?)""", (repo, url, next_step, actor["id"], int(time.time())))
            return project_view(db.execute(PROJECTS + " WHERE n.repo=?", (repo,)).fetchone())

    def review(self, token, repo, decision):
        repo = repository(repo)
        if decision not in ("compare", "defer"):
            raise ValueError("invalid project decision")
        with self.exchange._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            actor = self.exchange._principal(db, token, "review")
            if "read" not in actor["scopes"]:
                raise PermissionDenied("read scope required")
            row = db.execute(PROJECTS + " WHERE n.repo=?", (repo,)).fetchone()
            if not row:
                raise LookupError("nomination not found")
            if row["author_id"] == actor["id"]:
                raise PermissionDenied("another participant must review a nomination")
            if row["state"] == decision:
                return project_view(row)
            db.execute("UPDATE office_projects SET state=?, reviewer_id=?, reviewed_at=? WHERE repo=?",
                       (decision, actor["id"], int(time.time()), repo))
            return project_view(db.execute(PROJECTS + " WHERE n.repo=?", (repo,)).fetchone())
