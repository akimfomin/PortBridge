"""Refresh pinned Test Lab reports from explicitly configured public threads."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import re
import time
from urllib.parse import urlencode

from .activity import source_time
from .github import API, RepositoryNotPublic, Unavailable, WORK_URL, _Sync
from .lab_report_formats import (FRAMELAB_DISCUSSION, FRAMELAB_REVISION, FRAMELAB_TASK, FRAMELAB_TESTER_ID,
                                 REPORT_POLICIES, case_outcome, structured_result)
from .tester_discovery import LOGIN, MAX_BODY, report_lines


REVIEW_HEADER = "PortBridge test review v1"
REPORT_LINK = re.compile(rf"Report: ({WORK_URL.pattern})#issuecomment-([1-9][0-9]*)")
REVIEW_DIGEST = re.compile(r"Body SHA-256: ([0-9a-f]{64})")
REVIEW_DECISION = re.compile(r"Decision: (approve|revoke)")
PAGE_SIZE = 30
MAX_PAGES = 4
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


def report_sources(task):
    """Use only links from the reviewed task card, stripping comment permalinks."""
    links = (task["result_url"], task["source_url"], *task.get("related_report_urls", ()))
    return tuple(dict.fromkeys(url.split("#", 1)[0] for url in links
                               if WORK_URL.fullmatch(url.split("#", 1)[0])))


def monitored(task):
    return bool(task.get("report_cases")) and bool(report_sources(task))


def scope(task, source):
    contract = [source, [row["sha"] for row in task["revisions"]], task["report_cases"], task["report_profile"], task["equipment"], task["os"],
                task.get("approved_testers", ()), task.get("reviewed_reports", {})]
    digest = sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"structured-v1:{digest}"


def review_scope(report_scope):
    # Older exporters can keep reading report rows during a rollback.
    return f"{report_scope}:thread-reviews-v1"


def report_source(task, source=None):
    url = source or report_sources(task)[0]
    repo, _, number = url.removeprefix("https://github.com/").rsplit("/", 2)
    return repo, f"{API}/repos/{repo}/issues/{number}"


def legacy_framelab_scope(task, source):
    profile, cases = REPORT_POLICIES[FRAMELAB_TASK]
    return (task["id"] == FRAMELAB_TASK and source == FRAMELAB_DISCUSSION
            and FRAMELAB_TESTER_ID in task.get("approved_testers", ())
            and [row["sha"] for row in task["revisions"]] == [FRAMELAB_REVISION]
            and task["report_cases"] == list(cases) and task["report_profile"] == profile
            and task["equipment"] == ["amd"] and task["os"] == ["Windows", "Linux"])


def legacy_framelab_result(body, task):
    lines = []
    for line in report_lines(body):
        if line.casefold() in {"reproduction", "earlier failures and limitations"}:
            break
        lines.append(line)
    revision = task["revisions"][0]["sha"]
    result = framelab_result(lines, revision)
    if result is None:
        return None
    hardware, outcome = result
    device = next((f"1002:{code}" for code, name in FRAMELAB_DEVICES.items() if name == hardware), hardware)
    return {"revision": revision, "revisions": [revision], "equipment": "amd", "hardware": hardware,
            "device_id": device, "outcome": outcome, "opt_in": False}


def body_digest(body):
    return sha256(body.replace("\r\n", "\n").encode()).hexdigest()


def reviewed_result(body, task, url, actor_id):
    """Import a human-reviewed public report only while its exact source is unchanged."""
    record = task.get("reviewed_reports", {}).get(url)
    if not record or record["actor_id"] != actor_id:
        return None
    pins = [row["sha"] for row in task["revisions"]]
    outcome = case_outcome(record["cases"], task["report_cases"])
    if (record["body_sha256"] != body_digest(body) or record["revisions"] != pins
            or record["equipment"] not in task["equipment"] or record["os_family"] not in task["os"]
            or outcome is None):
        return None
    fields = ("revisions", "equipment", "hardware", "os", "os_family", "driver", "cases")
    return {**{field: record[field] for field in fields}, "revision": pins[0],
            "device_id": record["hardware"].casefold(), "outcome": outcome, "opt_in": False}


def comment_metadata(comment, source, repo, issue):
    if not isinstance(comment, dict) or comment.get("minimized") is True:
        return None
    ident = comment.get("id")
    actor = comment.get("user")
    body = comment.get("body")
    reported = source_time(comment.get("created_at"))
    updated = source_time(comment.get("updated_at"))
    if (type(ident) is not int or ident <= 0 or not isinstance(actor, dict) or actor.get("type") != "User"
            or type(actor.get("id")) is not int or actor["id"] <= 0
            or not isinstance(body, str) or len(body) > MAX_BODY or reported is None):
        return None
    author = actor.get("login")
    url = f"{source}#issuecomment-{ident}"
    expected = {"issue_url": issue, "html_url": url, "url": f"{API}/repos/{repo}/issues/comments/{ident}"}
    if (not isinstance(author, str) or not LOGIN.fullmatch(author)
            or any(not isinstance(comment.get(key), str) or comment[key].casefold() != value.casefold()
                   for key, value in expected.items())):
        return None
    updated = max(reported, updated) if updated else reported
    return {"url": url, "author": author,
            "reported_at": reported.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "updated_at": updated.isoformat(timespec="seconds").replace("+00:00", "Z")}


def normalize_report(comment, task, source, repo, issue):
    metadata = comment_metadata(comment, source, repo, issue)
    if metadata is None:
        return None
    actor_id = comment["user"]["id"]
    body = comment["body"]
    reviewed = reviewed_result(body, task, metadata["url"], actor_id)
    result = reviewed or structured_result(body, task)
    approved = (bool(reviewed) or actor_id in task.get("approved_testers", ())
                or comment.get("author_association") == "OWNER")
    # The original reports predate the common format. Keep their narrow source
    # and author boundary; other historical prose still requires manual review.
    if result is None and actor_id == FRAMELAB_TESTER_ID and legacy_framelab_scope(task, source):
        result = legacy_framelab_result(body, task)
    if result is None:
        return None
    return {**result, **metadata, "authority": "approved" if approved else "community",
            "body_sha256": body_digest(body)}


def normalize_thread_review(comment, task, source, repo, issue):
    """Accept a review only from the owner in the task's designated result thread."""
    sources = report_sources(task)
    if not sources or source != sources[0]:
        return None
    metadata = comment_metadata(comment, source, repo, issue)
    if metadata is None or comment.get("author_association") != "OWNER":
        return None
    lines = comment["body"].strip().splitlines()
    if (len(lines) < 5 or lines[:2] != [REVIEW_HEADER, f"Task: {task['id']}"]
            or (len(lines) > 5 and lines[5].strip())):
        return None
    report = REPORT_LINK.fullmatch(lines[2])
    digest = REVIEW_DIGEST.fullmatch(lines[3])
    decision = REVIEW_DECISION.fullmatch(lines[4])
    if not (report and digest and decision):
        return None
    target = next((url for url in sources if url.casefold() == report[1].casefold()), None)
    if target is None:
        return None
    return {**metadata, "report_url": f"{target}#issuecomment-{report[2]}",
            "body_sha256": digest[1], "review_decision": decision[1]}


def scan_comments(issue, request_page):
    # GitHub serves both issue and pull request conversation comments from /issues.
    # https://docs.github.com/en/rest/issues/comments#list-issue-comments
    for page in range(1, MAX_PAGES + 1):
        query = urlencode({"per_page": PAGE_SIZE, "page": page})
        comments, has_next = request_page(f"{issue}/comments?{query}")
        if not isinstance(comments, list) or len(comments) > PAGE_SIZE:
            raise Unavailable("GitHub returned unexpected Test Lab comments")
        yield from comments
        if not has_next:
            return
    raise Unavailable("Test Lab comment page budget exhausted")


def normalized_records(comments, task, source):
    repo, issue = report_source(task, source)
    records = []
    for comment in comments:
        record = (normalize_thread_review(comment, task, source, repo, issue)
                  or normalize_report(comment, task, source, repo, issue))
        if record is not None:
            records.append(record)
    return records


def comment_order(record, time_field="reported_at"):
    return record[time_field], int(record["url"].rsplit("-", 1)[1])


def sorted_records(records):
    unique = {record["url"]: record for record in records}
    return sorted(unique.values(), key=comment_order)


def resolve_reviews(task, records, checked_sources=None):
    """Resolve reviews against the latest observed body only after linking both sources."""
    primary_source = next(iter(report_sources(task)), None)
    reviews = {}
    reports = []
    for record in sorted_records(records):
        if "review_decision" not in record:
            reports.append(record)
        elif record["url"].partition("#")[0] == primary_source:
            reviews[(record["report_url"], record["body_sha256"])] = record

    resolved = []
    for report in reports:
        review = reviews.get((report["url"], report.get("body_sha256")))
        update_field = "updated_at" if report.get("updated_at") else "reported_at"
        if review is None or comment_order(review) <= comment_order(report, update_field):
            resolved.append(report)
            continue
        decision = review["review_decision"]
        if decision == "approve" and checked_sources is not None:
            checked = source_time(checked_sources.get(report["url"].partition("#")[0]))
            # An approval discovered after the last successful scan cannot promote
            # a retained body while the report's thread is still unavailable.
            if checked is None or checked < source_time(review["updated_at"]):
                resolved.append(report)
                continue
        evidence = {field: review[field] for field in ("url", "author", "reported_at", "updated_at")}
        resolved.append({**report, "authority": "approved" if decision == "approve" else "community",
                         "review": {**evidence, "decision": decision}})
    return resolved


def scan_reports(task, request_page):
    records = []
    for source in report_sources(task):
        _, issue = report_source(task, source)
        records.extend(normalized_records(scan_comments(issue, request_page), task, source))
    return resolve_reviews(task, records)


def fetch_comments(sync, source, task):
    repo, issue = report_source(task, source)
    sync._require_public(repo, verify_anonymous=True)

    def request_page(url):
        data, headers = sync._request(url, "core", None)
        return data, 'rel="next"' in headers.get("Link", "")

    comments = list(scan_comments(issue, request_page))
    if sync.token:
        sync._require_public(repo, recheck=True)
    return comments


def fetch_public_comments(sync, anonymous, source, task):
    try:
        return fetch_comments(sync, source, task)
    except Unavailable as exc:
        if not sync.token or isinstance(exc, RepositoryNotPublic) or exc.http_status not in {401, 403, 404}:
            raise
    return fetch_comments(anonymous, source, task)


def coverage_cells(task, reports):
    cells = []
    for equipment in task["equipment"]:
        findings = sorted((entry for entry in reports if entry.get("equipment") == equipment),
                          key=lambda entry: (entry.get("updated_at") or entry.get("reported_at", ""),
                                             entry.get("reported_at", "")))
        latest = {(entry.get("author", "").casefold(), entry.get("device_id") or entry["hardware"], entry.get("os_family")):
                  entry["outcome"] for entry in findings if entry.get("authority") == "approved"}
        if "fail" in latest.values():
            state = "contradicted"
        elif "pass" in latest.values():
            state = "covered"
        elif "partial" in latest.values():
            state = "partial"
        else:
            state = "reported" if findings else "missing"
        cells.append({"equipment": equipment, "state": state})
    return cells


def has_passing_coverage(task, reports, *, equipment=None):
    cells = coverage_cells(task, reports)
    if equipment:
        cells = [cell for cell in cells if cell["equipment"] == equipment]
    states = {cell["state"] for cell in cells}
    if equipment or task.get("coverage_policy") == "all":
        return states == {"covered"}
    return "covered" in states and "contradicted" not in states


def report_state(row):
    if row is None:
        return {"state": "unchecked", "checked_at": None, "attempted_at": None, "reports": []}
    state = "stale" if row["state"] == "unavailable" and row["checked_at"] else row["state"]
    return {"state": state, "checked_at": row["checked_at"], "attempted_at": row["attempted_at"],
            "reports": json.loads(row["reports"])}


def migrate_legacy_report(row):
    if row is None:
        return None
    return {**dict(row), "reports": json.dumps(
        [{**report, "authority": "approved", "equipment": "amd", "revisions": [report["revision"]],
          "device_id": next((f"1002:{code}" for code, name in FRAMELAB_DEVICES.items() if report["hardware"] == name),
                            report["hardware"]), "opt_in": False}
         for report in json.loads(row["reports"])])}


def legacy_row(rows, task, source):
    if legacy_framelab_scope(task, source):
        previous = rows.get((task["id"], f"framelab-table-v1:{source}:{FRAMELAB_REVISION}"))
        return migrate_legacy_report(previous)
    return None


def read_rows(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lab_report_checks'").fetchone():
        return {}
    return {(row["task"], row["scope"]): row for row in db.execute("SELECT * FROM lab_report_checks")}


def read_report_states(catalog, tasks):
    rows = {}
    if catalog is not None:
        with catalog.connect() as db:
            rows = read_rows(db)
    states = {}
    for task in tasks:
        if not monitored(task):
            continue
        sources = []
        reports = []
        for source in report_sources(task):
            report_scope = scope(task, source)
            row = rows.get((task["id"], report_scope)) or legacy_row(rows, task, source)
            state = report_state(row)
            reports.extend(state.pop("reports"))
            review_row = rows.get((task["id"], review_scope(report_scope)))
            if review_row and state["checked_at"] and review_row["checked_at"] == state["checked_at"]:
                reports.extend(json.loads(review_row["reports"]))
            sources.append({"url": source, **state})
        kinds = {entry["state"] for entry in sources}
        state = ("fresh" if kinds == {"fresh"} else "unchecked" if kinds == {"unchecked"}
                 else "stale" if kinds & {"fresh", "stale"} else "unavailable")
        checks = [entry["checked_at"] for entry in sources if entry["checked_at"]]
        attempts = [entry["attempted_at"] for entry in sources if entry["attempted_at"]]
        states[task["id"]] = {"state": state, "checked_at": min(checks, default=None),
                              "attempted_at": max(attempts, default=None), "sources": sources,
                              "reports": resolve_reviews(task, reports, {
                                  entry["url"]: entry["checked_at"] for entry in sources})}
    return states


def save_scan(db, task, record_scope, attempted, *, state, checked, reports, replace):
    db.execute("""INSERT INTO lab_report_checks VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(task, scope) DO UPDATE SET attempted_at=excluded.attempted_at, state=excluded.state,
            checked_at=CASE WHEN ? THEN excluded.checked_at ELSE lab_report_checks.checked_at END,
            reports=CASE WHEN ? THEN excluded.reports ELSE lab_report_checks.reports END
        WHERE excluded.attempted_at >= lab_report_checks.attempted_at""",
        (task["id"], record_scope, attempted, checked, state, json.dumps(reports), replace, replace))


def refresh_reports(catalog, tasks, *, authenticated=False):
    """Scan each reviewed discussion once and retain last complete results per source."""
    sources = {}
    for task in tasks:
        if monitored(task):
            for source in report_sources(task):
                sources.setdefault(source, []).append(task)
    with catalog.connect() as db:
        db.execute(TABLE)
        previous = read_rows(db)
        sync = _Sync(db, refresh=True, anonymous=not authenticated)
        anonymous = _Sync(db, refresh=True, anonymous=True) if sync.token else sync
        # Oldest scans first so an unavailable or crowded thread cannot
        # continuously starve lower-priority work within GitHub's time budget.
        ordered = sorted(sources, key=lambda source: min(
            ((previous.get((task["id"], scope(task, source))) or {"attempted_at": ""})["attempted_at"]
             for task in sources[source])))
        for source in ordered:
            if time.monotonic() >= sync.deadline:
                break
            attempted = datetime.now(timezone.utc).isoformat()
            # _Sync enforces both the rate-limit pause and the shared deadline.
            try:
                comments = fetch_public_comments(sync, anonymous, source, sources[source][0])
            except Unavailable as exc:
                with db:
                    for task in sources[source]:
                        # GitHub uses an anonymous 404 for missing and private resources.
                        clear = isinstance(exc, RepositoryNotPublic) or exc.http_status in {404, 451}
                        report_scope = scope(task, source)
                        retained = legacy_row(previous, task, source)
                        if retained and (task["id"], report_scope) not in previous:
                            check = report_state(retained)
                            save_scan(db, task, report_scope, attempted, state="unavailable",
                                      checked=None if clear else check["checked_at"],
                                      reports=[] if clear else check["reports"], replace=True)
                        else:
                            save_scan(db, task, report_scope, attempted, state="unavailable",
                                      checked=None, reports=[], replace=clear)
                        if clear and source == report_sources(task)[0]:
                            save_scan(db, task, review_scope(report_scope), attempted, state="unavailable",
                                      checked=None, reports=[], replace=True)
                if not sync.token and (exc.http_status == 429 or "rate limit" in str(exc).lower()):
                    break
            else:
                checked = datetime.now(timezone.utc).isoformat()
                with db:
                    for task in sources[source]:
                        records = sorted_records(normalized_records(comments, task, source))
                        report_scope = scope(task, source)
                        reports = [record for record in records if "review_decision" not in record]
                        save_scan(db, task, report_scope, attempted, state="fresh", checked=checked,
                                  reports=reports, replace=True)
                        if source == report_sources(task)[0]:
                            reviews = [record for record in records if "review_decision" in record]
                            save_scan(db, task, review_scope(report_scope), attempted, state="fresh", checked=checked,
                                      reports=reviews, replace=True)
    return read_report_states(catalog, tasks)
