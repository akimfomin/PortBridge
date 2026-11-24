"""Write advisory PortBridge results to a GitHub Actions job summary."""

import json
import os
from pathlib import Path
import re
import string
from urllib.parse import quote

from .catalog import PROBLEM_ID, public_url
from .github import PR_URL
from .preflight import PUBLIC_BASE, public_preflight


EVENT_LIMIT = 4 * 1024 * 1024
ESCAPE_MARKDOWN = str.maketrans({char: f"&#{ord(char)};" for char in string.punctuation})
HEADER = "## PortBridge prior-work summary\n\n"
UNAVAILABLE = "The public catalog is unavailable. Continue the usual review.\n"


def pull_request(event_path):
    with Path(event_path).open("rb") as stream:
        data = stream.read(EVENT_LIMIT + 1)
    if len(data) > EVENT_LIMIT:
        raise ValueError("GitHub event exceeds size limit")
    request = json.loads(data)["pull_request"]
    title, source = request["title"], request["html_url"]
    if not isinstance(title, str) or not isinstance(source, str) or not PR_URL.fullmatch(source):
        raise ValueError("Invalid pull request data")
    return {"q": " ".join(title.split())[:400], "url": source}


def label(text):
    return " ".join("".join(char for char in text[:320] if char.isprintable() or char.isspace()).split()).translate(
        ESCAPE_MARKDOWN
    )


def source_link(title, url):
    if not public_url(url) or len(url) > 500:
        return None
    destination = quote(url, safe=":/?#&=%+@-._~")
    return f"[{label(title)}]({destination})"


def source_group(heading, items):
    rows = []
    for item in items[:5]:
        link = source_link(item["title"], item["url"])
        if link:
            rows.append(f"- {link}")
    return [f"### {heading}", "", *rows, ""] if rows else []


def render_report(result):
    lines = ["Review these leads against the target revision and configuration.", ""]
    if result.get("catalog_status") in {"partial", "stale", "error", "seed-only"}:
        lines.extend(["The public snapshot may be incomplete.", ""])
    if result.get("origin_url") and result.get("indexed") is False:
        lines.extend(["This pull request is absent from the public index. Check its current details on GitHub.", ""])
    for source in result.get("source_coverage", []):
        repo = label(source.get("repo", source["slug"]))
        for mode, health in source["history"].items():
            if health["status"] != "complete":
                lines.append(f"- {repo} · {label(mode)} history: {label(health['status'])}")
        if source.get("freshness") in {"partial", "stale", "error"}:
            lines.append(f"- {repo} · recent sources: {label(source['freshness'])}")
            for kind, state in source.get("kinds", {}).items():
                if state["sync_status"] != "ok":
                    lines.append(f"  - {label(kind)}: {label(state['sync_status'])}")
    if lines[-1]:
        lines.append("")

    cards, candidates = [], []
    for card in result["problems"][:5]:
        ident = card["id"]
        if not PROBLEM_ID.fullmatch(ident):
            continue
        card_url = f"{PUBLIC_BASE}#/problems/{ident}"
        sources = [source_link(solution["project"], solution["source_url"]) for solution in card["solutions"][:4]]
        suffix = " · ".join(link for link in sources if link)
        row = f"- [{ident} {label(card['title'])}]({card_url})"
        section = candidates if card.get("match_level") == "candidate" else cards
        section.append(f"{row} · {suffix}" if suffix else row)
    groups = ["### Reviewed catalog", "", *cards, ""] if cards else []
    if candidates:
        groups.extend(["### Possible catalog matches", "", *candidates, ""])
    groups.extend(source_group("Suggested cross-project leads", [
        match["right"] for match in result["matches"] if match.get("relationship") != "same_revision"
    ]))
    groups.extend(source_group("Same revision in another project", [
        match["right"] for match in result["matches"] if match.get("relationship") == "same_revision"
    ]))
    groups.extend(source_group("Other public observations", result["observations"]))
    if groups:
        lines.extend(groups)
    else:
        lines.extend(["No related work was found in this snapshot.", ""])

    check = result.get("first_check")
    if check:
        link = source_link("Reported test result", check["url"])
        if link:
            scope = []
            revision = check.get("revision")
            if revision and re.fullmatch(r"[a-fA-F0-9]{7,64}", revision):
                scope.append(f"revision `{revision}`")
            scope.extend(label(platform) for platform in check.get("platforms", [])[:4])
            details = f" ({', '.join(scope)})" if scope else ""
            lines.extend([f"**First check** · {link}{details}", ""])
            if check.get("observed"):
                lines.extend([f"**{label(check['outcome'].capitalize())}** · {label(check['observed'])}", ""])

    if groups and result.get("next_step"):
        lines.extend([label(result["next_step"]), ""])
    return "\n".join(lines)


def summary(environ):
    if environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return "This summary runs on GitHub pull request events.\n"
    try:
        request = pull_request(environ["GITHUB_EVENT_PATH"])
    except (KeyError, OSError, TypeError, ValueError):
        return "The pull request event could not be read. Continue the usual review.\n"
    try:
        return render_report(public_preflight(**request, limit=5))
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return UNAVAILABLE


def main(environ=None):
    environ = os.environ if environ is None else environ
    destination = environ.get("GITHUB_STEP_SUMMARY")
    if destination:
        try:
            with Path(destination).open("a", encoding="utf-8") as stream:
                stream.write(HEADER + summary(environ) + "\n")
        except OSError:
            # The action is advisory even when the runner cannot open its summary file.
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
