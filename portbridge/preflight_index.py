"""Bounded static search files for public preflight."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import re
from time import monotonic
from urllib.parse import urlsplit

from .matching import (GENERAL_SOURCE_TERMS, ISA_OPCODE, RelatedIndex, observation_summary,
                       preflight_matches, rank_query, source_revision, terms)


MANIFEST = "data/preflight-index.json"
VERSIONED_MANIFEST = re.compile(r"preflight-([0-9a-f]{24})-index\.json")
SHARD = re.compile(r"preflight-[0-9a-f]{24}-[0-9a-f]{2,64}\.json")
SHARD_FORMAT = "PortBridge search shard v1"
SOURCE_NUMBER = re.compile(r"/(?:issues|pull)/([1-9][0-9]*)/?$")
SHARD_LIMIT = 128 * 1024
MANIFEST_LIMIT = 8 * 1024
POSTING_LIMIT = 96
QUERY_TERMS = 8
QUERY_READS = 20
QUERY_TIMEOUT = 12
LOOKUP_CONCURRENCY = 4
MATCH_LIMIT = 21  # The first verified check may consume one of the top 20 matches.


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def digest(key):
    return sha256(key.encode("utf-8")).hexdigest()


def source_number(url):
    match = SOURCE_NUMBER.search(urlsplit(url).path)
    return match[1] if match else None


def compact_records(index):
    """Keep the fields used by ranking and return values."""
    records = {}
    for url, row in index.rows.items():
        fields = ("kind", "project", "title", "url", "status", "fetched_at")
        record = {key: row[key] for key in fields if key in row}
        metadata = {"technical": {"terms": sorted(index.subjects[url] - index.titles[url]),
                                  "signals": sorted(index.signals[url])}}
        if revision := source_revision(row):
            metadata["sha"] = revision
        records[url] = {**record, "metadata": metadata}
    return records


def choose_postings(keys, records, *, rare=False):
    rows = []
    budget = SHARD_LIMIT - 4096
    for key in keys:
        if len(rows) >= POSTING_LIMIT:
            break
        row, size = records[key]
        if size + 1 > budget:
            break
        rows.append(row)
        budget -= size + 1
    return {"rows": rows, "truncated": len(rows) < len(keys), "rare": rare}


def source_fallback(index, url):
    """Use the same source-only fallback as local preflight without scanning unrelated rows."""
    anchors = index.titles[url] - GENERAL_SOURCE_TERMS
    rare = anchors & index.weight.keys()
    candidates = {other for word in rare for other in index.postings[word]}
    ranked = []
    project = index.rows[url]["project"]
    for other in candidates:
        row = index.rows[other]
        if row["project"] == project or index.kinds[other] != index.kinds[url]:
            continue
        shared = anchors & index.titles[other]
        if len(shared) < 2 or shared.isdisjoint(rare):
            continue
        score = rank_query(index.subjects[url], row["title"], index.subjects[other] | index.signals[other])
        if score:
            ranked.append((-score, other))
    return [other for _, other in sorted(ranked)[:MATCH_LIMIT]]


def index_entries(projects, observations):
    index = RelatedIndex(observations)
    stacks = {project["slug"]: project["stack"] for project in projects}
    records = compact_records(index)
    encoded = {key: (record, len(encode(record))) for key, record in records.items()}
    words = defaultdict(set)
    numbers = defaultdict(set)
    for url, record in records.items():
        original = index.rows[url].get("metadata", {}).get("technical") or {}
        technical = {**record["metadata"]["technical"], "code_symbols": original.get("code_symbols", []),
                     "discovery_cues": original.get("discovery_cues", [])}
        origin = {**record, "metadata": {**record["metadata"], "technical": technical}}
        matches = preflight_matches(index, stacks, url, limit=MATCH_LIMIT)
        capsule = {"row": origin, "matches": matches, "rare": sorted(index.titles[url] & index.weight.keys()),
                   "fallback": [observation_summary(records[other]) for other in source_fallback(index, url)]
                   if len(matches) < 2 else []}
        yield f"source:{url}", capsule
        if number := source_number(url):
            numbers[number].add(url)
        for word in index.subjects[url] | index.signals[url]:
            words[word].add(url)
    for word, keys in words.items():
        ordered = sorted(keys, key=lambda url: (word not in index.titles[url], url))
        yield f"word:{word}", choose_postings(ordered, encoded, rare=word in index.weight)
    for number, keys in numbers.items():
        yield f"number:{number}", choose_postings(sorted(keys), encoded)


def pack(prefix, items, files):
    payload = encode({"format": SHARD_FORMAT, "entries": {key: value for _, key, value in sorted(items)}})
    if len(payload) <= SHARD_LIMIT:
        files[prefix] = payload
        return
    if len(items) == 1 or len(prefix) == 64:
        raise ValueError("A public search entry exceeds its shard budget")
    children = defaultdict(list)
    for hashed, key, value in items:
        children[hashed[:len(prefix) + 1]].append((hashed, key, value))
    files[prefix] = encode({"format": SHARD_FORMAT, "children": sorted(child[-1] for child in children)})
    for child, group in children.items():
        pack(child, group, files)


def build_search_files(projects, observations):
    roots = defaultdict(list)
    for key, value in index_entries(projects, observations):
        hashed = digest(key)
        roots[hashed[:2]].append((hashed, key, value))
    files = {}
    for prefix, group in roots.items():
        pack(prefix, group, files)
    identity = sha256()
    for prefix, body in sorted(files.items()):
        identity.update(prefix.encode("ascii") + b":" + sha256(body).digest())
    generation = identity.hexdigest()[:24]
    return ({f"data/preflight-{generation}-{prefix}.json": content for prefix, content in files.items()}
            | {MANIFEST: encode({"version": 1, "generation": generation, "roots": sorted(roots)})})


class QueryBudget:
    def __init__(self):
        self.remaining = QUERY_READS
        self.deadline = monotonic() + QUERY_TIMEOUT


class SearchReader:
    """Read content from one manifest under a shared per-query request budget."""

    def __init__(self, manifest, fetch, budget=None):
        if (not isinstance(manifest, dict) or type(manifest.get("version")) is not int or manifest["version"] != 1
                or not re.fullmatch(r"[0-9a-f]{24}", str(manifest.get("generation", "")))
                or not isinstance(manifest.get("roots"), list) or len(manifest["roots"]) > 256
                or not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{2}", value)
                           for value in manifest["roots"])):
            raise ValueError("Unsupported PortBridge public search index")
        self.generation = manifest["generation"]
        self.roots = set(manifest["roots"])
        self.fetch = fetch
        self.shards = {}
        self.budget = budget if budget is not None else QueryBudget()
        self.truncated = False

    def load(self, prefix):
        payload = self.fetch(f"data/preflight-{self.generation}-{prefix}.json", SHARD_LIMIT,
                             max(0.1, min(6, self.budget.deadline - monotonic())))
        if not isinstance(payload, dict) or payload.get("format") != SHARD_FORMAT:
            raise ValueError("Invalid PortBridge public search shard")
        if set(payload) == {"format", "entries"} and isinstance(payload["entries"], dict):
            return payload
        children = payload.get("children")
        if (set(payload) != {"format", "children"} or len(prefix) >= 64 or not isinstance(children, list)
                or not all(isinstance(child, str) and re.fullmatch(r"[0-9a-f]", child) for child in children)):
            raise ValueError("Invalid PortBridge public search shard")
        return payload

    def find(self, keys):
        hashed = {key: digest(key) for key in keys}
        waiting = {key: value[:2] for key, value in hashed.items() if value[:2] in self.roots}
        found = {}
        while waiting:
            prefixes = list(dict.fromkeys(prefix for prefix in waiting.values() if prefix not in self.shards))
            requested = prefixes[:self.budget.remaining] if monotonic() < self.budget.deadline else []
            self.budget.remaining -= len(requested)
            if requested:
                with ThreadPoolExecutor(max_workers=LOOKUP_CONCURRENCY) as executor:
                    self.shards.update(zip(requested, executor.map(self.load, requested)))
            next_waiting = {}
            for key, prefix in waiting.items():
                payload = self.shards.get(prefix)
                if payload is None:
                    self.truncated = True
                    continue
                if "entries" in payload:
                    if key in payload["entries"]:
                        found[key] = payload["entries"][key]
                    continue
                next_char = hashed[key][len(prefix)]
                if next_char in payload["children"]:
                    next_waiting[key] = prefix + next_char
            waiting = next_waiting
        return found

    def select(self, *, anchor, query, number, problem):
        capsule = self.find([f"source:{anchor}"]).get(f"source:{anchor}") if anchor else None
        rows, matches, rare = {}, [], set()
        fallback = None
        if capsule is not None:
            rows[anchor] = capsule["row"]
            matches = capsule["matches"]
            rare = set(capsule["rare"])
        if number:
            keys = [f"number:{number}"]
        elif not query and capsule is not None:
            fallback = capsule["fallback"]
            keys = []
        elif not problem and len(matches) < 2:
            words = terms(query)
            if capsule is not None:
                row = capsule["row"]
                words |= terms(row["title"]) | set(row["metadata"]["technical"]["terms"])
            ordered = sorted(words, key=lambda word: (word in GENERAL_SOURCE_TERMS,
                                                        not bool(ISA_OPCODE.fullmatch(word)), word))
            self.truncated |= len(ordered) > QUERY_TERMS
            keys = [f"word:{word}" for word in ordered[:QUERY_TERMS]]
        else:
            keys = []
        for key, entry in self.find(keys).items():
            if entry["rare"]:
                rare.add(key.removeprefix("word:"))
            self.truncated |= entry["truncated"]
            for record in entry["rows"]:
                rows.setdefault(record["url"], record)
        return list(rows.values()), {"matches": matches, "rare": rare, "fallback": fallback}
