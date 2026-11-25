"""Refresh pinned Test Lab reports from explicitly configured public threads."""

from datetime import datetime, timezone
import json
import re
from urllib.parse import urlencode

from .activity import source_time
from .github import API, RepositoryNotPublic, Unavailable, WORK_URL, _Sync
from .tester_discovery import LOGIN, MAX_BODY, report_lines


PAGE_SIZE = 30
MAX_PAGES = 4
FRAMELAB_TASK = "framelab-12-vulkan-handoff"
# The FrameLab maintainer invited this tester in the linked report thread.
FRAMELAB_TESTER_ID = 71070620
FRAMELAB_DEVICES = {"1114": "AMD Radeon 860M", "13c0": "AMD Radeon Graphics (Ryzen 9 9950X3D)"}
FRAMELAB_CASES = {(scope, semaphore) for scope in ("same", "cross") for semaphore in ("binary", "timeline")}
COMMIT = re.compile(r"(?:Revision:|Exact unmodified source revision:"
                    r"|Build:.*standalone source files matched commit)\s*"
                    r"([a-f0-9]{40})\.?", re.I)
DEVICE = re.compile(r"\b(?:0x)?1002:(?:0x)?([a-f0-9]{4})\b", re.I)
QUEUE = re.compile(r"(\d{1,2})\s*(?:→|->)\s*(\d{1,2})( \(two distinct queues\)|, two distinct queues)?")
CLEAN = re.compile(
    r"CTest passed 1/1 .*The run produced 0 validation warnings, 0 validation errors, and 0 skips(?:\.|$)"
    r"|Final controlled-environment result: PASS, 4/4 cases; CTest 1/1, exit 0, [0-9.]+ s;"
    r" zero validation warnings/errors and zero skips(?:\.|$)",
    re.I,
)
CLEAN_VALIDATION = "validation: synchronization enabled; warnings=0; errors=0; skips=0"
SETUP_FIELDS = (
    re.compile(r"^(?:OS(?: and driver)?: )?(?:Windows|Linux|Ubuntu|Fedora)\b", re.I),
    re.compile(r"^(?:OS and driver:.*\bAMD|(?:AMD )?Driver(?:Info)?:?)\s+[0-9]+(?:\.[0-9]+)+", re.I),
    re.compile(r"\b(?:Vulkan|LunarG) SDK(?: version)?[ :]+[0-9]+(?:\.[0-9]+)+", re.I),
)
SYNC_VALIDATION = re.compile(r"\bsynchronization validation enabled\b"
                             r"|\benables VK_VALIDATION_FEATURE_ENABLE_SYNCHRONIZATION_VALIDATION_EXT\b", re.I)
TABLE = """CREATE TABLE IF NOT EXISTS lab_report_checks (
    task TEXT NOT NULL,
    scope TEXT NOT NULL,
    attempted_at TEXT NOT NULL,
    checked_at TEXT,
    state TEXT NOT NULL,
    reports TEXT NOT NULL,
    PRIMARY KEY (task, scope)
)"""


def framelab_result(lines, revision):
    """Interpret the published FrameLab result table and exact setup fields."""
    pins = [match[1].lower() for line in lines if (match := COMMIT.fullmatch(line))]
    devices = [match[1].lower() for line in lines if line.startswith(("Device:", "GPU:"))
               for match in DEVICE.finditer(line)]
    if pins != [revision] or len(devices) != 1:
        return None

    cases = {}
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [cell.strip().lower() for cell in line.strip("|").split("|")]
        queue = QUEUE.fullmatch(cells[0])
        if not queue:
            continue
        if len(cells) != 5 or cells[1] not in {"binary", "timeline"} or cells[4] not in {"pass", "fail", "skip"}:
            return None
        same_family = int(queue[1]) == int(queue[2])
        case = ("same" if same_family else "cross", cells[1])
        if case in cases:
            return None
        result = cells[4]
        if result == "pass" and cells[2:4] != ["64/64 pixels matched", "completed"]:
            return None
        cases[case] = "skip" if result == "pass" and same_family and queue[3] is None else result

    if not cases:
        return None
    clean = (any(line.casefold() == CLEAN_VALIDATION for line in lines)
             or (any(CLEAN.match(line) for line in lines)
                 and any(SYNC_VALIDATION.search(line) for line in lines)))
    setup_complete = all(any(field.search(line) for line in lines) for field in SETUP_FIELDS)
    if "fail" in cases.values():
        outcome = "fail"
    elif (cases.keys() == FRAMELAB_CASES and all(result == "pass" for result in cases.values())
          and clean and setup_complete):
        outcome = "pass"
    else:
        outcome = "partial"
    device = devices[0]
    return FRAMELAB_DEVICES.get(device, f"AMD GPU (1002:{device})"), outcome


def monitored(task):
    return task["id"] == FRAMELAB_TASK


def scope(task):
    pins = [entry["sha"] for entry in task["revisions"]]
    return f"framelab-table-v1:{task['result_url']}:{','.join(pins)}"


def report_source(task):
    url = task["result_url"]
    if not WORK_URL.fullmatch(url):
        raise ValueError("Test Lab reports require a canonical GitHub issue or pull request")
    repo, _, number = url.removeprefix("https://github.com/").rsplit("/", 2)
    return repo, f"{API}/repos/{repo}/issues/{number}"


def normalize_report(comment, task, repo, issue):
    if not isinstance(comment, dict) or comment.get("minimized") is True:
        return None
    ident = comment.get("id")
    actor = comment.get("user")
    body = comment.get("body")
    reported = source_time(comment.get("created_at"))
    if (type(ident) is not int or ident <= 0 or not isinstance(actor, dict)
            or actor.get("type") != "User" or actor.get("id") != FRAMELAB_TESTER_ID
            or not isinstance(body, str) or len(body) > MAX_BODY or reported is None):
        return None
    author = actor.get("login")
    url = f"{task['result_url']}#issuecomment-{ident}"
    expected = {"issue_url": issue, "html_url": url, "url": f"{API}/repos/{repo}/issues/comments/{ident}"}
    if (not isinstance(author, str) or not LOGIN.fullmatch(author)
            or any(not isinstance(comment.get(key), str) or comment[key].casefold() != value.casefold()
                   for key, value in expected.items())):
        return None
    revision = task["revisions"][0]["sha"]
    lines = []
    for line in report_lines(body):
        if line.casefold() in {"reproduction", "earlier failures and limitations"}:
            break
        lines.append(line)
    result = framelab_result(lines, revision)
    if result is None:
        return None
    hardware, outcome = result
    return {"url": url, "author": author, "revision": revision, "hardware": hardware, "outcome": outcome,
            "reported_at": reported.isoformat(timespec="seconds").replace("+00:00", "Z")}


def scan_reports(task, request_page):
    # GitHub places the discussion comments for both issues and PRs at /issues.
    # https://docs.github.com/en/rest/issues/comments#list-issue-comments
    repo, issue = report_source(task)
    reports = {}
    for page in range(1, MAX_PAGES + 1):
        query = urlencode({"per_page": PAGE_SIZE, "page": page})
        comments, has_next = request_page(f"{issue}/comments?{query}")
        if not isinstance(comments, list) or len(comments) > PAGE_SIZE:
            raise Unavailable("GitHub returned unexpected Test Lab comments")
        for comment in comments:
            if report := normalize_report(comment, task, repo, issue):
                reports[report["url"]] = report
        if not has_next:
            return sorted(reports.values(), key=lambda report: (
                report["reported_at"], int(report["url"].rsplit("-", 1)[1])))
    raise Unavailable("Test Lab comment page budget exhausted")


def fetch_reports(sync, task):
    repo, _ = report_source(task)
    sync._require_public(repo, verify_anonymous=True)

    def request_page(url):
        data, headers = sync._request(url, "core", None)
        return data, 'rel="next"' in headers.get("Link", "")

    return scan_reports(task, request_page)


def has_passing_coverage(reports):
    latest = {report["hardware"]: report["outcome"] for report in reports}
    return "pass" in latest.values() and "fail" not in latest.values()


def report_state(row):
    if row is None:
        return {"state": "unchecked", "checked_at": None, "attempted_at": None, "reports": []}
    state = "stale" if row["state"] == "unavailable" and row["checked_at"] else row["state"]
    return {"state": state, "checked_at": row["checked_at"], "attempted_at": row["attempted_at"],
            "reports": json.loads(row["reports"])}


def read_report_states(catalog, tasks):
    rows = {}
    if catalog is not None:
        with catalog.connect() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lab_report_checks'").fetchone():
                rows = {(row["task"], row["scope"]): row for row in db.execute("SELECT * FROM lab_report_checks")}
    return {task["id"]: report_state(rows.get((task["id"], scope(task)))) for task in tasks if monitored(task)}


def refresh_reports(catalog, tasks):
    """Persist a complete public scan, retaining the prior scan on transient failure."""
    with catalog.connect() as db:
        db.execute(TABLE)
        sync = _Sync(db, refresh=True, anonymous=True)
        for task in tasks:
            if not monitored(task):
                continue
            attempted = datetime.now(timezone.utc).isoformat()
            try:
                reports = fetch_reports(sync, task)
            except Unavailable as exc:
                # A confirmed private or legally unavailable source must not export saved reports.
                clear = isinstance(exc, RepositoryNotPublic) or exc.http_status == 451
                state, checked, reports = "unavailable", None, []
            else:
                clear = True
                state, checked = "fresh", datetime.now(timezone.utc).isoformat()
            with db:
                db.execute("""INSERT INTO lab_report_checks VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task, scope) DO UPDATE SET attempted_at=excluded.attempted_at, state=excluded.state,
                        checked_at=CASE WHEN ? THEN excluded.checked_at ELSE lab_report_checks.checked_at END,
                        reports=CASE WHEN ? THEN excluded.reports ELSE lab_report_checks.reports END
                    WHERE excluded.attempted_at >= lab_report_checks.attempted_at""",
                    (task["id"], scope(task), attempted, checked, state, json.dumps(reports), clear, clear))
    return read_report_states(catalog, tasks)
