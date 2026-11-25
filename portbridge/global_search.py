"""Optional discovery in public GitHub issues and pull requests."""

from contextlib import closing
import re
import sqlite3
from urllib.parse import urlencode, urlsplit

from .catalog import public_url
from .github import API, API_SYMBOL, TECHNICAL_TERM, Unavailable, _Sync
from .matching import ISA_OPCODE, canonical_url


QUERY_PHRASES = re.compile(r"\b(?:scratch memory|scratch buffer|liveness|live ranges?|last consumer|"
                           r"last use|stack coloring|spill slots?|compute dispatch|shader compiler|"
                           r"timeline[\s-]+semaphores?|enhanced[\s-]+barriers?|"
                           r"image layout|(?:pipeline|image)[\s-]+barriers?|barrier(?:[\s-]+coalescing)|"
                           r"(?:texture[\s-]+)?detil(?:e|ing)|swizzl(?:e|ing)|gfx(?:10|11|12)|bc[1-7]|"
                           r"register allocation|memory aliasing|synchronization|scratch|lifetime|"
                           r"dxil|dxbc|spir-v|d3d12|vulkan)\b", re.I)
QUERY_ALIASES = {
    "timeline semaphore": "timeline semaphore", "timeline semaphores": "timeline semaphore",
    "enhanced barrier": "enhanced barriers", "enhanced barriers": "enhanced barriers",
    "pipeline barriers": "pipeline barrier", "image barriers": "image barrier",
    "texture detile": "detile", "texture detiling": "detile", "detiling": "detile",

}
CONTEXT_PHRASES = frozenset({"direct3d 12", "directx 12", "spir v"})
RESULT_PATH = re.compile(r"/[^/]+/[^/]+/(?:issues|pull)/[1-9][0-9]*")
MAX_RESULTS = 10
SCOPE = "public_github_issues_and_pull_requests"


def search_terms(text):
    """Send only selected technical words and symbols to the anonymous search endpoint."""
    terms = {}
    for group in (ISA_OPCODE, API_SYMBOL, QUERY_PHRASES, TECHNICAL_TERM):
        for match in group.findall(text):
            term = match.casefold()
            alias = " ".join(term.replace("-", " ").split())
            terms[QUERY_ALIASES.get(alias, term)] = None
    return list(terms)[:4]


def _title_pattern(term, *, topic=False):
    if topic:
        # Natural phrases can be hyphenated or plural in titles. Symbols stay literal.
        phrase = r"[-_\s]+".join(re.escape(word) for word in term.removesuffix("s").split())
        return re.compile(rf"(?<!\w){phrase}s?(?!\w)", re.I)
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.I)


def _rank_candidates(items, words):
    phrases = {word for word in words if " " in word and word not in CONTEXT_PHRASES}
    if not phrases:
        return
    topics = [_title_pattern(word, topic=True) for word in phrases]
    contexts = [_title_pattern(word) for word in words if word not in phrases]

    def title_score(item):
        title = item["title"]
        topic_count = sum(pattern.search(title) is not None for pattern in topics)
        context_count = sum(pattern.search(title) is not None for pattern in contexts) if topic_count else 0
        return topic_count, context_count

    # Preserve GitHub's order for ties, including body-only results.
    items.sort(key=title_score, reverse=True)


def result_entry(entry):
    if not isinstance(entry, dict):
        return None
    url, title = entry.get("html_url"), entry.get("title")
    if not isinstance(url, str) or not public_url(url) or not RESULT_PATH.fullmatch(urlsplit(url).path):
        return None
    if not isinstance(title, str) or not title.strip() or entry.get("state") not in ("open", "closed"):
        return None
    return {"url": url, "title": " ".join(title.split())[:300], "state": entry["state"],
            "observed_at": entry.get("updated_at") if isinstance(entry.get("updated_at"), str) else None,
            "kind": "pr" if "/pull/" in urlsplit(url).path else "issue", "match_level": "candidate"}


def external_search(query, *, excluded=()):
    words = search_terms(query)
    result = {"scope": SCOPE, "terms": words, "matches": [], "state": "query_needed",
              "limits": "GitHub returns a limited first page. Review the original context and license."}
    if not words:
        return result
    params = {"q": " ".join(f'"{word}"' for word in words) + " in:title,body", "per_page": MAX_RESULTS}
    try:
        with closing(sqlite3.connect(":memory:")) as db:
            client = _Sync(db, False, anonymous=True)
            response, _ = client._request(f"{API}/search/issues?{urlencode(params)}", "search", None)
    except Unavailable:
        return {**result, "state": "unavailable"}
    if not isinstance(response, dict) or not isinstance(response.get("items"), list):
        return {**result, "state": "unavailable"}
    seen = {canonical_url(url) for url in excluded if url}
    for raw in response["items"][:MAX_RESULTS]:
        item = result_entry(raw)
        if item is None:
            continue
        key = canonical_url(item["url"])
        if key not in seen:
            result["matches"].append(item)
            seen.add(key)
    _rank_candidates(result["matches"], words)
    result["state"] = "partial" if response.get("incomplete_results") else "available"
    return result


def append_external_results(result, records, *, q, url):
    # When no free-text terms were supplied, use only an exact public source's stored title.
    parent = canonical_url(url) if url and not urlsplit(url).fragment else ""
    source_title = next((row["title"] for row in records if parent and canonical_url(row["url"]) == parent), "")
    known = [url, *(row["right"]["url"] for row in result["matches"]), *(row["url"] for row in result["observations"])]
    result["external_search"] = external_search(q or source_title, excluded=known)
    return result
