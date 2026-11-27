"""Bounded, source-pinned retrieval of external technical work."""

import argparse
from datetime import date
from functools import lru_cache
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .identity import stable_id
from .consoles import console_families
from .github import PR_URL
from .matching import REPOSITORY_MOVES, current_repository

DATA = Path(__file__).with_name("data") / "discovery.json"
MAX_ENTRIES = 128
MAX_QUERY = 200
MAX_RESULTS = 10
HOSTS = {"github.com", "gitlab.freedesktop.org"}
KINDS = {"implementation", "spec", "test", "diagnostic", "pr", "issue"}
STATES = {"reference", "open", "closed", "merged"}
TOKEN = re.compile(r"[a-zа-яё0-9]+(?:[_.:+-][a-zа-яё0-9]+)*", re.I)
SHA = re.compile(r"[a-f0-9]{40,64}", re.I)
SOURCE_FOUND = "source_found"
POTENTIAL = "potentially_applicable"
EVIDENCE_STAGES = (SOURCE_FOUND, POTENTIAL, "technically_verified", "reproducible_fix", "adopted_by_team")
STOP = set("the a an to for of at in on and or is was does are how do need which what one use"
           " from by as with into this that same different without when gpu cpu vulkan linux windows"
           " xbox series source data problem candidate pipeline cache shader buffer test code work state"
           " для где как что это с в на и или по".split())


def words(value):
    return TOKEN.findall(value.lower())


def key(url):
    if not isinstance(url, str):
        return ""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return ""
    if parsed.scheme != "https" or parsed.netloc.lower() not in HOSTS:
        return ""
    host, path = parsed.netloc.lower(), parsed.path.rstrip("/").lower()
    if host == "github.com":
        parts = path.split("/", 3)
        if len(parts) == 4 and not parts[0]:
            repo = current_repository("/".join(parts[1:3])).lower()
            path = f"/{repo}/{parts[3]}"
    return host + path


def query_key(url):
    normalized = key(url)
    if normalized and urlsplit(url).fragment.startswith(("issuecomment-", "discussion_r", "pullrequestreview-")):
        return ""
    return normalized


def features(value):
    return sorted(set(words(value)) - STOP)


@lru_cache(maxsize=1)
def discovery_index():
    raw = json.loads(DATA.read_bytes())
    russian = json.loads(DATA.with_suffix(".ru.json").read_bytes())
    if raw["schema_version"] != 1 or not 0 < len(raw["entries"]) <= MAX_ENTRIES:
        raise ValueError("Invalid Discovery corpus")
    rows = []
    for item in raw["entries"]:
        source = raw["sources"][item["project"]]
        if (not key(item["source"]).startswith(key(source["url"]) + "/") or not key(source["license_url"])
                or not SHA.fullmatch(source["revision"]) or item["kind"] not in KINDS or item["state"] not in STATES
                or not set(item["topics"]) <= raw["facets"].keys()):
            raise ValueError(f"Invalid source-pinned Discovery entry: {item['id']}")
        if not all(isinstance(item.get(field), str) and item[field].strip()
                   for field in ("title", "problem", "similarity", "differences", "limits", "adaptation", "test")):
            raise ValueError(f"Incomplete applicability metadata: {item['id']}")
        primary = features(f"{item['title']} {item['title_ru']}")
        symbols = features(" ".join(item["symbols"]))
        context = features(" ".join(item[field] for field in ("problem", "similarity", "adaptation")))
        rows.append({**item, "repository": source["name"], "repository_url": source["url"],
                     "consoles": console_families(source["url"]),
                     "translations": {"ru": russian[item["id"]]},
                     "revision": source["revision"], "license": source["license"], "license_url": source["license_url"],
                     "reviewed_on": raw["reviewed_at"][:10],
                     "features": {"title": primary, "symbols": symbols, "context": context}})
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate Discovery source ID")
    return {"schema_version": 1, "reviewed_on": raw["reviewed_at"][:10],
            "facets": raw["facets"], "entries": rows, "cases": raw["cases"],
            "repository_moves": {old.lower(): current.lower() for old, current in REPOSITORY_MOVES.items()}}


def date_filter(value):
    if not value:
        return ""
    try:
        if date.fromisoformat(value).isoformat() == value:
            return value
    except (TypeError, ValueError):
        pass
    raise ValueError("Use YYYY-MM-DD for a Discovery date filter")


def result_entry(row, score, matched_facets, matched_symbols, exact, reviewed_primary):
    eligible = row["id"] == reviewed_primary and row["state"] in {"reference", "merged"} and row["kind"] != "diagnostic"
    output = {name: value for name, value in row.items() if name != "features"}
    return {**output, "match_level": "candidate", "score": score,
            "evidence_status": POTENTIAL if eligible else SOURCE_FOUND,
            "match": {"exact": exact, "facets": sorted(matched_facets), "symbols": sorted(matched_symbols)}}


def empty_link_result(requested_url, scan_status, reason):
    """Describe what was actually searched when a source URL has no hits."""
    if scan_status == "available":
        return "no_match", "The reviewed index and saved GitHub search have no matching source in this scope."
    if scan_status == "no_subject":
        return scan_status, "No supported technical subject was found in the source metadata. No external search ran."
    if scan_status == "not_scanned":
        message = "There is no saved external search for this link."
        if PR_URL.fullmatch("https://" + requested_url):
            message += " To search this PR, run python -m portbridge.discovery_scan --online --url followed by its URL."
        return scan_status, message
    if scan_status == "partial":
        return scan_status, "GitHub returned an incomplete search page. Other matching sources may exist."
    if scan_status == "offline":
        return scan_status, "The search ran offline. No external sources were checked."
    if scan_status == "stale":
        return scan_status, "The saved search is out of date. A current match could not be confirmed."
    if reason == "snapshot_unavailable":
        return "unavailable", "The public Discovery snapshot is unavailable. Only the bundled reviewed index was searched."
    if scan_status == "rate_limit" or reason == "rate_limit":
        return "unavailable", "GitHub rate-limited the search. A matching source could not be checked."
    return "unavailable", "The external search could not be completed. A matching source could not be checked."


def discover(q="", *, origin_url="", index=None, project="", kind="", status="", platform="",
             before="", after="", limit=5, profile="hybrid"):
    if not isinstance(q, str) or len(q) > MAX_QUERY or type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
        raise ValueError("Use a Discovery query up to 200 characters and a limit from 1 to 10")
    if ((kind and kind not in KINDS) or (status and status not in STATES) or profile not in {"lexical", "hybrid"}
            or any(not isinstance(value, str) or len(value) > 100 for value in (project, platform))):
        raise ValueError("Invalid Discovery filter")
    before, after = date_filter(before), date_filter(after)
    if before and after and before < after:
        raise ValueError("Discovery end date precedes start date")
    index = index if index is not None else discovery_index()
    if (not isinstance(index, dict) or index.get("schema_version") != 1
            or not isinstance(index.get("entries"), list) or len(index["entries"]) > MAX_ENTRIES):
        raise ValueError("Invalid Discovery snapshot or entry count")
    if origin_url and (not isinstance(origin_url, str) or len(origin_url) > 500 or not key(origin_url)):
        raise ValueError("Use a public HTTPS source URL for Discovery")
    request = q.strip()
    requested_url = query_key(request) or query_key(origin_url)
    case = next((row for row in index["cases"] if key(row["origin_url"]) == requested_url), None)
    scans = index.get("automatic", {}).get(requested_url, {})
    query = (case["query"] if case else scans.get("subject", "")) if (not request or query_key(request)) else request
    reviewed_primary = (case["primary"] if case and case["state"] == "open" and case["verdict"] == "candidate"
                        and (not request or query_key(request) == requested_url or request == case["query"]) else None)
    query_words = set(features(query))
    phrase = f" {' '.join(words(query))} "
    topics = {name for name, aliases in index["facets"].items() if profile == "hybrid"
              and any(f" {' '.join(words(alias))} " in phrase for alias in aliases)}
    exact_sha = query.lower() if SHA.fullmatch(query) else ""
    matches = []
    for row in index["entries"]:
        if ((project and row["project"] != project.lower()) or (kind and row["kind"] != kind)
                or (status and row["state"] != status)
                or (platform and platform.lower() not in {name.lower() for name in row["platforms"]})
                or (before and row["reviewed_on"] > before) or (after and row["reviewed_on"] < after)):
            continue
        repo_key = key(row["repository_url"])
        commit_path = "/-/commit/" if repo_key.startswith("gitlab.freedesktop.org/") else "/commit/"
        exact = bool((requested_url and requested_url in {key(row["source"]), repo_key + commit_path + row["revision"]})
                     or request.lower() == row["id"]
                     or (exact_sha and row["revision"].lower() == exact_sha))
        matched_topics = topics & set(row["topics"])
        core = row["features"]
        matched_symbols = query_words.intersection(core["symbols"])
        title = query_words.intersection(core["title"])
        context = query_words.intersection(core["context"])
        useful = title | matched_symbols
        if not exact and not matched_topics and not (matched_symbols or len(useful | context) >= 2 and useful):
            continue
        score = (100 if exact else 0) + 12 * len(matched_topics) + 5 * len(matched_symbols) + 3 * len(title) + len(context)
        if case and row["id"] == case["primary"] and profile == "hybrid":
            score += 18
        matches.append(result_entry(row, score, matched_topics, matched_symbols, exact, reviewed_primary))
    matches.sort(key=lambda row: (not row["match"]["exact"], -row["score"], row["id"]))
    automatic = [row for row in scans.get("matches", [])
                 if (not project or row["project"] == project.lower())
                 and (not kind or row["kind"] == kind) and (not status or row["state"] == status)
                 and not platform and (not before or row["retrieved_on"] <= before)
                 and (not after or row["retrieved_on"] >= after)][:limit]
    scan_status = scans.get("status", "not_scanned")
    reason = scans.get("reason")
    result_status, empty_reason = "available", None
    if not matches and not automatic:
        if requested_url:
            result_status, empty_reason = empty_link_result(requested_url, scan_status, reason)
        else:
            result_status = "no_match" if query else "query_needed"
    return {"schema_version": 1, "reviewed_on": index["reviewed_on"],
            "target_consoles": console_families(origin_url or request,
                                default=("xbox-series",) if case else ()) ,
            "status": result_status,
            "scope": "reviewed_external_sources", "case": case, "matches": matches[:limit],
            "subject": scans.get("subject", ""),
            "empty_reason": empty_reason, "scan_reason": reason,
            "technical_recommendations": [row for row in matches[:limit] if row["evidence_status"] == POTENTIAL],
            "automatic_matches": automatic, "scan_status": scan_status,
            "evidence_stages": list(EVIDENCE_STAGES)}


def historical_candidates(report):
    """Expose evidence for Radar queueing, with no claim, test or adoption event."""
    origin = (report.get("case") or {}).get("origin_url")
    if origin is None:
        return []
    candidates = []
    for row in report["technical_recommendations"]:
        candidates.append({"id": stable_id("discovery", key(origin), row["id"]),
                           "entry_id": row["id"], "state": POTENTIAL, "origin_url": origin,
                           "source_url": row["source"], "revision": row["revision"], "license": row["license"],
                           "authors": row["authors"], "verification": row["test"]})
    return candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("q", "url", "project", "kind", "status", "platform", "before", "after"):
        parser.add_argument(f"--{name}", default="")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--db", type=Path, help="also read saved public Discovery finds from a local catalog")
    args = vars(parser.parse_args())
    try:
        db = args.pop("db")
        index = None
        if db is not None:
            from .catalog import ReadOnlyCatalog
            from .discovery_scan import cached_index
            if not db.is_file():
                raise ValueError("The local catalog is missing")
            origin = args["url"]
            index = cached_index(ReadOnlyCatalog(db), origin_urls=[origin] if query_key(origin) else [])
        result = discover(origin_url=args.pop("url"), index=index, **args)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
