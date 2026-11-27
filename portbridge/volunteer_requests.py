"""Preview explicitly opted-in volunteers for a public Test Lab request."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from urllib.error import URLError

from .activity import source_time
from .test_requests import FIELDS, GitHub, LOGIN, REPO_PATH, commit_parts, normalized_model

HUB = 112
PREFIX = "PortBridge volunteer v1 |"
SCOPES = ("windows-d3d12", "windows-10-d3d12", "windows-11-ltsc-d3d12",
          "windows-vulkan", "linux-vulkan", "linux-hip", "macos-metal")


def hardware_scope(value):
    vendor, sep, text = value.partition(":")
    vendor = vendor.strip().lower()
    if not sep or vendor not in {"amd", "intel", "nvidia"}:
        return None
    model = normalized_model(vendor, text)
    return (vendor, model) if model else None


def match_request(issue, comments, scope, *, now=None):
    """Match a coordinator-selected scope to the latest consent per GitHub account."""
    if scope not in SCOPES or issue.get("state") != "open" or "pull_request" in issue:
        raise ValueError("Select a supported scope and an open Test Lab issue.")
    if not (issue.get("title") or "").startswith("Test request:"):
        raise ValueError("Select an open Test Lab issue.")
    form = FIELDS.fullmatch((issue.get("body") or "").replace("\r\n", "\n").strip())
    if not form or not commit_parts(form["revision"].strip()):
        raise ValueError("The request needs the Test Lab form and a pinned commit.")
    hardware = hardware_scope(form["equipment"].strip())
    if hardware is None:
        raise ValueError("The request needs an exact supported GPU model.")
    now = now or datetime.now(timezone.utc)
    oldest = now - timedelta(days=90)
    owner = (issue.get("user") or {}).get("login", "").lower()
    latest = {}
    for comment in comments:
        actor = comment.get("user") or {}
        login = actor.get("login") or ""
        if actor.get("type") != "User" or not LOGIN.fullmatch(login) or login.lower() == owner:
            continue
        body = (comment.get("body") or "").strip()
        number = comment.get("id")
        seen = source_time(comment.get("updated_at") or comment.get("created_at"))
        if not body.startswith(PREFIX) or type(number) is not int or number <= 0 or not seen or not oldest <= seen <= now:
            continue
        parts = [part.strip() for part in body.split("|")]
        consent = (len(parts) == 4 and "\n" not in body and parts[1] == scope
                   and hardware_scope(parts[2]) == hardware and parts[3] == "yes")
        order = (seen, not consent, number)
        key = login.lower()
        if key not in latest or order > latest[key][0]:
            latest[key] = (order, consent, login, number)
    return [
        {"login": login, "consent_url": f"https://github.com/akimfomin/PortBridge/issues/{HUB}#issuecomment-{number}"}
        for _, consent, login, number in sorted(latest.values(), key=lambda row: row[2].lower()) if consent
    ]


def hub_comments(github):
    for page in range(1, 21):
        rows, more = github.request(f"{REPO_PATH}/issues/{HUB}/comments?per_page=100&page={page}", public=True)
        if not isinstance(rows, list):
            raise ValueError("The volunteer thread could not be verified.")
        yield from rows
        if not more:
            return
    raise ValueError("The volunteer thread exceeds the verification limit.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue", type=int, help="PortBridge Test Lab issue number")
    parser.add_argument("--scope", required=True, choices=SCOPES, help="Confirm OS and API required by the request")
    args = parser.parse_args(argv)
    if not 1 <= args.issue <= 9999999999:
        parser.error("Enter a valid PortBridge issue number.")
    github = GitHub("")
    try:
        issue = github.get(f"{REPO_PATH}/issues/{args.issue}", public=True)
        matches = match_request(issue, hub_comments(github), args.scope)
    except (URLError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps({"issue": args.issue, "scope": args.scope, "matches": matches, "sent": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
