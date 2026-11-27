"""Experimental query-selected source candidates for the local Discovery catalog."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from . import code_search, source_corpus
from .matching import current_repository

SCOPES = {
    "KhronosGroup/SPIRV-Tools": ("test/val",),
    "KhronosGroup/VK-GL-CTS": ("external/vulkancts/modules/vulkan/synchronization",
                            "external/vulkancts/modules/vulkan/subgroups"),
    "HansKristian-Work/vkd3d-proton": ("tests",),
    "xcl-dev/xcl": ("crates/xcl/src/gpu/dxil",),
}
MAX_FILES = 256
SHORTLIST = 16
APPLICATION_ID = 0x50424352
SCHEMA = """
CREATE TABLE IF NOT EXISTS code_research_generation (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    policy TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS code_research_files (
    repo TEXT NOT NULL,
    path TEXT NOT NULL,
    revision TEXT NOT NULL,
    blob TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (repo, path)
);
CREATE TABLE IF NOT EXISTS code_research_terms (
    term TEXT NOT NULL,
    repo TEXT NOT NULL,
    path TEXT NOT NULL,
    PRIMARY KEY (term, repo, path),
    FOREIGN KEY (repo, path) REFERENCES code_research_files(repo, path) ON DELETE CASCADE
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS code_research_file_terms ON code_research_terms(repo, path);
"""


def scopes():
    return [{**group, "directories": SCOPES[group["repo"]], "scoped": True}
            for group in code_search._manifest() if group["repo"] in SCOPES]


def generation():
    return sha256(json.dumps([code_search.CACHE_PREFIX, scopes()], sort_keys=True).encode()).hexdigest()


@contextmanager
def connect(path, *, write=False):
    path = Path(path).resolve()
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
    mode = "rwc" if write else "ro"
    with closing(sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True)) as db, db:
        app = db.execute("PRAGMA application_id").fetchone()[0]
        if app != APPLICATION_ID:
            if not write or app or db.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone():
                raise ValueError("Use a dedicated code research database")
            db.execute(f"PRAGMA application_id={APPLICATION_ID}")
        db.execute("PRAGMA foreign_keys=ON")
        yield db


def references(tree_fetch):
    result = []
    for group in scopes():
        repo, revision = group["repo"], group["revision"]
        tree = tree_fetch(group)
        if not isinstance(tree, dict) or tree.get("truncated") is not False or not isinstance(tree.get("tree"), list):
            raise ValueError(f"Incomplete research tree for {repo}")
        seen = set()
        for entry in tree["tree"]:
            if not isinstance(entry, dict):
                continue
            path, blob = entry.get("path"), entry.get("sha")
            if (entry.get("type") != "blob" or entry.get("mode") != "100644"
                    or not source_corpus.valid_file(group, path) or path in seen or not isinstance(blob, str)
                    or not source_corpus.BLOB_SHA.fullmatch(blob)
                    or type(entry.get("size")) is not int or not 0 < entry["size"] <= source_corpus.MAX_FILE_BYTES):
                continue
            seen.add(path)
            result.append({"repo": repo, "revision": revision, "path": path, "blob": blob,
                           "license": group["license"],
                           "license_url": f"https://github.com/{repo}/blob/{revision}/{group['license_path']}"})
        if not seen:
            raise ValueError(f"No eligible files in research tree for {repo}")
    if len(result) > MAX_FILES:
        raise ValueError("Research source tree exceeds its file budget")
    return sorted(result, key=lambda row: (row["repo"], row["path"]))


def refresh(path, *, tree_fetch=source_corpus.fetch_tree, fetch=code_search._fetch):
    policy = generation()
    with connect(path, write=True) as db:
        db.executescript(SCHEMA)
        current = db.execute("SELECT policy FROM code_research_generation WHERE id=1").fetchone()
        count = db.execute("SELECT COUNT(*) FROM code_research_files").fetchone()[0]
    if current == (policy,) and count:
        return {"indexed": 0, "expected": count, "cached": count, "errors": []}
    refs = references(tree_fetch)
    updated, errors = [], []

    def build(ref):
        try:
            try:
                body = fetch(ref)
            except URLError as error:
                if isinstance(error, HTTPError) and error.code not in {500, 502, 503, 504}:
                    raise
                sleep(0.25)
                body = fetch(ref)
            return code_search.index_file(ref, body), None
        except (OSError, ValueError) as error:
            return ref, type(error).__name__

    with ThreadPoolExecutor(max_workers=4) as pool:
        for row, error in pool.map(build, refs):
            if error:
                errors.append({"path": code_search._key(row), "reason": error})
            else:
                updated.append(row)
    if not errors:
        # Readers see one complete revision of the corpus. Keep a previously
        # usable index when a download or integrity check fails.
        with connect(path, write=True) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM code_research_files")
            for row in updated:
                repo, path = row["repo"], row["path"]
                db.execute("INSERT INTO code_research_files VALUES (?,?,?,?,?)",
                           (repo, path, row["revision"], row["blob"], json.dumps(row, separators=(",", ":"))))
                db.executemany("INSERT INTO code_research_terms VALUES (?,?,?)",
                               ((term, repo, path) for term in row["terms"]
                                if not term.startswith(code_search.ANCHOR_PREFIX)))
            db.execute("INSERT OR REPLACE INTO code_research_generation VALUES (1,?)", (policy,))
    return {"indexed": len(updated) if not errors else 0, "expected": len(refs), "cached": 0, "errors": errors}


def lookup(path, query, *, origin_url, limit=5):
    exact, _ = code_search.query_terms(query)
    exact = sorted(term for term in exact if not code_search.GENERIC_STATUS.match(term))
    if len(exact) < 2 and not any(term.startswith(code_search.VUID_PREFIX) for term in exact):
        return []
    owner = current_repository("/".join(urlsplit(origin_url).path.split("/")[1:3]))
    marks = ",".join("?" for _ in exact)
    with connect(path) as db:
        db.execute("BEGIN")
        current = db.execute("SELECT policy FROM code_research_generation WHERE id=1").fetchone()
        if current != (generation(),):
            return []
        rows = db.execute(f"""
            WITH shortlist AS (
                SELECT repo,path,COUNT(*) AS overlap,
                       MAX(term GLOB 'pb_vuid_*') AS diagnostic
                FROM code_research_terms
                WHERE term IN ({marks}) AND repo != ? COLLATE NOCASE
                GROUP BY repo,path HAVING COUNT(*) >= 2 OR diagnostic
                ORDER BY diagnostic DESC,overlap DESC,repo,path LIMIT ?
            )
            SELECT payload FROM shortlist JOIN code_research_files USING (repo,path)
            ORDER BY diagnostic DESC,overlap DESC,repo,path
        """, (*exact, owner, SHORTLIST)).fetchall()
    index = {"version": code_search.SCHEMA_VERSION, "files": [json.loads(row[0]) for row in rows]}
    return code_search.lookup(index, query, origin_url=origin_url, limit=limit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--refresh", action="store_true")
    operation.add_argument("--query")
    parser.add_argument("--origin", default="")
    args = parser.parse_args()
    if args.refresh:
        result = refresh(args.db)
    else:
        result = {"matches": lookup(args.db, args.query, origin_url=args.origin)}
    print(json.dumps(result, indent=2))
    return int(bool(result.get("errors")))


if __name__ == "__main__":
    raise SystemExit(main())
