"""Re-evaluate frozen public issues against a prepared PortBridge code index."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from time import perf_counter
from urllib.request import Request, build_opener


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("product", type=Path)
    parser.add_argument("database", type=Path)
    parser.add_argument("suite", help="mixed, diagnostic, or an explicit frozen holdout JSON path")
    parser.add_argument("--research-db", type=Path, help="compare with the separate experimental source index")
    parser.add_argument("--inputs", type=Path, help="read previously fetched public issue inputs locally")
    args = parser.parse_args()
    sys.path.insert(0, str(args.product.resolve()))
    from portbridge.catalog import ReadOnlyCatalog
    from portbridge.code_search import lookup, observation_query, projection
    from portbridge.github import NoRedirect, _technical
    if args.research_db:
        from portbridge import code_research

    path = (Path(__file__).with_name(args.suite + "-holdout.json")
            if args.suite in {"mixed", "diagnostic"} else Path(args.suite))
    cases = json.loads(path.read_bytes())["cases"]
    saved = {row["url"]: row for row in json.loads(args.inputs.read_bytes())} if args.inputs else None
    index = projection(ReadOnlyCatalog(args.database))
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "PortBridge-frozen-holdout"}
    token = os.environ.get("PORTBRIDGE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    opener = build_opener(NoRedirect())
    results = []
    for case in cases:
        origin = case["origin"]
        source = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+)/issues/(\d+)", origin)
        if not source:
            raise ValueError("Unexpected origin in the frozen holdout")
        if saved is None:
            route = f"https://api.github.com/repos/{source[1]}/issues/{source[2]}"
            with opener.open(Request(route, headers=headers), timeout=15) as response:
                issue = json.loads(response.read(1_000_000))
        else:
            issue = saved[origin]
        body = issue.get("body") or ""
        if issue["title"] != case["title"] or sha256(body.encode()).hexdigest() != case["body_sha256"]:
            raise ValueError(f"Frozen input changed at {origin}")
        row = {"title": issue["title"], "url": origin, "kind": "issue",
               "metadata": {"technical": _technical({"title": issue["title"], "body": body}, [], {})}}
        query = observation_query(row)
        start = perf_counter()
        matches = lookup(index, query, origin_url=origin, limit=5)
        result = {"origin": origin, "grade": case["grade"], **grade(matches, case["sources"])}
        if args.research_db:
            baseline_ms = (perf_counter() - start) * 1000
            start = perf_counter()
            existing = {match["url"] for match in matches}
            extra = code_research.lookup(args.research_db, query, origin_url=origin, limit=5)
            extra = [match for match in extra if match["url"] not in existing]
            result["research"] = grade(extra, case["sources"])
            result["duration_ms"] = {"baseline": round(baseline_ms, 2),
                                     "research": round((perf_counter() - start) * 1000, 2)}
        results.append(result)
    print(json.dumps({"index_files": len(index["files"]), "output": results}, indent=2))


def grade(matches, sources):
    hit = next(({"rank": rank, "line": found["line"], "url": found["url"]}
                for rank, found in enumerate(matches, 1) for expected in sources
                if all(found[field] == expected[field] for field in ("path", "revision", "license"))
                and found["repo"].casefold() == expected["repo"].casefold()
                and expected["lines"][0] <= found["line"] <= expected["lines"][1]), None)
    return {"hit": hit, "candidates": [{field: match[field] for field in ("url", "line")} for match in matches]}


if __name__ == "__main__":
    main()
