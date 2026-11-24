"""Persistent curated problems and public GitHub observations."""

from collections import defaultdict
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from itertools import combinations
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

from . import PROJECT_LINK
from .matching import RelatedIndex, canonical_url, source_revision


PROBLEM_STATUS = {"investigating", "partial", "verified", "resolved"}
SOLUTION_STATUS = {"reported", "open", "partial", "verified", "merged", "unknown"}
EVIDENCE_KIND = {"maintainer_claim", "automated_test", "independent", "source_observation"}
EVIDENCE_OUTCOME = {"passed", "failed", "mixed", "observed", "unknown"}
OBSERVATION_KIND = {"issue", "pr", "commit", "test"}
SYNC_STATUS = {"ok", "partial", "stale", "error", "seed-only"}
PROBLEM_ID = re.compile(r"PB-[0-9]{4,}")
REPO_NAME = re.compile(r"[\w.-]+/[\w.-]+", re.ASCII)


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def utc_sort_key(value):
    return (value or "").removesuffix("Z").removesuffix("+00:00")


def public_url(url):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return (parsed.scheme == "https" and parsed.netloc == "github.com" and
            bool(parsed.path.strip("/")) and not any(ch.isspace() for ch in url))


def expect(condition, message):
    if not condition:
        raise ValueError(message)


def validate_seed(seed):
    projects = seed["projects"]
    slugs = {project["slug"] for project in projects}
    expect(len(slugs) == len(projects), "Duplicate project slug")
    for project in projects:
        expect(re.fullmatch(r"[a-z0-9-]+", project["slug"]), "Invalid project slug")
        expect(REPO_NAME.fullmatch(project["repo"]), "Invalid GitHub repository")
        expect(public_url(project["url"]), "Invalid project URL")

    problems = seed["problems"]
    ids = {problem["id"] for problem in problems}
    expect(len(ids) == len(problems), "Duplicate problem ID")
    for problem in problems:
        ident = problem["id"]
        expect(PROBLEM_ID.fullmatch(ident), f"Invalid problem ID: {ident}")
        expect(problem["status"] in PROBLEM_STATUS, f"Invalid problem status: {ident}")
        dependencies = set(problem["dependency_ids"])
        expect(dependencies <= ids and ident not in dependencies, f"Invalid dependencies: {ident}")
        subjects = {source["url"] for solution in problem["solutions"] for source in solution["source_refs"]}
        solution_projects = set()
        for solution in problem["solutions"]:
            project = solution["project"]
            expect(project in slugs and project not in solution_projects, f"Invalid solution project: {ident}")
            solution_projects.add(project)
            expect(solution["status"] in SOLUTION_STATUS, f"Invalid solution status: {ident}")
            expect(bool(solution["source_refs"]), f"Missing solution sources: {ident}")
            for source in solution["source_refs"] + solution["evidence"]:
                expect(public_url(source["url"]), f"Invalid source URL: {ident}")
            for evidence in solution["evidence"]:
                expect(evidence["kind"] in EVIDENCE_KIND, f"Invalid evidence kind: {ident}")
                expect(evidence.get("outcome", "unknown") in EVIDENCE_OUTCOME, f"Invalid evidence outcome: {ident}")
                expect(bool(evidence["observed"]), f"Missing evidence summary: {ident}")
                if "check_for" in evidence:
                    scope = evidence["check_for"]
                    expect(isinstance(scope, list) and all(isinstance(url, str) and url in subjects for url in scope),
                           f"Invalid evidence scope: {ident}")
    reference = seed.get("coordination", {}).get("reference")
    if reference:
        expect(reference["project"] in slugs and public_url(reference["url"]), "Invalid reference build")


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    slug TEXT PRIMARY KEY, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS problems (
    id TEXT PRIMARY KEY, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS withdrawn_problems (
    id TEXT NOT NULL, payload TEXT NOT NULL, withdrawn_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
    project TEXT NOT NULL REFERENCES projects(slug),
    kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT,
    fetched_at TEXT NOT NULL,
    metadata TEXT NOT NULL,
    PRIMARY KEY (project, kind, source_id)
);
CREATE INDEX IF NOT EXISTS observation_recent ON observations(updated_at DESC);
CREATE INDEX IF NOT EXISTS observation_url ON observations(lower(url));
CREATE TABLE IF NOT EXISTS source_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL, kind TEXT NOT NULL, url TEXT NOT NULL,
    previous_status TEXT NOT NULL, status TEXT NOT NULL,
    previous_revision TEXT, revision TEXT, observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS source_changes_url ON source_changes(lower(url), id);
CREATE TABLE IF NOT EXISTS sync_projects (
    slug TEXT PRIMARY KEY REFERENCES projects(slug), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history_sync (
    slug TEXT NOT NULL REFERENCES projects(slug), mode TEXT NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (slug, mode)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY, value TEXT NOT NULL
);
"""


def encode(value):
    return json.dumps(value, ensure_ascii=False)


class Catalog:
    def __init__(self, path, seed_path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        seed = json.loads(Path(seed_path).read_text(encoding="utf-8"))
        validate_seed(seed)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            db.executemany("INSERT INTO projects VALUES(?, ?) ON CONFLICT(slug) DO UPDATE SET payload=excluded.payload",
                           ((p["slug"], encode(p)) for p in seed["projects"]))
            managed = {problem["id"] for problem in seed["problems"]}
            withdrawn = [(row["id"], row["payload"], timestamp())
                         for row in db.execute("SELECT id, payload FROM problems") if row["id"] not in managed]
            db.executemany("INSERT INTO withdrawn_problems VALUES (?, ?, ?)", withdrawn)
            db.executemany("DELETE FROM problems WHERE id=?", ((row[0],) for row in withdrawn))
            db.executemany("INSERT INTO problems VALUES(?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                           ((p["id"], encode(p)) for p in seed["problems"]))
            db.execute("INSERT INTO settings VALUES('coordination', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (encode(seed.get("coordination", {})),))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def projects(self):
        with self.connect() as db:
            rows = db.execute("""SELECT projects.payload, sync.payload AS sync
                FROM projects LEFT JOIN sync_projects sync USING(slug) ORDER BY projects.rowid""").fetchall()
        projects = []
        for row in rows:
            sync = json.loads(row["sync"]) if row["sync"] else {}
            projects.append({**json.loads(row["payload"]), "sync_status": sync.get("sync_status", "seed-only"),
                             "last_success": sync.get("last_success"), "sources": sync.get("sources", {})})
        return projects

    def coordination(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key='coordination'").fetchone()
        return json.loads(row[0]) if row else {}

    def record_sync(self, result, *, update_health=True, history_mode=None):
        observed_at = timestamp()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            projects = {row[0] for row in db.execute("SELECT slug FROM projects")}
            for item in result["items"]:
                if (item["project"] not in projects or item["kind"] not in OBSERVATION_KIND or
                        not public_url(item["url"])):
                    continue
                key = (item["project"], item["kind"], str(item["source_id"]))
                previous = db.execute("""SELECT updated_at, fetched_at, status, metadata FROM observations
                    WHERE project=? AND kind=? AND source_id=?""", key).fetchone()
                updated_at = utc_sort_key(item["updated_at"])
                fetched_at = item.get("fetched_at") or observed_at
                status, metadata = item["status"], dict(item["metadata"])
                incoming_revision = source_revision({"metadata": metadata})
                old_metadata = {}
                before = after = None
                if previous:
                    older_update = utc_sort_key(previous["updated_at"])
                    prev_state = (older_update, utc_sort_key(previous["fetched_at"]))
                    if (updated_at, utc_sort_key(fetched_at)) < prev_state:
                        continue
                    old_metadata = json.loads(previous["metadata"])
                    metadata = {**old_metadata, **metadata}
                    preserve = ("merged_at", "base_branch") if updated_at == older_update else ("merged_at",)
                    for name in preserve:
                        if not metadata.get(name) and name in old_metadata:
                            metadata[name] = old_metadata[name]
                    if previous["status"] == "merged" and status == "closed":
                        status = "merged"
                if item["kind"] in {"pr", "test"}:
                    before = old_metadata.get("last_known_head_sha") or source_revision({"metadata": old_metadata})
                    after = incoming_revision
                    if previous and updated_at == older_update and not after:
                        after = source_revision({"metadata": old_metadata})
                    metadata["head_sha"] = after
                    metadata["last_known_head_sha"] = after or before
                db.execute("""INSERT INTO observations VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project, kind, source_id) DO UPDATE SET
                    title=excluded.title, url=excluded.url, status=excluded.status,
                    updated_at=excluded.updated_at, fetched_at=excluded.fetched_at, metadata=excluded.metadata""",
                    (*key, item["title"][:300], item["url"], status, item["updated_at"], fetched_at, encode(metadata)))
                if previous:
                    if previous["status"] != status or (before and after and before != after):
                        db.execute("""INSERT INTO source_changes(project, kind, url, previous_status, status,
                                      previous_revision, revision, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                   (item["project"], item["kind"], item["url"], previous["status"], status,
                                    before, after, fetched_at))
            if history_mode in {"backfill", "incremental"}:
                db.executemany("""INSERT INTO history_sync VALUES (?, ?, ?)
                    ON CONFLICT(slug, mode) DO UPDATE SET payload=excluded.payload""",
                               ((entry["slug"], history_mode, encode({**entry, "checked_at": observed_at}))
                                for entry in result.get("history", []) if entry["slug"] in projects))
            if not update_health:
                return
            for status in result.get("projects", []):
                slug = status.get("slug")
                if slug in projects:
                    previous = db.execute("SELECT payload FROM sync_projects WHERE slug=?", (slug,)).fetchone()
                    record = {**(json.loads(previous[0]) if previous else {}), **status}
                    if not status.get("last_success") and previous:
                        record["last_success"] = json.loads(previous[0]).get("last_success")
                    db.execute("INSERT INTO sync_projects VALUES(?, ?) ON CONFLICT(slug) DO UPDATE SET payload=excluded.payload",
                               (slug, encode(record)))
            health = {"refresh_at": observed_at, "warnings": result.get("warnings", [])}
            db.execute("INSERT INTO settings VALUES('sync', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (encode(health),))

    def health(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key='sync'").fetchone()
            count = db.execute("SELECT count(*) FROM observations").fetchone()[0]
            tables = {state[0] for state in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            history = [dict(state) for state in db.execute(
                "SELECT slug, next_page, complete FROM github_history WHERE mode='backfill' ORDER BY slug"
            )] if "github_history" in tables else []
            history_checks = defaultdict(dict)
            if "history_sync" in tables:
                for check in db.execute("SELECT * FROM history_sync"):
                    history_checks[check["slug"]][check["mode"]] = json.loads(check["payload"])
        projects = self.projects()
        states = {project["sync_status"] for project in projects}
        details = json.loads(row[0]) if row else {"refresh_at": None, "warnings": []}
        if row is None:
            status = "seed-only"
        elif states == {"ok"} and not details["warnings"]:
            status = "ok"
        elif states == {"stale"}:
            status = "stale"
        elif not count:
            status = "error"
        else:
            status = "partial"
        backfill = {entry["slug"]: entry for entry in history}
        sources = []
        for project in projects:
            slug = project["slug"]
            cursor = backfill.get(slug, {})
            history_state = "complete" if cursor.get("complete") else "partial" if cursor else "unknown"
            modes = {"backfill": {"status": history_state, "next_page": cursor.get("next_page")},
                     "incremental": {"status": "unknown"}}
            for mode, check in history_checks[slug].items():
                modes[mode].update(check)
            sources.append({"slug": slug, "repo": project["repo"], "freshness": project["sync_status"],
                            "last_success": project["last_success"], "kinds": project["sources"], "history": modes})
        return {"status": status, "observation_count": count, "history": history, "sources": sources, **details}

    def problems(self, *, q="", project="", status="", partial=False):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM problems ORDER BY id").fetchall()
        found = []
        for row in rows:
            problem = summarize(json.loads(row[0]))
            if status and status != problem["status"]:
                continue
            if project and project not in {solution["project"] for solution in problem["solutions"]}:
                continue
            if partial and not problem["partial_opportunity"]:
                continue
            if contains(problem, q):
                found.append(problem)
        return self.annotate_sources(found)

    def problem(self, ident):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM problems WHERE id=?", (ident,)).fetchone()
        return self.annotate_sources([summarize(json.loads(row[0]))])[0] if row else None

    def curated_topic(self, source):
        matches = [card["id"] for card in self.problems() if any(
            not urlsplit(ref["url"]).fragment and canonical_url(ref["url"]) == source
            for solution in card["solutions"] for ref in solution["source_refs"]
        )]
        return matches[0] if len(matches) == 1 else None

    def observed_revisions(self, sources):
        urls = sorted({canonical_url(source) for source in sources})
        result = {}
        with self.connect() as db:
            for start in range(0, len(urls), 200):
                chunk = urls[start:start + 200]
                placeholders = ", ".join("?" for _ in chunk)
                for row in db.execute(f"""SELECT lower(url) AS url, metadata FROM observations
                    WHERE lower(url) IN ({placeholders})""", chunk):
                    result[row["url"]] = source_revision({"metadata": json.loads(row["metadata"])})
        return result

    def annotate_sources(self, problems):
        references = defaultdict(list)
        for problem in problems:
            for solution in problem["solutions"]:
                for item in solution["source_refs"] + solution["evidence"]:
                    references[canonical_url(item["url"])].append(item)
        with self.connect() as db:
            for chunk in range(0, len(references), 200):
                urls = list(references)[chunk:chunk + 200]
                params = ",".join("?" for _ in urls)
                rows = db.execute(f"""SELECT lower(url) AS key, kind, status, updated_at, fetched_at, metadata
                                   FROM observations WHERE lower(url) IN ({params})""", urls)
                for row in rows:
                    snapshot = json.loads(row["metadata"])
                    state = {key: row[key] for key in ("kind", "status", "updated_at", "fetched_at")}
                    state["revision"] = snapshot.get("head_sha")
                    for ref in references[row["key"]]:
                        ref["github"] = state
        return problems

    def observations(self, *, q="", kind="", project="", limit=100):
        clauses, arguments = [], []
        for column, value in (("kind", kind), ("project", project)):
            if value:
                clauses.append(f"{column}=?")
                arguments.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as db:
            result = []
            for row in db.execute("SELECT * FROM observations" + where + " ORDER BY updated_at DESC", arguments):
                item = dict(row)
                item["metadata"] = json.loads(item["metadata"])
                if contains(item, q):
                    result.append(item)
                    if limit is not None and len(result) >= limit:
                        break
        return result

    def matches(self, *, q="", limit=60):
        problems = self.problems()
        approved, known_links = [], defaultdict(set)
        for problem in problems:
            references = []
            for solution in problem["solutions"]:
                refs = [{**ref, "project": solution["project"]} for ref in solution["source_refs"]]
                for ref in refs:
                    known_links[canonical_url(ref["url"])].add(problem["id"])
                references.append(refs[0])
            if contains(problem, q):
                state = "reviewed_symptom" if problem.get("relationship") == "shared_symptom" else "reviewed_same"
                reason = ("Совпадает симптом. Общая причина не установлена." if state == "reviewed_symptom"
                          else "Связь указана в проверенной карточке каталога.")
                for left, right in combinations(references, 2):
                    approved.append(match(left, right, None, reason, state, problem["id"]))
        stacks = {project["slug"]: project["stack"] for project in self.projects()}
        suggested = self.search_index().matches(stacks, exclude=lambda a, b: known_links[a] & known_links[b],
                                                keep=lambda pair: contains(pair, q), limit=limit)
        return (approved + suggested)[:limit]

    def search_index(self):
        return RelatedIndex(self.observations(limit=None))

    def related(self, url, *, limit=20):
        if not public_url(url):
            raise ValueError("related requires a public GitHub source URL")
        stacks = {project["slug"]: project["stack"] for project in self.projects()}
        origin = canonical_url(url)
        index = self.search_index()
        return {"indexed": origin in index.rows,
                "matches": index.matches(stacks, origin=origin, limit=limit)}

    def source_changes(self, *, url="", limit=100):
        if url and not public_url(url):
            raise ValueError("use a public GitHub source URL")
        condition, args = ("WHERE lower(url)=?", (canonical_url(url),)) if url else ("", ())
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                f"SELECT * FROM source_changes {condition} ORDER BY id DESC LIMIT ?", (*args, limit))]

    def outreach(self):
        projects = {project["slug"]: project for project in self.projects()}
        with self.connect() as db:
            states = {canonical_url(row["url"]): row["status"] for row in
                      db.execute("SELECT url, status FROM observations WHERE kind IN ('issue', 'pr')")}
        drafts = []
        for problem in self.problems(partial=True):
            sources = [solution for solution in problem["solutions"]
                       if solution["status"] in {"verified", "merged"} and solution.get("outreach_summary")]
            if not sources or problem.get("relationship") == "shared_symptom":
                continue
            for target in problem["solutions"]:
                if target["status"] in {"verified", "merged"}:
                    continue
                receiver = projects[target["project"]]
                target_path = f"https://github.com/{receiver['repo'].lower()}"
                target_url = next((ref["url"] for ref in target["source_refs"]
                                   if re.fullmatch(re.escape(target_path) + r"/(?:issues|pull)/[0-9]+",
                                                   canonical_url(ref["url"]))
                                   and states.get(canonical_url(ref["url"])) not in {"closed", "merged"}), None)
                if not target_url:
                    continue
                source = min(sources, key=lambda solution: projects[solution["project"]]["stack"] != receiver["stack"])
                sender = projects[source["project"]]
                source_url = source["source_refs"][0]["url"]
                mode = "reference" if sender["stack"] == receiver["stack"] else "comparison"
                caveat = ("Please confirm on this branch before treating the issue as fixed."
                          if mode == "reference" else
                          "The graphics backends differ. The test case may help; the implementation needs separate validation.")
                ident = problem["id"]
                drafts.append({
                    "id": f"{ident}:{target['project']}",
                    "problem_id": ident,
                    "target_project": target["project"],
                    "target_url": target_url,
                    "target_status": states.get(canonical_url(target_url), "unobserved"),
                    "source_project": source["project"],
                    "source_url": source_url,
                    "mode": mode,
                    "message": f"Cross-project note prepared with {PROJECT_LINK} ({ident}).\n\n"
                               f"{source['outreach_summary']}\n\n{caveat}",
                })
        return drafts


class ReadOnlyCatalog(Catalog):
    def __init__(self, path):
        self.path = Path(path).resolve()

    @contextmanager
    def connect(self):
        uri = f"{self.path.as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            yield db


def summarize(problem):
    solutions = problem["solutions"]
    confirmed = {solution["project"] for solution in solutions if
                 any(e["kind"] in {"independent", "automated_test"} for e in solution["evidence"])}
    progress = {"partial", "verified", "merged"}
    partial = (len(solutions) > 1 and any(s["status"] in progress for s in solutions) and
               any(s["status"] not in {"verified", "merged"} for s in solutions) and
               problem["status"] != "resolved")
    return {**problem, "project_count": len(solutions), "verified_count": len(confirmed),
            "partial_opportunity": partial}


def contains(payload, query):
    terms = query.casefold().split()
    if not terms:
        return True
    text = encode(payload).casefold()
    for term in terms:
        if re.fullmatch(r"#[0-9]+", term):
            number = term[1:]
            if not re.search(rf"(?:#|/issues/|/pull/){number}(?![0-9])", text):
                return False
        elif term not in text:
            return False
    return True


def match(left, right, score, reason, state, problem_id=None):
    def side(source):
        result = {key: source[key] for key in ("project", "title", "url")}
        if "translations" in source:
            result["translations"] = source["translations"]
        return result

    return {"left": side(left), "right": side(right),
            "score": score, "reason": reason, "state": state, "problem_id": problem_id}
