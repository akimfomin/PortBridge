"""Run the frozen code retrieval holdout without GitHub writes or raw-body output."""

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("product", type=Path)
    parser.add_argument("database", type=Path)
    parser.add_argument("inputs", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.product.resolve()))
    github = importlib.import_module("portbridge.github")
    search = importlib.import_module("portbridge.code_search")
    catalog = importlib.import_module("portbridge.catalog")

    folder = Path(__file__).resolve().parent
    frozen = json.loads((folder / "holdout.json").read_bytes())
    inputs = json.loads(args.inputs.read_bytes())
    index = search.projection(catalog.ReadOnlyCatalog(args.database))
    output = []
    for label, issue in zip(frozen["cases"], inputs, strict=True):
        assert label["origin"] == issue["url"] and label["title"] == issue["title"]
        assert label["body_sha256"] == hashlib.sha256(issue["body"].encode()).hexdigest()
        row = {"title": issue["title"], "url": issue["url"], "kind": "issue",
               "metadata": {"technical": github._technical(issue, [], {})}}
        results = search.lookup(index, search.observation_query(row), origin_url=issue["url"], limit=5)
        hit = next((
            {"rank": rank, "line": found["line"], "url": found["url"]}
            for rank, found in enumerate(results, 1)
            for expected in label["sources"]
            if (found["repo"].casefold() == expected["repo"].casefold()
                and found["path"] == expected["path"] and found["revision"] == expected["revision"]
                and found["license"] == expected["license"]
                and expected["lines"][0] <= found["line"] <= expected["lines"][1])
        ), None)
        output.append({"origin": issue["url"], "grade": label["grade"], "hit": hit,
                       "candidates": [{"url": result["url"], "line": result["line"],
                                       "signals": result["signals"]} for result in results]})
    print(json.dumps({"index_files": len(index["files"]), "output": output}, indent=2))


if __name__ == "__main__":
    main()
