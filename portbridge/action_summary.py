"""Write advisory PortBridge results to a GitHub Actions job summary."""

import json
import os
from pathlib import Path
import re
import string
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener

from .catalog import PROBLEM_ID, public_url
from .discovery_search import key as discovery_source_key
from .github import API, NoRedirect, PR_URL
from .matching import canonical_url, current_repository
from .preflight import PUBLIC_BASE, english_text, public_preflight


EVENT_LIMIT = 4 * 1024 * 1024
ESCAPE_MARKDOWN = str.maketrans({char: f"&#{ord(char)};" for char in string.punctuation})
HEADER = "## PortBridge prior-work summary\n\n"
UNAVAILABLE = "The public catalog is unavailable. Continue the usual review.\n"


def pull_request(event_name, event_path):
    with Path(event_path).open("rb") as stream:
        data = stream.read(EVENT_LIMIT + 1)
    if len(data) > EVENT_LIMIT:
        raise ValueError("GitHub event exceeds size limit")
    event = json.loads(data)
    head = None
    if event_name == "workflow_dispatch":
        title, source = "", event["inputs"]["pull_request_url"]
        if isinstance(source, str):
            source = source.strip()
    else:
        request = event["pull_request"]
        title, source = request["title"], request["html_url"]
        if event["repository"]["private"] is not False or request["base"]["repo"]["private"] is not False:
            raise ValueError("Public repositories only")
        head = request["head"]["sha"]
        if not isinstance(head, str) or not re.fullmatch("[0-9a-f]{40}", head):
            raise ValueError("Missing PR event head")
    if (not isinstance(title, str) or not isinstance(source, str)
            or len(source) > 500 or not PR_URL.fullmatch(source)):
        raise ValueError("Invalid pull request data")
    return {"q": " ".join(title.split())[:200], "url": source}, head


def label(text):
    return " ".join("".join(char for char in text[:320] if char.isprintable() or char.isspace()).split()).translate(
        ESCAPE_MARKDOWN
    )


def public_pr_head(url):
    """Resolve a typed URL anonymously without sending PR prose to the renderer."""
    owner, repo, _, number = urlsplit(url).path.strip("/").split("/")
    endpoint = f"{API}/repos/{current_repository(f'{owner}/{repo}')}/pulls/{number}"
    request = Request(endpoint, headers={"User-Agent": "PortBridge receiver", "Accept": "application/vnd.github+json"})
    with build_opener(NoRedirect()).open(request, timeout=6) as response:
        data = response.read(EVENT_LIMIT + 1)
    if len(data) > EVENT_LIMIT:
        raise ValueError("PR metadata exceeds the limit")
    pr = json.loads(data)
    head = pr["head"]["sha"]
    if (pr["number"] != int(number) or pr["base"]["repo"]["private"] is not False
            or not PR_URL.fullmatch(pr["html_url"]) or canonical_url(pr["html_url"]) != canonical_url(url)
            or not re.fullmatch("[0-9a-f]{40}", head)):
        raise ValueError("Unexpected public PR identity")
    return head


def source_link(title, url, *, discovery=False):
    if not (discovery_source_key(url) if discovery else public_url(url)) or len(url) > 500:
        return None
    destination = quote(url, safe=":/?#&=%+@-._~")
    return f"[{label(title)}]({destination})"


def source_group(heading, items, confidence=None):
    rows = []
    for item in items[:5]:
        link = source_link(item["title"], item["url"])
        if link:
            rows.append(f"- {link}" + (f" · {confidence}" if confidence else ""))
    return [f"### {heading}", "", *rows, ""] if rows else []


def render_report(result, *, source_url=None, head=None, event_origin=False):
    lines = ["Review these leads against the target revision and configuration.", ""]
    origin = source_url or result.get("origin_url")
    if origin and PR_URL.fullmatch(origin):
        lines.extend([source_link("Source pull request", origin), ""])
        if head:
            scope = "PR event head" if event_origin else "Public PR head"
            lines.extend([f"{scope}: `{head}`. Catalog evidence may predate this head.", ""])
    if result.get("catalog_status") in {"partial", "stale", "error", "seed-only"}:
        lines.extend(["The public snapshot may be incomplete.", ""])
    if (result.get("catalog_freshness") or {}).get("age_state") == "stale":
        lines.extend(["Latest successful GitHub data is at least two hours old.", ""])
    for heading, stamp in (("GitHub last success", result.get("catalog_last_success")),
                           ("Snapshot generated", (result.get("publication") or {}).get("generated_at"))):
        if stamp:
            lines.append(f"- {heading}: {label(stamp)}")
    if result.get("origin_url") and result.get("indexed") is False:
        lines.extend(["This pull request is absent from the public index. Check its current details on GitHub.", ""])
    coverage = result.get("source_coverage", [])
    if len(coverage) > 1:
        # An unknown repository gets catalog-wide health from preflight.
        lines.extend([f"[Catalog source health]({PUBLIC_BASE}data/health.json)", ""])
    for source in coverage if len(coverage) == 1 else ():
        repo = label(source.get("repo", source["slug"]))
        for mode, health in source["history"].items():
            if health["status"] != "complete":
                lines.append(f"- {repo} · {label(mode)} history: {label(health['status'])}")
        if source.get("freshness") in {"partial", "stale", "error", "unavailable"} or source.get("age_state") == "stale":
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
        title = english_text(card, "title") or card["title"]
        row = f"- [{ident} {label(title)}]({card_url})"
        section = candidates if card.get("match_level") == "candidate" else cards
        section.append(f"{row} · {suffix}" if suffix else row)
    groups = ["### Reviewed catalog", "", *cards, ""] if cards else []
    if candidates:
        groups.extend(["### Possible catalog matches", "", *candidates, ""])
    groups.extend(source_group("Suggested cross-project leads", [
        match["right"] for match in result["matches"] if match.get("relationship") != "same_revision"
    ], "candidate · needs review"))
    groups.extend(source_group("Same revision in another project", [
        match["right"] for match in result["matches"] if match.get("relationship") == "same_revision"
    ], "matching revision · scope still needs review"))
    discovery = result.get("discovery") or {}
    if discovery.get("index_source") == "bundled_fallback":
        lines.extend(["Discovery is using bundled sources because the public snapshot is unavailable.", ""])
    historical = []
    for entry in discovery.get("technical_recommendations", [])[:2]:
        link = source_link(entry["title"], entry["source"], discovery=True)
        revision = entry.get("revision", "")
        if link and re.fullmatch(r"[a-fA-F0-9]{40,64}", revision):
            historical.append(f"- {link} · `{revision[:12]}` · potentially applicable, candidate for verification")
    if historical:
        groups.extend(["### Historical work in other projects", "", *historical, ""])
    research = [entry for entry in discovery.get("matches", []) if entry.get("evidence_status") == "source_found"]
    research.extend(discovery.get("automatic_matches", []))
    research_links = [source_link(entry["title"], entry["source"], discovery=True) for entry in research[:3]]
    research_lines = [f"- {link} · research source" for link in research_links if link]
    if research_lines:
        groups.extend(["### Discovery research sources", "", *research_lines, ""])
    code = result.get("source_code") or {}
    source_lines = []
    for entry in code.get("matches", [])[:3]:
        link = source_link(entry["path"], entry["url"])
        if link:
            source_lines.append(f"- {link} · line {entry['line']} · candidate, compare with the target")
    if source_lines:
        groups.extend(["### Candidate source-code lines", "", *source_lines, ""])
    if groups:
        lines.extend(groups)
    else:
        lines.extend(["No related work was found in this snapshot.", ""])
        if discovery.get("empty_reason"):
            lines.extend([label(discovery["empty_reason"]), ""])

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
            observed = english_text(check, "observed") or check.get("observed")
            if observed:
                lines.extend([f"**{label(check['outcome'].capitalize())}** · {label(observed)}", ""])

    if groups and result.get("next_step"):
        lines.extend([label(result["next_step"]), ""])
    return "\n".join(lines)


def summary_result(environ):
    event_name = environ.get("GITHUB_EVENT_NAME")
    explicit = environ.get("PORTBRIDGE_PR_URL", "").strip()
    if event_name == "pull_request_target" or (not explicit and event_name not in {"pull_request", "workflow_dispatch"}):
        return "skipped", "This summary runs on GitHub pull request events and manual workflow runs.\n"
    event_origin = not explicit and event_name == "pull_request"
    try:
        if explicit:
            if len(explicit) > 500 or not PR_URL.fullmatch(explicit):
                raise ValueError("Use a public GitHub pull request URL")
            request = {"q": "", "url": explicit}
            head = None
        else:
            request, head = pull_request(event_name, environ["GITHUB_EVENT_PATH"])
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        if explicit or event_name == "workflow_dispatch":
            return "invalid_input", "Enter a public GitHub pull request URL in pull_request_url.\n"
        return "invalid_input", "The pull request event could not be read. Continue the usual review.\n"
    if not event_origin:
        try:
            head = public_pr_head(request["url"])
        except HTTPError as error:
            with error:
                code = error.code
            if code in (404, 410):
                return "origin_missing", "GitHub could not find a publicly readable pull request at this URL.\n"
            return "origin_unverified", "GitHub could not verify the public PR. Retry when metadata is available.\n"
        except (AttributeError, KeyError, OSError, TypeError, ValueError):
            return "origin_unverified", "GitHub could not verify the public PR. Retry when metadata is available.\n"
    try:
        result = public_preflight(**request, limit=5)
        status = "unavailable" if result.get("catalog_status") == "unavailable" else "reported"
        return status, render_report(result, source_url=request["url"], head=head, event_origin=event_origin)
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return "unavailable", UNAVAILABLE


def summary(environ):
    return summary_result(environ)[1]


def main(environ=None):
    environ = os.environ if environ is None else environ
    destination = environ.get("GITHUB_STEP_SUMMARY")
    status = "summary_unavailable"
    if destination:
        try:
            with Path(destination).open("a", encoding="utf-8") as stream:
                outcome, markdown = summary_result(environ)
                stream.write(HEADER + markdown + "\n")
            status = outcome
        except OSError:
            # The action is advisory even when the runner cannot open its summary file.
            pass
    if output := environ.get("GITHUB_OUTPUT"):
        try:
            with Path(output).open("a", encoding="utf-8") as stream:
                stream.write(f"status={status}\n")
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
