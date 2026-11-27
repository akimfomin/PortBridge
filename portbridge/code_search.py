"""Build and query a bounded index of pinned, licensed public code."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from .discovery_terms import STORED_SYMBOL
from .matching import STOP_WORDS

MANIFEST = Path(__file__).with_name("data") / "code_sources.json"
SCHEMA_VERSION = 2
MAX_FILES = 32
MAX_BYTES = 1_200_000
MAX_INDEX_BYTES = 4_000_000
MAX_TERMS = 2800
POSITIONS = 16
WORD = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]{2,95}\b", re.ASCII)
SYMBOL = re.compile(r"(?:[a-z][A-Z]|[A-Za-z]_+[A-Za-z0-9])")
SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|_+")
QUOTED = re.compile(r"""(?:"[^"\r\n]*"|'[^'\r\n]*')""")
URL = re.compile(r"https?://[^\s<>()]+")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
PIN = re.compile(r"[0-9a-f]{40}")
PATH = re.compile(r"(?:[A-Za-z0-9_.+-]+/)*[A-Za-z0-9_.+-]+")
SHA256 = re.compile(r"[0-9a-f]{64}")
STOP = set("""the and for with return case this const void struct bool true false include null nullptr default insert
    set get add view_to image_view test tests source code file files log update support fix fixes after before when some
    version int uint enum value values pointer count size info flags flag format image device function context graphics
    resource resources uint32_t uint64_t size_t static inline define dxgi d3d12 vulkan spirv std name allow noerror
    type data pcreateinfo error graphicsapi vkd3d vk true false nullptr async result query implementation pipeline
    print handled docs input output index global shader compute games game series tests host target native
    are not non one can all out how has will else only""".split()) | STOP_WORDS
PRIVATE_TEXT = re.compile(r"(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|[A-Za-z]:\\[^\s`]+|\\\\[^\s`]+|/(?:home|Users)/[^\s`]+)")
API_NAME = re.compile(r"(?:D3D12_|DXGI_|VK_|VUID-|vk[A-Z]|ID3D12|GetDiskFreeSpace|GetVolumeInformation|GetFileInformation|SetFileInformation|Wave[A-Z]|EarlyCSE|SelectionDAG|[ds]s?_(?:read|write|add|cmp|load|store))")
SENSITIVE = re.compile(r"(?i)(?:password|secret|credential|api_?key|private_?key|access_?token|ghp_|github_pat_|AKIA|[A-F0-9]{24,})")
CACHE_PREFIX = f"deep-code-v{SCHEMA_VERSION}:"


def _path(value):
    return isinstance(value, str) and PATH.fullmatch(value) and not {"..", "."}.intersection(value.split("/"))


def references():
    manifest = json.loads(MANIFEST.read_bytes())
    seen = set()
    out = []
    for group in manifest:
        repo, revision, license_path = group["repo"], group["revision"], group["license_path"]
        if (not REPO.fullmatch(repo) or not _path(repo) or not PIN.fullmatch(revision)
                or not _path(license_path) or not group["license"]):
            raise ValueError("Invalid public code corpus entry")
        for path in group["files"]:
            if not _path(path) or (repo, path) in seen:
                raise ValueError("Invalid or duplicate code path")
            seen.add((repo, path))
            out.append({"repo": repo, "revision": revision, "path": path, "license": group["license"],
                        "license_url": f"https://github.com/{repo}/blob/{revision}/{license_path}"})
    if len(out) > MAX_FILES:
        raise ValueError("Public code corpus exceeds file budget")
    return out


def _key(reference):
    return "/".join(reference[name] for name in ("repo", "revision", "path"))


def _tokens(line):
    return [word for word in WORD.findall(line)
            if word.casefold() not in STOP and not SENSITIVE.search(word)]


def identifiers(text, *, public_only=False):
    """Keep exact public API-style names from otherwise untrusted issue text."""
    text = "\n".join(line for line in text[:33_500].splitlines() if not SENSITIVE.search(line))
    text = PRIVATE_TEXT.sub(" ", URL.sub(" ", text))
    return list(dict.fromkeys(word for word in _tokens(text)
                              if len(word) >= 5 and SYMBOL.search(word)
                              and (not public_only or API_NAME.match(word) or STORED_SYMBOL.fullmatch(word))))[:24]


def public_symbols(text):
    """Persist only code names from recognized public API or instruction families."""
    return identifiers(text, public_only=True)


def query_terms(text):
    tokens = _tokens(URL.sub(" ", text[:2000]))
    exact = set(word.casefold() for word in tokens)
    words = {part.casefold() for word in tokens for part in SPLIT.split(word)
             if len(part) >= 3 and part.casefold() not in STOP}
    technical = {word.casefold() for word in identifiers(text)}
    technical.update(word for word in exact if "_" in word or STORED_SYMBOL.fullmatch(word))
    if not technical and len(exact) == 1 and len(text.strip()) >= 4:
        technical = exact
    return technical, (exact | words) - technical


def observation_query(row):
    technical = row.get("metadata", {}).get("technical") or {}
    return row.get("title", "") + "\n" + " ".join([
        *technical.get("code_symbols", ()), *technical.get("discovery_cues", ()),
        *technical.get("signals", ()), *technical.get("terms", ())])


def _fetch(reference):
    from .github import NoRedirect
    address = "https://raw.githubusercontent.com/" + _key(reference)
    request = Request(address, headers={"User-Agent": "PortBridge-readonly-code-index"})
    with build_opener(NoRedirect).open(request, timeout=8) as response:
        return response.read(MAX_BYTES + 1)


def index_file(reference, content):
    if len(content) > MAX_BYTES or b"\0" in content:
        raise ValueError("Source is binary or exceeds the byte budget")
    # Publish searchable names and first line positions, with links to the source.
    # Retain neither source lines nor the original text or strings in implementation files.
    postings = defaultdict(list)
    qualified = set()
    for number, line in enumerate(content.decode("utf-8").splitlines(), start=1):
        if SENSITIVE.search(line):
            continue
        line = PRIVATE_TEXT.sub(" ", line)
        if not reference["path"].endswith((".adoc", ".rst", ".md", ".texi")):
            literals_removed = QUOTED.sub(" ", line)
        else:
            literals_removed = line
        words = _tokens(URL.sub(" ", literals_removed))
        qualified.update(word.casefold() for word in words if SYMBOL.search(word) and len(word) >= 5)
        features = {value.casefold() for word in words for value in (word, *SPLIT.split(word))
                    if len(value) >= 3 and value.casefold() not in STOP}
        for feature in features:
            if len(postings[feature]) < POSITIONS:
                postings[feature].append(number)
    # Favor technical names. Plain terms with a bounded number of occurrences
    # support co-occurrence when two implementations use different names.
    order = sorted(postings, key=lambda token: (token not in qualified, len(postings[token]), token))
    return {**reference, "sha256": sha256(content).hexdigest(),
            "terms": {token: postings[token] for token in order[:MAX_TERMS]}}


def projection(catalog):
    expected = {CACHE_PREFIX + _key(row): row for row in references()}
    with catalog.connect() as db:
        rows = db.execute("SELECT key,value FROM settings WHERE key GLOB ? ORDER BY key", (CACHE_PREFIX + "*",))
        files = []
        for key, payload in rows:
            if key not in expected:
                continue
            try:
                indexed = json.loads(payload)
            except ValueError:
                continue
            if _sensible(indexed) and _key(indexed) == _key(expected[key]):
                features = {word: positions for word, positions in indexed["terms"].items()
                            if WORD.fullmatch(word) and not SENSITIVE.search(word) and isinstance(positions, list)
                            and len(positions) <= POSITIONS
                            and all(type(line) is int and 0 < line < MAX_BYTES for line in positions)}
                files.append({**expected[key], "terms": features, "sha256": indexed["sha256"]})
    result = {"version": SCHEMA_VERSION, "expected_files": len(expected), "files": files}
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_INDEX_BYTES:
        raise ValueError("Public code index exceeds the client size limit")
    return result


def refresh(catalog, *, fetch=_fetch):
    sources = references()
    existing = {_key(row) for row in projection(catalog)["files"]}
    missing = [row for row in sources if _key(row) not in existing]

    def build(ref):
        try:
            return index_file(ref, fetch(ref)), None
        except (OSError, ValueError) as error:
            return ref, type(error).__name__

    errors, done = [], 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        with catalog.connect() as db:
            for row, error in pool.map(build, missing):
                if error:
                    errors.append({"path": _key(row), "reason": error})
                    continue
                db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)",
                           (CACHE_PREFIX + _key(row), json.dumps(row, separators=(",", ":"))))
                done += 1
            keys = [CACHE_PREFIX + _key(source) for source in sources]
            db.execute(f"DELETE FROM settings WHERE key GLOB ? AND key NOT IN ({','.join('?' for _ in keys)})",
                       ("deep-code-v*:*", *keys))
    return {"indexed": done, "cached": len(sources) - len(missing), "expected": len(sources), "errors": errors}


def _sensible(row):
    return (isinstance(row, dict) and isinstance(row.get("repo"), str) and REPO.fullmatch(row["repo"])
            and _path(row["repo"]) and _path(row.get("path")) and isinstance(row.get("revision"), str)
            and PIN.fullmatch(row["revision"]) and isinstance(row.get("license"), str)
            and isinstance(row.get("license_url"), str) and row["license_url"].startswith(
                f"https://github.com/{row['repo']}/blob/{row['revision']}/")
            and isinstance(row.get("terms"), dict) and len(row["terms"]) <= MAX_TERMS
            and isinstance(row.get("sha256"), str) and SHA256.fullmatch(row["sha256"]))


def lookup(index, query, *, origin_url="", limit=5):
    exact, words = query_terms(query)
    focus, _ = query_terms(query.split("\n", 1)[0])
    files = index.get("files", []) if index.get("version") == SCHEMA_VERSION else []
    files = [row for row in files[:MAX_FILES] if _sensible(row)]
    if not exact and len(words) < 3:
        return []
    owner = "/".join(urlsplit(origin_url).path.split("/")[1:3]).casefold()
    frequencies = Counter(token for row in files for token in (exact | words) & row["terms"].keys())
    results = []
    for row in files:
        if row["repo"].casefold() == owner:
            continue
        tokens = (exact | words) & row["terms"].keys()
        strong = exact & tokens
        if not strong and len(tokens) < 3:
            continue
        hit_lines = defaultdict(set)
        for token in tokens:
            positions = row["terms"][token]
            if isinstance(positions, list):
                for line in positions[:POSITIONS]:
                    if type(line) is int and 0 < line < MAX_BYTES:
                        hit_lines[line].add(token)
        if not hit_lines:
            continue
        ranked = []
        for line in sorted(hit_lines):
            nearby = set().union(*(hit_lines.get(n, ()) for n in range(max(1, line - 12), line + 13)))
            if not nearby & strong and len(nearby) < 3:
                continue
            score = sum((20 if token in focus else 7 if token in strong else 1)
                        + 1 / frequencies[token] for token in nearby)
            ranked.append((round(score, 4), len(hit_lines[line] & focus), len(hit_lines[line] & strong),
                           -line, sorted(nearby)))
        if not ranked:
            continue
        score, _, _, anchored, evidence = max(ranked)
        project, path, revision = row["repo"], row["path"], row["revision"]
        results.append({"url": f"https://github.com/{project}/blob/{revision}/{path}#L{-anchored}",
                        "path": path, "repo": project, "revision": revision, "line": -anchored,
                        "license": row["license"], "license_url": row["license_url"], "score": score,
                        "signals": evidence[:10], "evidence_status": "source_found",
                        "next_step": "Compare the cited lines and one opposite control in the target before adapting."})
    return sorted(results, key=lambda row: (-row["score"], row["url"]))[: max(1, min(limit, 10))]


def report(index, query, *, origin_url="", limit=5):
    matches = lookup(index, query, origin_url=origin_url, limit=limit)
    count = len(index.get("files", []))
    return {"status": "found" if matches else ("no_match" if count else "not_indexed"),
            "indexed_files": count, "expected_files": index.get("expected_files"), "matches": matches,
            "scope": "pinned_public_files", "confidence": "candidate"}


def main():
    from .__main__ import DEFAULT_DB, DEFAULT_SEED
    from .catalog import Catalog, ReadOnlyCatalog
    from .preflight import snapshot

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--q", default="")
    args = parser.parse_args()
    if args.refresh:
        result = refresh(Catalog(args.db or DEFAULT_DB, DEFAULT_SEED))
    elif args.q:
        try:
            index = projection(ReadOnlyCatalog(args.db)) if args.db else snapshot("source-code")
            result = report(index, args.q)
        except (OSError, ValueError):
            result = {"status": "unavailable", "matches": []}
    else:
        parser.error("Provide --refresh or --q")
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
