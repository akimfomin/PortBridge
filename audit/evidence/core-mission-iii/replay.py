"""Re-evaluate frozen public issues against a prepared PortBridge code index."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from urllib.request import Request, build_opener


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("product", type=Path)
    parser.add_argument("database", type=Path)
    parser.add_argument("suite", choices=("mixed", "diagnostic"))
    args = parser.parse_args()
    sys.path.insert(0, str(args.product.resolve()))
    from portbridge.catalog import ReadOnlyCatalog
    from portbridge.code_search import lookup, observation_query, projection
    from portbridge.github import NoRedirect, _technical

    path = Path(__file__).with_name(args.suite + "-holdout.json")
    cases = json.loads(path.read_bytes())["cases"]
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
        route = f"https://api.github.com/repos/{source[1]}/issues/{source[2]}"
        with opener.open(Request(route, headers=headers), timeout=15) as response:
            issue = json.loads(response.read(1_000_000))
        body = issue.get("body") or ""
        if issue["title"] != case["title"] or sha256(body.encode()).hexdigest() != case["body_sha256"]:
            raise ValueError(f"Frozen input changed at {origin}")
        row = {"title": issue["title"], "url": origin, "kind": "issue",
               "metadata": {"technical": _technical({"title": issue["title"], "body": body}, [], {})}}
        matches = lookup(index, observation_query(row), origin_url=origin, limit=5)
        hit = next(({"rank": rank, "line": found["line"], "url": found["url"]}
                    for rank, found in enumerate(matches, 1) for expected in case["sources"]
                    if all(found[field] == expected[field] for field in ("path", "revision", "license"))
                    and found["repo"].casefold() == expected["repo"].casefold()
                    and expected["lines"][0] <= found["line"] <= expected["lines"][1]), None)
        results.append({"origin": origin, "grade": case["grade"], "hit": hit,
                        "candidates": [{field: match[field] for field in ("url", "line")} for match in matches]})
    print(json.dumps({"index_files": len(index["files"]), "output": results}, indent=2))


if __name__ == "__main__":
    main()
