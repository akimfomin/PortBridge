"""Immutable pages and exact postings for the public catalog browser."""

from collections import defaultdict
from hashlib import sha256
import re

from .matching import source_url_aliases
from .preflight_index import SHARD_LIMIT, digest, encode, pack, source_number


BROWSE_MANIFEST = "data/browse-index.json"
BROWSE_INDEX = re.compile(r"browse-[0-9a-f]{24}-index\.json")
BROWSE_PAGE = re.compile(r"browse-[0-9a-f]{24}-(?:matches|sources)-page-(?:0|[1-9][0-9]*)\.json")
BROWSE_TERMS = re.compile(r"browse-[0-9a-f]{24}-(?:matches|sources)-terms-[0-9a-f]{2,64}\.json")
BROWSE_POSTING = re.compile(r"browse-[0-9a-f]{24}-(?:matches|sources)-post-[0-9a-f]{64}-part-(?:0|[1-9][0-9]*)\.json")
PAGE_SIZE = 48
WORD = re.compile(r"\w+")
SOURCE_FIELDS = ("title", "url", "project", "kind", "status", "updated_at", "fetched_at")


def word_keys(*values):
    return {f"word:{word}" for value in values if isinstance(value, str) for word in WORD.findall(value.lower())}


def url_keys(*urls):
    keys = set()
    for url in urls:
        if url:
            keys.update(f"url:{alias.lower()}" for alias in source_url_aliases(url))
            if number := source_number(url):
                keys.add(f"number:{number}")
    return keys


def source_keys(row):
    technical = row.get("metadata", {}).get("technical") or {}
    return (
        word_keys(row["title"], *technical.get("terms", ()), *technical.get("signals", ()))
        | url_keys(row["url"])
        | {f'{field}:{row[field].lower()}' for field in ("project", "status", "kind")}
    )


def match_keys(row):
    sides = (row["left"], row["right"])
    titles = [side["title"] for side in sides]
    titles.extend(fields.get("title") for side in sides for fields in side.get("translations", {}).values())
    stage = "reviewed" if row["state"].startswith("reviewed_") else "candidate"
    return (
        word_keys(*titles, row.get("reason"), row.get("problem_id"))
        | url_keys(*(side["url"] for side in sides))
        | {f'project:{side["project"].lower()}' for side in sides}
        | {f"stage:{stage}", f'status:{row["state"].lower()}'}
    )


def posting_value(files, kind, hashed, key, ids):
    digits = len(str(ids[-1]))
    # Include the entry key and JSON wrappers in the leaf budget. The early
    # bound avoids encoding a long array merely to measure its size.
    if len(ids) * (digits + 1) + len(encode(key)) + 128 <= SHARD_LIMIT:
        return ids
    part_size = (SHARD_LIMIT - 128) // (digits + 1)
    for offset in range(0, len(ids), part_size):
        part = offset // part_size
        files[f"{kind}-post-{hashed}-part-{part}"] = encode({"items": ids[offset:offset + part_size]})
    return {"parts": (len(ids) + part_size - 1) // part_size}


def browse_kind(kind, rows, keys, compact):
    postings, roots, counts = defaultdict(list), defaultdict(list), defaultdict(dict)
    files = {}
    for offset in range(0, len(rows), PAGE_SIZE):
        page = rows[offset:offset + PAGE_SIZE]
        files[f"{kind}-page-{offset // PAGE_SIZE}"] = encode({"items": [compact(row) for row in page]})
        for ident, row in enumerate(page, offset):
            for key in keys(row):
                postings[key].append(ident)
    for key, ids in postings.items():
        hashed = digest(key)
        roots[hashed[:2]].append((hashed, key, posting_value(files, kind, hashed, key, ids)))
        group, _, value = key.partition(":")
        if group in {"stage", "project", "status", "kind"}:
            counts[group][value] = len(ids)
    shards = {}
    for prefix, group in roots.items():
        pack(prefix, group, shards)
    files.update({f"{kind}-terms-{prefix}": data for prefix, data in shards.items()})
    return files, {"total": len(rows), "roots": sorted(roots),
                   "counts": {key: dict(sorted(values.items())) for key, values in sorted(counts.items())}}


def build_browse_files(matches, observations):
    sources = sorted(observations, key=lambda row: (row["updated_at"] or "", row["url"]), reverse=True)
    match_files, match_spec = browse_kind("matches", matches, match_keys, lambda row: row)
    source_files, source_spec = browse_kind("sources", sources, source_keys,
                                            lambda row: {key: row[key] for key in SOURCE_FIELDS if key in row})
    files = {**match_files, **source_files}
    identity = sha256()
    for key, data in sorted(files.items()):
        identity.update(key.encode("ascii") + b":" + sha256(data).digest())
    generation = identity.hexdigest()[:24]
    manifest = {"version": 1, "generation": generation, "page_size": PAGE_SIZE,
                "kinds": {"matches": match_spec, "sources": source_spec}}
    index = encode(manifest)
    return {f"data/browse-{generation}-{key}.json": data for key, data in files.items()} | {
        BROWSE_MANIFEST: index, f"data/browse-{generation}-index.json": index,
    }
