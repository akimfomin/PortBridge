"""Replay the frozen public origins against either PortBridge checkout."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True, help="Local public PR JSON, keyed by URL")
    args = parser.parse_args()

    sys.path.insert(0, str(args.code.resolve()))
    from portbridge.github import _technical
    from portbridge.matching import RelatedIndex, canonical_url

    selection, labels = read(args.selection), read(args.labels)
    if hashlib.sha256(args.selection.read_bytes()).hexdigest() != labels["origin_file_sha256"]:
        raise SystemExit("The selected origins do not match the independent labels")
    grades = {case["url"]: case for case in labels["cases"]}
    corpus = read(args.corpus)["observations"]
    inputs = read(args.inputs)
    repo_names = {case["repo"].lower(): case["repo"] for case in selection["origins"]}
    for entry in corpus:
        repository = "/".join(entry["url"].split("/")[3:5])
        repo_names.setdefault(repository.lower(), repository)
    rows = {canonical_url(item["url"]): item for item in corpus}
    repo_projects = {"/".join(url.split("/")[3:5]): row["project"] for url, row in rows.items()}
    accepted = set()
    for case in selection["origins"]:
        url = case["url"]
        raw = inputs.get(url)
        item = canonical_url(url)
        old = rows.pop(item, None)
        if not (raw and raw["head_sha"] == case["head_sha"] and raw["title"] == case["title"]
                and hashlib.sha256(raw["body"].encode()).hexdigest() == case["body_sha256"]):
            continue
        metadata = {**(old or {}).get("metadata", {}), "head_sha": case["head_sha"],
                    "technical": _technical(raw, [], repo_names), "draft": False}
        rows[item] = {"url": url, "kind": "pr", "title": raw["title"], "metadata": metadata,
                      "project": repo_projects.get("/".join(item.split("/")[3:5]), case["repo"].lower()),
                      "status": "open" if raw["state"] == "open" else ("merged" if raw["merged"] else "closed"),
                      "updated_at": case["updated_at"]}
        accepted.add(url)
    index = RelatedIndex(rows.values())
    results, totals = [], Counter()
    for case in selection["origins"]:
        url = case["url"]
        origin = canonical_url(url)
        grade = grades[url]
        row = {"url": url, "grade": grade["grade"]}
        if url not in accepted or origin not in index.rows:
            totals["unavailable"] += 1
            results.append({**row, "status": "pin_unavailable", "top5": []})
            continue
        results_page = sorted(index.candidates(origin), key=lambda entry: (-entry[1], entry[0]))[:5]
        alternatives = {canonical_url(source) for source in grade.get("sources", [])}
        page = [{"url": index.rows[other]["url"], "basis": basis, "signals": signals, "score": round(score, 4)}
                for other, score, basis, signals in results_page]
        hits = sum(canonical_url(result["url"]) in alternatives for result in page)
        totals["ran"] += 1
        totals["with_leads"] += bool(page)
        totals["links"] += len(page)
        if grade["grade"] in {"positive_external", "verified_author_hint"}:
            totals[grade["grade"] + "_available"] += 1
            totals[grade["grade"] + "_hit"] += bool(hits)
        if grade["grade"] == "documented_negative_control":
            totals["negative_available"] += 1
            totals["negative_with_leads"] += bool(page)
        results.append({**row, "status": "replayed", "top5": page, "expected_links_seen": hits})
    print(json.dumps({"indexed": len(index.rows), "totals": totals, "cases": results}, indent=2))


if __name__ == "__main__":
    main()
