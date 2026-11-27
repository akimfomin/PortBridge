"""Rebuild the experimental index from pinned Git mirrors and hashed public files."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha1
from pathlib import Path
import json
import subprocess
import sys
from time import perf_counter, sleep
from urllib.error import HTTPError, URLError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", type=Path)
    parser.add_argument("database", type=Path)
    parser.add_argument("cache", type=Path)
    parser.add_argument("mirrors", nargs="+", type=Path, help="directories containing pinned bare Git mirrors")
    args = parser.parse_args()
    sys.path.insert(0, str(args.product.resolve()))
    from portbridge import code_research, code_search, source_corpus

    args.cache.mkdir(parents=True, exist_ok=True)
    groups = code_research.scopes()
    trees = {}
    entries = []
    for group in groups:
        repo = group["repo"]
        name = repo.split("/")[1]
        mirror = next((parent / name for parent in args.mirrors if (parent / name).is_dir()), None)
        if mirror is None:
            raise ValueError(f"No Git metadata mirror for {repo}")
        tree = subprocess.check_output(
            ["git", "-C", str(mirror), "ls-tree", "-rz", group["revision"], "--", *group["directories"]]
        )
        for record in tree.decode("utf-8").split("\0"):
            if not record:
                continue
            mode, kind, blob, path = record.replace("\t", " ", 1).split(" ", 3)
            if (kind == "blob" and source_corpus.BLOB_SHA.fullmatch(blob)
                    and code_research.regular_source(group, path, mode)):
                entries.append((group, path, blob, mode))
        trees[repo] = {"tree": [], "truncated": False}

    if len(entries) > code_research.MAX_FILES:
        raise ValueError("Too many approved files")

    def load(entry):
        group, path, blob, mode = entry
        file = args.cache / blob
        if file.exists():
            content = file.read_bytes()
        else:
            reference = {"repo": group["repo"], "revision": group["revision"], "path": path}
            for attempt in range(3):
                try:
                    content = code_search._fetch(reference)
                    break
                except URLError as error:
                    if attempt == 2 or isinstance(error, HTTPError) and error.code not in {500, 502, 503, 504}:
                        raise
                    sleep(0.25)
        if len(content) > source_corpus.MAX_FILE_BYTES:
            return group["repo"], None
        fingerprint = sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if fingerprint != blob:
            raise ValueError(f"Content mismatch for {group['repo']}/{path}")
        if not file.exists():
            file.write_bytes(content)
        return group["repo"], {"type": "blob", "mode": mode, "path": path, "sha": blob, "size": len(content)}

    start = perf_counter()
    byte_count = 0
    for offset in range(0, len(entries), 32):
        with ThreadPoolExecutor(max_workers=4) as pool:
            for repo, row in pool.map(load, entries[offset:offset + 32]):
                if row:
                    trees[repo]["tree"].append(row)
                    byte_count += row["size"]
        if byte_count > code_research.MAX_SOURCE_BYTES:
            raise ValueError("Approved content exceeds the byte budget")
    scan_seconds = perf_counter() - start
    start = perf_counter()
    result = code_research.refresh(args.database, tree_fetch=lambda group: trees[group["repo"]],
                                   fetch=lambda ref: (args.cache / ref["blob"]).read_bytes())
    result.update({"source_bytes": byte_count, "collect_seconds": round(scan_seconds, 3),
                   "build_seconds": round(perf_counter() - start, 3)})
    print(json.dumps(result, indent=2))
    return bool(result["errors"])


if __name__ == "__main__":
    raise SystemExit(main())
