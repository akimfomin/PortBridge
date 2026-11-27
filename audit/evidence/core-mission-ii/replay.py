"""Replay frozen public PR metadata through the normal snapshot URL entry point."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
from unittest.mock import patch
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", type=Path)
    parser.add_argument("workdir", type=Path)
    parser.add_argument("input", nargs="+", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--code", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.product.resolve()))
    from portbridge.__main__ import DEFAULT_SEED
    from portbridge.catalog import Catalog
    from portbridge.export import export
    from portbridge.github import _technical
    from portbridge.matching import current_repository
    from portbridge.preflight import public_preflight

    args.workdir.mkdir(parents=True, exist_ok=True)
    db = args.workdir / "catalog.sqlite3"
    if args.checkpoint and not db.exists():
        with sqlite3.connect(args.checkpoint) as source, sqlite3.connect(db) as copy:
            source.backup(copy)
    catalog = Catalog(db, DEFAULT_SEED)
    projects = {current_repository(p["repo"]).casefold(): p["slug"] for p in catalog.projects() if p.get("repo")}
    sets = [json.loads(path.read_bytes()) for path in args.input]
    origins = {url: item for rows in sets for url, item in rows.items()}
    observations = []
    unsupported = []
    for url, row in origins.items():
        repo = current_repository("/".join(urlsplit(url).path.strip("/").split("/")[:2])).casefold()
        project = projects.get(repo)
        if not project:
            unsupported.append(url)
            continue
        observations.append({
            "project": project, "kind": "pr", "source_id": urlsplit(url).path.rsplit("/", 1)[1],
            "url": url, "title": row["title"], "status": "merged" if row.get("merged") else row["state"],
            "updated_at": row["updated_at"], "metadata": {
                "head_sha": row["head_sha"], "technical": _technical(row, [], projects),
            },
        })
    # Remove older copies of the named origins so a moving checkpoint cannot
    # supersede a frozen PR, then insert its exact normalized title and body.
    with catalog.connect() as connection:
        connection.executemany("DELETE FROM observations WHERE url=?",
                               [(row["url"],) for row in observations])
    catalog.record_sync({"items": observations}, update_health=False)
    if args.code:
        from portbridge.code_search import refresh
        print(refresh(catalog), file=sys.stderr)
    site = export(catalog, args.workdir / "snapshot")
    cases = []
    started = time.perf_counter()
    for url, row in origins.items():
        outputs = []
        def read_file(name, limit, *_args, **_kwargs):
            payload = (site / name).read_bytes()
            if len(payload) > limit:
                raise ValueError("Snapshot exceeds the client budget")
            outputs.append(name)
            return json.loads(payload)
        with patch("portbridge.preflight.read_public_file", side_effect=read_file):
            retrieved = public_preflight(url=url)
        candidates = [entry["right"]["url"] for entry in retrieved.get("matches", [])]
        candidates.extend(item["source"] for item in (retrieved.get("discovery") or {}).get("matches", []))
        codes = retrieved.get("source_code") or {}
        cases.append({"url": url, "head_sha": row["head_sha"], "indexed": retrieved.get("indexed"),
                      "body_sha256": hashlib.sha256(row["body"].encode()).hexdigest(),
                      "top5": list(dict.fromkeys(candidates))[:5],
                      "source_code_status": codes.get("status"), "code_top5": [
                          {"url": item["url"], "signals": item["signals"]} for item in codes.get("matches", [])],
                      "snapshot_reads": len(outputs), "external_search_requests": 0})
    print(json.dumps({"origins": len(origins), "unsupported": unsupported, "seconds": round(time.perf_counter()-started, 3),
                      "cases": cases}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
