"""Invite one suitable public test reporter after a maintainer labels a request."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .activity import source_time
from .github import API, NoRedirect, Unavailable
from .lab import EQUIPMENT, PORTBRIDGE, build_lab
from .lab_reports import has_passing_coverage, monitored, report_source, scan_reports
from .matching import canonical_url, current_repository


REPOSITORY = "akimfomin/PortBridge"
REPO_PATH = f"/repos/{REPOSITORY}"
APPROVAL = "notify-testers"
BOT = "github-actions[bot]"
TESTERS_FILE = Path(__file__).resolve().parent / "data" / "testers.json"
INVITES_FILE = TESTERS_FILE.with_name("test_invites.json")
COOLDOWN = timedelta(days=7)
REPORT_MAX_AGE = timedelta(days=90)
MAX_API_BYTES = 8 * 1024 * 1024
GITHUB_LOGIN = r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}"
GITHUB_REPO = r"[A-Za-z0-9_.-]{1,100}"
LOGIN = re.compile(GITHUB_LOGIN)
COMMIT = re.compile(rf"https://github\.com/({GITHUB_LOGIN})/({GITHUB_REPO})/commit/([A-Fa-f0-9]{{40}})")
PULL = re.compile(rf"https://github\.com/({GITHUB_LOGIN})/({GITHUB_REPO})/pull/([1-9][0-9]*)")
EVIDENCE_URL = re.compile(
    rf"https://github\.com/{GITHUB_LOGIN}/{GITHUB_REPO}/(?:(?:pull|issues)/[1-9][0-9]*"
    r"(?:#(?:issuecomment-|discussion_r|pullrequestreview-)[1-9][0-9]*)?|commit/[A-Fa-f0-9]{40})"
)
HARDWARE = re.compile(r"[A-Za-z0-9][A-Za-z0-9(). +/_-]{0,79}")
GPU_MODEL = re.compile(
    r"\b(RX|RTX|GTX)\s*([0-9]{3,4})(?:\s*(XTX|XT|GRE|Ti Super|Ti|Super))?"
    r"(?:\s+(Laptop(?: GPU)?|Mobile))?\b",
    re.I,
)
TASK_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MARKER = re.compile(rf"<!-- portbridge:test-invite:v[12]:([1-9][0-9]*):({GITHUB_LOGIN})"
                    rf"(?::([a-z0-9-]{{1,80}}:[0-9a-f]{{40}}:(?:amd|cpu|intel|nvidia)))? -->")
FIELDS = re.compile(
    r"### Lab task\n+(?P<task>[^\n]*)\n+"
    r"### Equipment\n+(?P<equipment>[^\n]+)\n+"
    r"### Source commit\n+(?P<revision>[^\n]+)\n+"
    r"### Requested check\n+(?P<check>[\s\S]+)"
)
CAPABILITIES = {
    "amd-rdna2-native-isa-hip": "native AMD RDNA2 instructions through HIP",
    "d3d12-native-wave64": "native Wave64 on D3D12",
    "d3d12-native-wave64-rdna4": "native Wave64 on D3D12 and RDNA4",
    "win32-vulkan-1.3": "Vulkan 1.3 presentation on Windows",
    "win32-vulkan-geometry": "Vulkan geometry shaders on Windows",
    "python-cpu": "CPU testing with Python",
}
TASK_CAPABILITIES = {
    "anyxboxx-147-native-wave64-gather": "amd-rdna2-native-isa-hip",
    "anyxboxx-133-native-carry": "amd-rdna2-native-isa-hip",
    "anyxboxx-133-native-fma": "amd-rdna2-native-isa-hip",
    "pb-5-xcl-wave64": "d3d12-native-wave64",
    "pb-9-reforge-present": "win32-vulkan-1.3",
    "scarlett-commons-continued-add-basic": "python-cpu",
    "xcl-1100-fma": "d3d12-native-wave64-rdna4",
}


def parse_request(body):
    if not isinstance(body, str) or len(body) > 4096:
        raise ValueError("invalid Test Request form")
    match = FIELDS.fullmatch(body.replace("\r\n", "\n").strip())
    if not match:
        raise ValueError("use the Test Request form with the four named fields")
    fields = {name: value.strip() for name, value in match.groupdict().items()}
    if fields["task"] in {"_No response_", "custom"}:
        fields["task"] = ""
    if fields["task"] and not TASK_ID.fullmatch(fields["task"]):
        raise ValueError("invalid Lab task ID")
    equipment, separator, model = fields["equipment"].partition(":")
    if equipment not in EQUIPMENT:
        raise ValueError("invalid equipment")
    fields["equipment"] = equipment
    fields["model"] = normalized_model(equipment, model) if separator else ""
    if separator and (fields["task"] or not fields["model"]):
        raise ValueError("exact GPU models are only supported for custom requests")
    if not commit_parts(fields["revision"]):
        raise ValueError("use a public GitHub commit URL with its full revision")
    check = fields["check"]
    if (not 8 <= len(check) <= 1000 or not any(character.isalpha() for character in check)
            or re.search(r"@|https?://|\bwww\.|(?:^|\n)#{1,6}\s", check, re.I)):
        raise ValueError("describe the requested check in plain text without links or mentions")
    if not fields["task"] and not fields["model"] and GPU_MODEL.search(check):
        raise ValueError("put the exact GPU model in the Equipment field")
    return fields


def normalized_model(equipment, model):
    model = " ".join(model.casefold().split())
    prefixes = {"amd": r"^(?:amd )?(?:radeon )?", "nvidia": r"^(?:nvidia )?(?:geforce )?",
                "intel": r"^(?:intel )?"}
    model = re.sub(prefixes.get(equipment, r"^$"), "", model)
    if equipment == "intel":
        return model if re.fullmatch(r"arc [ab][0-9]{3}m?", model) else ""
    match = GPU_MODEL.fullmatch(model)
    if match and ((equipment == "amd" and match[1] == "rx")
                  or (equipment == "nvidia" and match[1] in {"rtx", "gtx"})):
        return " ".join(part for part in match.groups() if part)
    return ""


def commit_parts(url):
    match = COMMIT.fullmatch(url)
    return match.groups() if match and match[2] not in {".", ".."} else None


def validate_scope(fields, github):
    if fields["task"]:
        tasks = build_lab(equipment=fields["equipment"], status="needs_run")["tasks"]
        task = next((entry for entry in tasks if entry["id"] == fields["task"]), None)
        if (task is None or not task["revisions"]
                or canonical_url(task["revisions"][0]["url"]) != canonical_url(fields["revision"])):
            raise ValueError("Lab task, equipment or revision does not match the open test")
        return TASK_CAPABILITIES.get(task["id"]), task["result_url"], task
    owner, repo, sha = commit_parts(fields["revision"])
    path = f"/repos/{current_repository(f'{owner}/{repo}')}"
    if github.get(path, public=True).get("private") is not False:
        raise ValueError("custom check needs a public repository")
    if github.get(f"{path}/commits/{sha}", public=True).get("sha", "").casefold() != sha.casefold():
        raise ValueError("custom check needs a pinned public commit")
    return None, None, None


def report_invitation_hold(task, github, equipment):
    if not task or not monitored(task):
        return ""
    _, issue = report_source(task)
    try:
        thread = github.get(issue.removeprefix(API), public=True)
        if not isinstance(thread, dict) or thread.get("state") != "open":
            return "The linked Test Lab report thread is closed or unavailable."
        reports = scan_reports(task, lambda url: github.request(url.removeprefix(API), public=True))
    except (OSError, Unavailable, ValueError):
        return "The linked Test Lab results could not be verified. No tester was invited."
    if has_passing_coverage(task, reports, equipment=equipment):
        return "The requested Test Lab coverage is already reported and ready for review."
    return ""


def load_testers(path=TESTERS_FILE):
    return validate_testers(json.loads(path.read_text(encoding="utf-8")))


def validate_testers(rows):
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError("invalid public tester roster")
    for row in rows:
        if (not isinstance(row, dict) or not LOGIN.fullmatch(row["login"])
                or row["equipment"] not in EQUIPMENT or not HARDWARE.fullmatch(row["hardware"])
                or not EVIDENCE_URL.fullmatch(row["evidence_url"]) or not source_time(row["reported_at"])
                or not isinstance(row["capabilities"], list)
                or any(capability not in CAPABILITIES for capability in row["capabilities"])):
            raise ValueError("invalid public tester record")
    return rows


def load_prior_invites(path=INVITES_FILE):
    if not path.is_file():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError("invalid public invitation history")
    for row in rows:
        if (not isinstance(row, dict) or not LOGIN.fullmatch(row["login"]) or not source_time(row["sent_at"])
                or not EVIDENCE_URL.fullmatch(row["evidence_url"])):
            raise ValueError("invalid prior invitation record")
    return rows


def trusted_marker(comment):
    if comment.get("user", {}).get("login") != BOT:
        return None
    body = comment.get("body") or ""
    return MARKER.fullmatch(body.partition("\n")[0])


def approved_issue(issue):
    return (issue.get("state") == "open" and "pull_request" not in issue
            and any(label.get("name") == APPROVAL for label in issue.get("labels", [])))


def dispatch(event, testers, github, *, event_name="issues", now=None, discover=None, prior_invites=()):
    if event.get("repository", {}).get("full_name", "").casefold() != REPOSITORY.casefold():
        return "Ignored unrelated event."
    if event_name == "workflow_dispatch":
        requested_issue = str(event.get("inputs", {}).get("issue_number", ""))
        if not re.fullmatch(r"[1-9][0-9]{0,9}", requested_issue):
            raise ValueError("enter a PortBridge request issue number")
        issue = github.get(f"{REPO_PATH}/issues/{requested_issue}")
        if not approved_issue(issue):
            return "The request is no longer open and approved."
    elif event_name == "issues" and event.get("action") == "labeled" and event.get("label", {}).get("name") == APPROVAL:
        issue = event["issue"]
    else:
        return "Ignored unrelated event."
    number = issue["number"]
    actor = event["sender"]["login"]
    if type(number) is not int or number <= 0 or not LOGIN.fullmatch(actor) or "pull_request" in issue:
        raise ValueError("invalid request issue or approving account")
    path = f"{REPO_PATH}/issues/{number}"
    if any(marker and int(marker[1]) == number for marker in
           (trusted_marker(comment) for comment in github.comments(f"{path}/comments"))):
        return "This request already has an invitation."
    permissions = github.get(f"{REPO_PATH}/collaborators/{actor}/permission")
    if permissions.get("permission") not in {"write", "admin"}:
        raise ValueError("the approving account needs repository write access")
    fields = parse_request(issue.get("body"))
    capability, original, task = validate_scope(fields, github)
    cell_scope = (f"{task['id']}:{task['revisions'][0]['sha']}:{fields['equipment']}" if task else None)
    now = now or datetime.now(timezone.utc)
    since = now - COOLDOWN
    excluded = {actor.casefold(), issue["user"]["login"].casefold()}
    excluded.update(row["login"].casefold() for row in prior_invites if since <= source_time(row["sent_at"]) <= now)
    for comment in github.comments(f"{REPO_PATH}/issues/comments", since=since.isoformat(timespec="seconds")):
        marker = trusted_marker(comment)
        created = source_time(comment.get("created_at"))
        if marker and created and created >= since:
            if cell_scope and marker[3] == cell_scope:
                return "This Test Lab revision and hardware cell already has a recent invitation."
            excluded.add(marker[2].casefold())
    requested_capabilities = (capability,) if capability else ()
    discovered = validate_testers(discover(fields["equipment"], requested_capabilities)) if discover else []
    oldest = now - REPORT_MAX_AGE
    candidates = [row for row in [*discovered, *testers] if row["equipment"] == fields["equipment"]
                  and (not capability or capability in row["capabilities"])
                  and (not fields["model"] or normalized_model(row["equipment"], row["hardware"]) == fields["model"])
                  and row["login"].casefold() not in excluded and oldest <= source_time(row["reported_at"]) <= now]
    if not candidates:
        return "No matching tester outside the recent invitation window."
    selected = max(candidates, key=lambda row: (source_time(row["reported_at"]), row["login"].casefold()))
    receiving_url = (task or {}).get("receiving_url", original)
    receiving = PULL.fullmatch(receiving_url or "")
    if receiving:
        owner, repo, pull = receiving.groups()
        receiving_repo = current_repository(f"{owner}/{repo}")
        source = github.get(f"/repos/{receiving_repo}/pulls/{pull}", public=True)
        revision = commit_parts(fields["revision"])[2]
        head = (source.get("head") or {}).get("sha") or ""
        if source.get("state") != "open" or head.casefold() != revision.casefold():
            return "The receiving pull request changed or closed. Review the current revision before inviting a tester."
    if hold := report_invitation_hold(task, github, fields["equipment"]):
        return hold
    current = github.get(path)
    if not approved_issue(current):
        return "The request is no longer open and approved."
    if parse_request(current.get("body")) != fields:
        return "The request changed after approval. Review and apply the label again."
    github.comment(f"{path}/comments", invitation(number, selected, capability, original, cell_scope=cell_scope))
    return "Posted one PortBridge Test Lab invitation."


def invitation(number, tester, capability, original=None, *, cell_scope=None):
    login = tester["login"]
    hardware = tester["hardware"]
    evidence = tester["evidence_url"]
    relevant = f" and the recorded support for {CAPABILITIES[capability]}" if capability else ""
    original_link = f" · [Original test discussion]({original})" if original else ""
    marker = (f"v2:{number}:{login}:{cell_scope}" if cell_scope else f"v1:{number}:{login}")
    return (
        f"<!-- portbridge:test-invite:{marker} -->\n"
        f"@{login}, PortBridge matched this test request to your [public {hardware} report]({evidence})"
        f"{relevant}. If you have time, you can take the check or decline here in this issue.\n\n"
        f"[Open the request]({PORTBRIDGE}/issues/{number}){original_link} · "
        "[PortBridge Test Lab](https://akimfomin.github.io/PortBridge/#/lab)"
    )


class GitHub:
    def __init__(self, token):
        self.token = token
        self.opener = build_opener(NoRedirect())

    def request(self, path, *, public=False, body=None):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "PortBridge Test Lab"}
        if not public:
            if not path.startswith(REPO_PATH + "/"):
                raise ValueError("authenticated requests must stay inside PortBridge")
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            if public:
                raise ValueError("the dispatcher cannot write outside PortBridge")
            headers["Content-Type"] = "application/json"
        request = Request(API + path, data=json.dumps(body).encode("utf-8") if body is not None else None,
                          headers=headers)
        with self.opener.open(request, timeout=15) as response:
            payload = response.read(MAX_API_BYTES + 1)
            if len(payload) > MAX_API_BYTES:
                raise ValueError("GitHub response exceeds size limit")
            return json.loads(payload), 'rel="next"' in response.headers.get("Link", "")

    def get(self, path, *, public=False):
        return self.request(path, public=public)[0]

    def comments(self, path, *, since=None):
        for page in range(1, 21):
            params = {"per_page": 100, "page": page}
            if since:
                params.update(since=since, sort="created", direction="desc")
            comments, has_next = self.request(f"{path}?{urlencode(params)}")
            yield from comments
            if not has_next:
                return
        raise ValueError("comment history is too large to check for repeat invitations")

    def comment(self, path, body):
        self.request(path, body={"body": body})


def main():
    from .tester_discovery import discover_testers

    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        print(dispatch(event, load_testers(), GitHub(os.environ["GITHUB_TOKEN"]),
                       event_name=os.environ["GITHUB_EVENT_NAME"], discover=discover_testers,
                       prior_invites=load_prior_invites()))
    except HTTPError as error:
        print(f"GitHub API returned HTTP {error.code}.")
        return 1
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        print("Test Request could not be verified against the form, roster or GitHub. No retry was attempted.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
