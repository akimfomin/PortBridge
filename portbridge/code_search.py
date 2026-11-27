"""Build and query a bounded index of pinned, licensed public code."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha1, sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from . import source_corpus
from .discovery_terms import STORED_SYMBOL
from .matching import STOP_WORDS, current_repository

MANIFEST = Path(__file__).with_name("data") / "code_sources.json"
SCHEMA_VERSION = 2
MAX_FILES = 96
MAX_BYTES = 1_200_000
MAX_INDEX_BYTES = 4_000_000
MAX_TERMS = 2800
POSITIONS = 16
WORD = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]{2,95}\b", re.ASCII)
SYMBOL = re.compile(r"(?:[a-z][A-Z]|[A-Za-z]_+[A-Za-z0-9])")
SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|_+")
# GLSL fixtures can be assembled from C or C++ string literals.
GLSL_BUILTIN = re.compile(
    r"\bgl_(?:NumSubgroups|Subgroup(?:Size|ID|InvocationID|EqMask|GeMask|GtMask|LeMask|LtMask)"
    r"|GlobalInvocationID|LocalInvocation(?:ID|Index)|NumWorkGroups|WorkGroupSize)\b"
)
QUOTED = re.compile(r"""(?:"[^"\r\n]*"|'[^'\r\n]*')""")
C_SOURCE_SEGMENTS = re.compile(
    r'''"(?:\\.|[^"\\\r\n])*"|'(?:\\.|[^'\\\r\n])*'|(?P<comment>//[^\r\n]*|/\*.*?(?:\*/|\Z))''',
    re.S,
)
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
CACHE_PREFIX = "deep-code-v11:"
ANCHOR_PREFIX = "pb_decl_"
REFPAGE_PREFIX = "pb_ref_"
ANCHOR_PREFIXES = (ANCHOR_PREFIX, REFPAGE_PREFIX)
PERFORMANCE_TITLE = re.compile(r"\b(?:latency|stutters?|performance|frametime|throughput|fps|slow(?:down|er)?|"
                               r"hangs?|freezes?|regression)\b", re.I)
VUID_PREFIX = "pb_vuid_"
GENERIC_STATUS = re.compile(r"(?:vk_error_|dxgi_error_|e_(?:fail|invalidarg|outofmemory)$)")
VUID = re.compile(r"\bVUID-(?:[A-Za-z0-9_]{1,54}-){2,3}[0-9]{5}\b", re.I)
DOC_DEFINITION = re.compile(r"^\s*[*+-]\s+(?:ename|flink|sname):([A-Za-z_][A-Za-z_0-9]+)\b")
DOC_REFPAGE = re.compile(r"""^\[open,\s*refpage=(?P<quote>['"])(?P<name>[A-Za-z_][A-Za-z_0-9]+)(?P=quote)(?:,[^\]\r\n]*)?\]\s*$""")
DOC_OPAQUE_BLOCK = re.compile(r"([-./+])\1{3,}")
CODE_SIGNATURE = re.compile(
    r"^\s*(?!(?:return|if|else|while|for|case|match|throw|await|new)\b)"
    r"(?:[A-Za-z_][\w:<>&*]*\s+)+([A-Za-z_][A-Za-z_0-9]+)\s*\("
)


def definition_token(word):
    return ANCHOR_PREFIX + word.casefold()


def _path(value):
    return isinstance(value, str) and PATH.fullmatch(value) and not {"..", "."}.intersection(value.split("/"))


def _manifest():
    groups = json.loads(MANIFEST.read_bytes())
    size = 0
    for group in groups:
        repo, revision, license_path = group["repo"], group["revision"], group["license_path"]
        if (not REPO.fullmatch(repo) or not _path(repo) or not PIN.fullmatch(revision)
                or not _path(license_path) or not group["license"]):
            raise ValueError("Invalid public code corpus entry")
        size += len(group["files"])
        if "directories" in group:
            if (not group["directories"] or not all(_path(path) for path in group["directories"])
                    or type(group["limit"]) is not int or not 1 <= group["limit"] <= source_corpus.MAX_SELECTED):
                raise ValueError("Invalid public source scope")
            size += group["limit"]
    if size > MAX_FILES:
        raise ValueError("Public code corpus exceeds file budget")
    return groups



def _scope_rows(group, rows):
    if not isinstance(rows, list) or not 0 < len(rows) <= group["limit"]:
        return []
    paths = set()
    for row in rows:
        if (not isinstance(row, dict) or not source_corpus.valid_file(group, row.get("path"))
                or not isinstance(row.get("blob"), str) or not PIN.fullmatch(row["blob"])
                or row["path"] in paths):
            return []
        paths.add(row["path"])
    return rows


def references(catalog=None):
    groups = _manifest()
    selections = {}
    if catalog:
        with catalog.connect() as db:
            for key, payload in db.execute("SELECT key,value FROM settings WHERE key GLOB ?",
                                           (source_corpus.CACHE + "*",)):
                try:
                    selections[key] = json.loads(payload)
                except ValueError:
                    continue
    seen = set()
    out = []
    for group in groups:
        repo, revision = group["repo"], group["revision"]
        rows = [{"path": path} for path in group["files"]]
        if "directories" in group:
            rows.extend(_scope_rows(group, selections.get(source_corpus.cache_key(group))))
        for entry in rows:
            path = entry["path"]
            if not _path(path) or (repo, path) in seen:
                raise ValueError("Invalid or duplicate code path")
            seen.add((repo, path))
            out.append({**entry, "repo": repo, "revision": revision, "license": group["license"],
                        "license_url": f"https://github.com/{repo}/blob/{revision}/{group['license_path']}"})
    return out


def _discover_scopes(catalog, tree_fetch):
    groups = _manifest()
    scopes = [group for group in groups if "directories" in group]
    fixed = {(group["repo"], path) for group in groups for path in group["files"]}
    errors, downloads = [], 0
    for group in scopes:
        key = source_corpus.cache_key(group)
        with catalog.connect() as db:
            known = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if known:
            try:
                if _scope_rows(group, json.loads(known[0])):
                    continue
            except ValueError:
                pass
        try:
            downloads += 1
            selection = source_corpus.select({**group, "already_indexed": [
                path for repo, path in fixed if repo == group["repo"]]}, tree_fetch(group))
            if not _scope_rows(group, selection):
                raise ValueError("Approved source scope yielded no indexable files")
        except (OSError, ValueError) as error:
            errors.append({"scope": group["repo"], "reason": type(error).__name__})
            continue
        with catalog.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(selection)))
    return downloads, errors


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
                              and (not public_only or API_NAME.match(word) or STORED_SYMBOL.fullmatch(word)
                                   or GLSL_BUILTIN.fullmatch(word))))[:24]


def public_symbols(text):
    """Persist only code names from recognized public API or instruction families."""
    return identifiers(text, public_only=True)


def public_diagnostics(text):
    sanitized = URL.sub(" ", PRIVATE_TEXT.sub(" ", text[:33_500]))
    return list(dict.fromkeys(match[0].casefold() for match in VUID.finditer(sanitized)))[:16]


def diagnostic_token(identifier):
    return VUID_PREFIX + identifier.casefold().replace("-", "_")


def query_terms(text):
    tokens = _tokens(VUID.sub(" ", URL.sub(" ", text[:2000])))
    exact = set(word.casefold() for word in tokens)
    words = {part.casefold() for word in tokens for part in SPLIT.split(word)
             if len(part) >= 3 and part.casefold() not in STOP}
    technical = {word.casefold() for word in identifiers(VUID.sub(" ", text))}
    technical.update(word for word in exact if "_" in word or STORED_SYMBOL.fullmatch(word))
    technical.update(diagnostic_token(vuid) for vuid in public_diagnostics(text))
    if not technical and len(exact) == 1 and len(text.strip()) >= 4:
        technical = exact
    return technical, (exact | words) - technical


def observation_query(row):
    technical = row.get("metadata", {}).get("technical") or {}
    return row.get("title", "") + "\n" + " ".join([
        *technical.get("code_symbols", ()), *technical.get("discovery_cues", ()),
        *technical.get("code_diagnostics", ()), *technical.get("signals", ()), *technical.get("terms", ())])


def _fetch(reference):
    from .github import NoRedirect
    address = "https://raw.githubusercontent.com/" + _key(reference)
    request = Request(address, headers={"User-Agent": "PortBridge-readonly-code-index"})
    with build_opener(NoRedirect).open(request, timeout=8) as response:
        return response.read(MAX_BYTES + 1)


def index_file(reference, content):
    if blob := reference.get("blob"):
        if sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest() != blob:
            raise ValueError("Source bytes do not match their Git blob")
    if len(content) > MAX_BYTES or b"\0" in content:
        raise ValueError("Source is binary or exceeds the byte budget")
    # Publish searchable names and first line positions, with links to the source.
    # Retain neither source lines nor the original text or strings in implementation files.
    postings = defaultdict(list)
    qualified = set()
    docs = reference["path"].endswith((".adoc", ".rst", ".md", ".texi"))
    source = content.decode("utf-8")
    shader_names = {}
    c_source = reference["path"].endswith((".c", ".cpp", ".h", ".hpp"))
    if c_source and GLSL_BUILTIN.search(source):
        active = C_SOURCE_SEGMENTS.sub(lambda match: re.sub(r"[^\r\n]", " ", match[0])
                                       if match["comment"] else match[0], source)
        shader_names = {number: builtins for number, line in enumerate(active.splitlines(), start=1)
                        if (builtins := GLSL_BUILTIN.findall(URL.sub(" ", line)))}
    lines = source.splitlines()
    asciidoc = reference["path"].endswith(".adoc")
    opaque_fence = None
    for number, line in enumerate(lines, start=1):
        if asciidoc and DOC_OPAQUE_BLOCK.fullmatch(line.strip()):
            if opaque_fence is None:
                opaque_fence = line.strip()
            elif opaque_fence == line.strip():
                opaque_fence = None
        if SENSITIVE.search(line):
            continue
        line = PRIVATE_TEXT.sub(" ", line)
        if not docs:
            literals_removed = QUOTED.sub(" ", line)
        else:
            literals_removed = line
        words = _tokens(URL.sub(" ", literals_removed))
        if c_source:
            words = [word for word in words if not GLSL_BUILTIN.fullmatch(word)]
            words.extend(shader_names.get(number, ()))
        qualified.update(word.casefold() for word in words if SYMBOL.search(word) and len(word) >= 5)
        features = {value.casefold() for word in words for value in (word, *SPLIT.split(word))
                    if len(value) >= 3 and value.casefold() not in STOP}
        declaration = (DOC_DEFINITION if docs else CODE_SIGNATURE).match(literals_removed[:512])
        refpage = (DOC_REFPAGE.fullmatch(literals_removed) if asciidoc and opaque_fence is None
                   and number < len(lines) and lines[number].strip() == "--" else None)
        if declaration or refpage:
            name = refpage["name"] if refpage else declaration[1]
            if name in words and len(name) <= 84:
                marker = REFPAGE_PREFIX + name.casefold() if refpage else definition_token(name)
                features.add(marker)
                qualified.add(marker)
        diagnostics = {diagnostic_token(vuid) for vuid in public_diagnostics(line) if len(vuid) <= 87}
        features.update(diagnostics)
        qualified.update(diagnostics)
        for feature in features:
            if len(postings[feature]) < POSITIONS:
                postings[feature].append(number)
    # Favor technical names. Plain terms with a bounded number of occurrences
    # support co-occurrence when two implementations use different names.
    order = sorted(postings, key=lambda token: (not token.startswith(VUID_PREFIX),
                                                not token.startswith(ANCHOR_PREFIXES), token not in qualified,
                                                len(postings[token]), token))
    return {**reference, "sha256": sha256(content).hexdigest(),
            "terms": {token: postings[token] for token in order[:MAX_TERMS]}}


def projection(catalog):
    expected = {CACHE_PREFIX + _key(row): row for row in references(catalog)}
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
            if (_sensible(indexed) and _key(indexed) == _key(expected[key])
                    and indexed.get("blob") == expected[key].get("blob")):
                features = {word: positions for word, positions in indexed["terms"].items()
                            if WORD.fullmatch(word) and not SENSITIVE.search(word) and isinstance(positions, list)
                            and len(positions) <= POSITIONS
                            and all(type(line) is int and 0 < line < MAX_BYTES for line in positions)}
                files.append({**expected[key], "terms": features, "sha256": indexed["sha256"]})
    # Existing clients read only a prefix of the v2 format.
    files.sort(key=lambda row: ("blob" in row, row["repo"].casefold(), row["path"]))
    result = {"version": SCHEMA_VERSION, "diagnostics": True, "expected_files": len(expected), "files": files}
    if len(snapshot_bytes(result)) > MAX_INDEX_BYTES:
        # Small references keep all their postings. Their unused share goes
        # to larger references, with diagnostics and definitions retained first.
        sizes = sorted((len(snapshot_bytes(row)), index) for index, row in enumerate(files))
        remaining = MAX_INDEX_BYTES - 4096
        for offset, (size, index) in enumerate(sizes):
            share = remaining // (len(sizes) - offset)
            if size > share:
                trim_postings(files[index], share)
                size = len(snapshot_bytes(files[index]))
            remaining -= size
        if len(snapshot_bytes(result)) > MAX_INDEX_BYTES:
            raise ValueError("Public code index exceeds the client size limit")
    return result



def snapshot_bytes(index):
    return json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def trim_postings(row, budget):
    terms = row["terms"]
    row["terms"] = {}
    remaining = budget - len(snapshot_bytes(row))
    for token, positions in terms.items():
        remaining -= len(snapshot_bytes({token: positions})) - 1
        if remaining < 0:
            break
        row["terms"][token] = positions


def refresh(catalog, *, fetch=_fetch, tree_fetch=source_corpus.fetch_tree):
    # Custom file fetchers can replay pinned sources without network tree discovery.
    with_tree = fetch is _fetch or tree_fetch is not source_corpus.fetch_tree
    tree_reads, errors = _discover_scopes(catalog, tree_fetch) if with_tree else (0, [])
    sources = references(catalog)
    existing = {_key(row) for row in projection(catalog)["files"]}
    missing = [row for row in sources if _key(row) not in existing]

    previous = {}
    with catalog.connect() as db:
        for (payload,) in db.execute("SELECT value FROM settings WHERE key GLOB ?", (CACHE_PREFIX + "*",)):
            try:
                cached = json.loads(payload)
            except ValueError:
                continue
            if _sensible(cached) and cached.get("blob"):
                previous[(cached["repo"], cached["path"], cached["blob"])] = cached

    def build(ref):
        key = (ref["repo"], ref["path"], ref.get("blob"))
        if key in previous:
            return {**previous[key], **ref}, None, True
        try:
            return index_file(ref, fetch(ref)), None, False
        except (OSError, ValueError) as error:
            return ref, type(error).__name__, False

    done = reused = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        with catalog.connect() as db:
            for row, error, from_blob in pool.map(build, missing):
                if error:
                    errors.append({"path": _key(row), "reason": error})
                    continue
                db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)",
                           (CACHE_PREFIX + _key(row), json.dumps(row, separators=(",", ":"))))
                reused += int(from_blob)
                done += int(not from_blob)
            keys = [CACHE_PREFIX + _key(source) for source in sources]
            db.execute(f"DELETE FROM settings WHERE key GLOB ? AND key NOT IN ({','.join('?' for _ in keys)})",
                       ("deep-code-v*:*", *keys))
    return {"indexed": done, "cached": len(sources) - len(missing), "reused_blobs": reused,
            "expected": len(sources), "tree_reads": tree_reads, "errors": errors}


def _sensible(row):
    return (isinstance(row, dict) and isinstance(row.get("repo"), str) and REPO.fullmatch(row["repo"])
            and _path(row["repo"]) and _path(row.get("path")) and isinstance(row.get("revision"), str)
            and PIN.fullmatch(row["revision"]) and isinstance(row.get("license"), str)
            and isinstance(row.get("license_url"), str) and row["license_url"].startswith(
                f"https://github.com/{row['repo']}/blob/{row['revision']}/")
            and (row.get("blob") is None or isinstance(row["blob"], str) and PIN.fullmatch(row["blob"]))
            and isinstance(row.get("terms"), dict) and len(row["terms"]) <= MAX_TERMS
            and isinstance(row.get("sha256"), str) and SHA256.fullmatch(row["sha256"]))


def lookup(index, query, *, origin_url="", limit=5):
    exact, words = query_terms(query)
    focus, _ = query_terms(query.split("\n", 1)[0])
    files = index.get("files", []) if index.get("version") == SCHEMA_VERSION else []
    files = [row for row in files[:MAX_FILES] if _sensible(row)]
    if not exact and len(words) < 3:
        return []
    owner = current_repository("/".join(urlsplit(origin_url).path.split("/")[1:3])).casefold()
    files = [row for row in files if current_repository(row["repo"]).casefold() != owner]
    diagnostics = {word for word in exact if word.startswith(VUID_PREFIX)}
    diagnostic_files = [row for row in files if diagnostics & row["terms"].keys()]
    performance = PERFORMANCE_TITLE.search(query.split("\n", 1)[0])
    builtins = set() if performance else {name.casefold() for name in GLSL_BUILTIN.findall(query[:2000])}
    if diagnostic_files:
        files = [row for row in files if diagnostics & row["terms"].keys()
                 or len(builtins & row["terms"].keys()) >= 2]
    diagnostic_fallback = bool(diagnostics and not diagnostic_files)
    corroboration = {word for word in exact - diagnostics if not GENERIC_STATUS.match(word)}
    definitions = {definition_token(word) for word in corroboration}
    definitions.update(REFPAGE_PREFIX + word for word in corroboration & focus)
    frequencies = Counter(token for row in files for token in (exact | words) & row["terms"].keys())
    results = []
    for row in files:
        tokens = (exact | words) & row["terms"].keys()
        strong = exact & tokens
        if not strong and (diagnostic_fallback or len(tokens) < 3):
            continue
        hit_lines = defaultdict(set)
        row_definitions = definitions & row["terms"].keys()
        for token in tokens | row_definitions:
            positions = row["terms"][token]
            if isinstance(positions, list):
                for line in positions[:POSITIONS]:
                    if type(line) is int and 0 < line < MAX_BYTES:
                        hit_lines[line].add(token)
        if not hit_lines:
            continue
        ranked = []
        for line in sorted(hit_lines):
            diagnostic = len(hit_lines[line] & diagnostics)
            if diagnostic_files and not diagnostic and len(hit_lines[line] & builtins) < 2:
                continue
            nearby = set().union(*(hit_lines.get(n, ()) for n in range(max(1, line - 12), line + 13)))
            nearby.difference_update(definitions)
            declaration = len(hit_lines[line] & row_definitions)
            # A search linked to an issue needs evidence beyond shared words.
            # A single API definition cannot explain a timing or stability regression.
            if origin_url and not diagnostic:
                supported = len(nearby & corroboration) >= 2
                if performance:
                    supported = supported and bool(declaration)
                if not (supported or declaration and not performance):
                    continue
            if not nearby & strong and len(nearby) < 3:
                continue
            score = sum((20 if token in focus else 7 if token in strong else 1)
                        + 1 / frequencies[token] for token in nearby)
            ranked.append((diagnostic, round(score + 25 * declaration + 80 * diagnostic, 4), declaration,
                           len(hit_lines[line] & focus), len(hit_lines[line] & strong),
                           -line, sorted(nearby)))
        if not ranked:
            continue
        diagnostic, score, _, _, _, anchored, evidence = max(ranked)
        project, path, revision = row["repo"], row["path"], row["revision"]
        results.append((bool(diagnostic), {"url": f"https://github.com/{project}/blob/{revision}/{path}#L{-anchored}",
                        "path": path, "repo": project, "revision": revision, "line": -anchored,
                        "license": row["license"], "license_url": row["license_url"], "score": score,
                        "signals": [token[len(VUID_PREFIX):].replace("_", "-")
                                    if token.startswith(VUID_PREFIX) else token for token in evidence[:10]], "evidence_status": "source_found",
                        "next_step": ("The diagnostic ID was not found. Check the rule separately before using this API lead."
                                      if diagnostic_fallback else
                                      "Compare the cited lines and one opposite control in the target before adapting.")}))
    ranked_results = sorted(results, key=lambda item: (not item[0], -item[1]["score"], item[1]["url"]))
    return [row for _, row in ranked_results[:max(1, min(limit, 10))]]


def report(index, query, *, origin_url="", limit=5):
    matches = lookup(index, query, origin_url=origin_url, limit=limit)
    count = len(index.get("files", []))
    return {"status": "found" if matches else ("no_match" if count else "not_indexed"),
            "indexed_files": count, "expected_files": index.get("expected_files"), "matches": matches,
            "scope": "pinned_public_files", "confidence": "candidate"}



def browser_matches(index, observations):
    """Project compact source candidates for recently updated public links."""
    from .discovery_search import query_key

    if not index.get("files"):
        return {}, 0
    candidates = {}
    recent = sorted(observations, key=lambda row: row.get("updated_at") or "", reverse=True)
    for row in recent:
        if row.get("kind") not in {"pr", "issue"}:
            continue
        url = row.get("url") or ""
        key = query_key(url)
        if not key or key in candidates:
            continue
        hits = lookup(index, observation_query(row), origin_url=url, limit=2)
        candidates[key] = [{name: hit[name] for name in ("url", "path", "line", "license", "license_url", "next_step")}
                           for hit in hits]
        if len(candidates) >= 96:
            break
    return {key: hits for key, hits in candidates.items() if hits}, len(candidates)


def main():
    from .__main__ import DEFAULT_DB, DEFAULT_SEED
    from .catalog import Catalog, ReadOnlyCatalog
    from .preflight import snapshot

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--q", default="")
    parser.add_argument("--require-complete", action="store_true", help="fail on any source refresh error")
    args = parser.parse_args()
    if args.require_complete and not args.refresh:
        parser.error("--require-complete requires --refresh")
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
    return int(args.require_complete and bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
