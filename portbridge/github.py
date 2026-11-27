"""Read-only GitHub metadata sync with a conditional-request SQLite cache."""

from contextlib import closing
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .discovery_terms import API_SYMBOL, cues
from .matching import (RelatedIndex, canonical_url, current_repository, instruction_names, repository_identity,
                       source_revision)
from .technical_mechanisms import mechanisms


API = "https://api.github.com"
REPO = re.compile(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+")
PR_URL = re.compile(rf"https://github\.com/{REPO.pattern}/pull/[1-9][0-9]*")
WORK_URL = re.compile(rf"https://github\.com/{REPO.pattern}/(?:pull|issues)/[1-9][0-9]*")
SHA = re.compile(r"[0-9a-fA-F]{40,64}")
PAGE_SIZE = 20
CACHE_TTL = 900
SIGNATURE_VERSION = 6
PAIR_CHECK_LIMIT = 8
MAX_RESPONSE = 4 * 1024 * 1024
NOT_MODIFIED = object()
BODY_LIMIT = 32_768
SIGNATURE_LIMIT = 16
INSTRUCTION_LIMIT = 48
UPDATE_OVERLAP = 60
INITIAL_UPDATE_WINDOW = 24 * 60 * 60
PUBLIC_ACCESS_FAILURES = {404, 451}
URL = re.compile(r"https?://[^\s<>()\[\]\"`]+", re.I)
REFERENCE = re.compile(r"/([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+)/(issues|pull|commit)/([A-Za-z0-9]+)/?")
REPOSITORY_PATH = re.compile(rf"/({REPO.pattern})/?")
TOKEN_PATTERN = re.compile(r"(?i)(?<![a-z0-9])(?:github_pat_|gh[pousr]_)[a-z0-9_]{8,}")
TECHNICAL_TERM = re.compile(
    r"\b(?:d3d12|direct3d(?: 12)?|directx(?: 12)?|dxgi|vulkan|metal|xenos|xggraphics|"
    r"dxil|dxbc|spir[- ]?v|hlsl|glsl|rectlist|rectangle list|quadlist|shader(?:s)?|"
    r"tessellation|atomic(?:s)?|bindless|descriptor heap|resource barrier|swapchain|swap chain|"
    r"pipeline cache|root signature|command queue|command list|executeindirect|"
    r"wave(?:32|64)|mesh shader|sampler feedback|device (?:lost|removed|hung)|"
    r"black frame|black screen|memory leak|out of memory|vertex fetch|"
    r"buffer overflow|data race|deadlock|access violation|frame pacing|"
    r"stencil|depth test|depth buffer|texture tiling|readback|workgraph|work graph|"
    r"xinput|xaudio2|wasapi|avx2|arm64|x86_64|wine|proton|moltenvk|vkd3d)\b", re.I,
)
TERM_ALIASES = {
    "direct3d 12": "d3d12", "directx 12": "d3d12", "spirv": "spir-v",
    "spir v": "spir-v", "rectangle list": "rectlist", "swap chain": "swapchain",
    "atomics": "atomic", "shaders": "shader", "work graph": "workgraph",
}



class NoRedirect(HTTPRedirectHandler):
    """A repository move must not send a token to a redirect destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Unavailable(Exception):
    """The page is temporarily unavailable or cannot be read."""

    def __init__(self, message, *, http_status=None, reason=None, attempted=True, retry_at=None):
        super().__init__(message)
        self.http_status = http_status
        self.reason = reason or ({301: "moved", 403: "forbidden", 404: "not_public",
                                  410: "gone", 429: "rate_limit", 451: "restricted"}.get(http_status)
                                 or ("github_unavailable" if http_status and http_status >= 500 else "unknown"))
        self.attempted = attempted
        self.retry_at = retry_at


class RepositoryNotPublic(Unavailable):
    """An authenticated lookup explicitly confirmed nonpublic visibility."""


class FeedDisabled(Unavailable):
    """Repository metadata explicitly disables this feed."""


def _text(value, limit=300):
    if not isinstance(value, str):
        return ""
    return TOKEN_PATTERN.sub("[redacted]", " ".join(value[:4096].split()))[:limit]


def _object(value):
    return value if isinstance(value, dict) else {}


def _array(value):
    return value if isinstance(value, list) else []


def _login(value):
    return _text(_object(value).get("login"), 100)


def _sha(value):
    return value.lower() if isinstance(value, str) and SHA.fullmatch(value) else ""


def _etag(value):
    if isinstance(value, str) and len(value) <= 240 and all(32 <= ord(char) <= 126 for char in value):
        return value or None
    return None


def _utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds") if value else None


def _timestamp(value):
    if isinstance(value, str):
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if date.tzinfo is not None:
                return int(date.timestamp())
        except (ValueError, OverflowError, OSError):
            pass
    return 0


def _number(value):
    return value if type(value) is int and value > 0 else None


def _project(entry):
    repo = entry.get("repo") or entry.get("repository") or entry.get("repo_full_name")
    if not isinstance(repo, str) or not REPO.fullmatch(repo) or repo.rsplit("/", 1)[1] in (".", ".."):
        raise ValueError("a GitHub project must specify a repository as owner/name")
    slug = entry.get("slug") or entry.get("id") or repository_identity(repo).lower()
    if not isinstance(slug, str) or not slug.strip():
        raise ValueError("a GitHub project must specify a non-empty string slug")
    return {**entry, "slug": slug, "repo": current_repository(repo)}


def _limited(values):
    return list(dict.fromkeys(values))[:SIGNATURE_LIMIT]


def _technical(entry, label_names, repositories):
    # Only bounded, controlled vocabulary and typed source references leave memory.
    body = entry.get("body")
    body = body[:BODY_LIMIT] if isinstance(body, str) else ""
    value = f"{_text(entry.get('title'))}\n{' '.join(label_names)}\n{body}"
    references = []
    external_repositories = {}

    def reference(match):
        try:
            parsed = urlsplit(match[0].rstrip(".,;!:"))
        except ValueError:
            return " "
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
            return " "
        path = REFERENCE.fullmatch(parsed.path)
        root = path or REPOSITORY_PATH.fullmatch(parsed.path)
        if root:
            repo = current_repository(root[1])
            if repo.lower() not in repositories and repo.rsplit("/", 1)[1] not in {".", ".."}:
                if len(external_repositories) < SIGNATURE_LIMIT:
                    external_repositories.setdefault(repo.lower(), repo)
        if path:
            _, route, ident = path.groups()
            if route == "commit":
                ident = _sha(ident)
            elif not re.fullmatch(r"[1-9][0-9]{0,11}", ident):
                ident = ""
            if ident and repo.lower() in repositories and len(references) < SIGNATURE_LIMIT:
                canonical = f"https://github.com/{repositories[repo.lower()]}/{route}/{ident}"
                if canonical not in references:
                    references.append(canonical)
        return " "

    searchable = URL.sub(reference, value)
    terms = (match[0].casefold() for match in TECHNICAL_TERM.finditer(searchable))
    return {
        "version": SIGNATURE_VERSION,
        "terms": _limited(TERM_ALIASES.get(term, term) for term in terms),
        "discovery_cues": cues(searchable),
        "mechanisms": sorted(mechanisms(searchable)),
        "signals": (instruction_names(searchable)[:INSTRUCTION_LIMIT]
                    + _limited(match[0].casefold() for match in API_SYMBOL.finditer(searchable))),
        "references": references,
        "external_repositories": list(external_repositories.values()),
    }


def _current_signatures(items, kind):
    return kind not in {"issue", "pr", "repository_issues"} or all(
        _object(_object(_object(item).get("metadata")).get("technical")).get("version") == SIGNATURE_VERSION
        for item in items
    )


def _item(entry, kind, project, repositories, *, repository_issues=False):
    repo = project["repo"]
    metadata = {"evidence_kind": "reported", "github_endpoint": kind}
    actor = _object(entry.get("user"))
    author = _login(actor)
    status = _text(entry.get("state"), 40) or "unknown"
    title = _text(entry.get("title"))
    updated = _text(entry.get("updated_at"), 40)
    if kind == "commit":
        ident = _sha(entry.get("sha"))
        commit = _object(entry.get("commit"))
        git_author = _object(commit.get("author"))
        git_committer = _object(commit.get("committer"))
        actor = _object(entry.get("author"))
        author = _login(actor) or _text(git_author.get("name"), 100)
        message = commit.get("message")
        if isinstance(message, str):
            title = _text(message.partition("\n")[0])
        updated = _text(git_committer.get("date") or git_author.get("date"), 40)
        status = "recorded"
        endpoint = "commit"
        metadata["sha"] = ident
    elif kind == "test":
        ident = _number(entry.get("id"))
        endpoint = "actions/runs"
        conclusion = _text(entry.get("conclusion"), 40)
        status = conclusion or _text(entry.get("status"), 40) or "unknown"
        actor = _object(entry.get("actor"))
        author = _login(actor)
        title = _text(entry.get("name")) or _text(entry.get("display_title"))
        metadata.update({
            "evidence_kind": "automated",
            "scope": "workflow_run",
            "workflow": _text(entry.get("name"), 120),
            "run_status": _text(entry.get("status"), 40),
            "conclusion": conclusion or None,
            "head_sha": _sha(entry.get("head_sha")),
            "head_branch": _text(entry.get("head_branch"), 120),
            "event": _text(entry.get("event"), 40),
            "pull_requests": [
                pr["number"] for pr in _array(entry.get("pull_requests"))[:20]
                if isinstance(pr, dict) and _number(pr.get("number"))
            ],
        })
    else:
        ident = _number(entry.get("number"))
        endpoint = "issues" if kind == "issue" else "pull"
        labels = [
            _text(_object(label).get("name"), 80)
            for label in _array(entry.get("labels"))[:30]
        ]
        metadata.update({"number": ident, "labels": [label for label in labels if label]})
        metadata["technical"] = _technical(entry, metadata["labels"], repositories)
        title = _text(URL.sub(" ", title))
        if repository_issues:
            metadata["github_endpoint"] = "repository_issues"
        if kind == "pr":
            pull = _object(entry.get("pull_request"))
            merged_at = _text(entry.get("merged_at") or pull.get("merged_at"), 40)
            if merged_at:
                status = "merged"
            metadata.update({
                "merged_at": merged_at or None,
                "draft": entry.get("draft") is True,
                "head_sha": _sha(_object(entry.get("head")).get("sha")),
                "base_branch": _text(_object(entry.get("base")).get("ref"), 120),
            })
        else:
            metadata["state_reason"] = _text(entry.get("state_reason"), 40) or None
    if not ident:
        return None
    metadata["author"] = author
    metadata["author_type"] = _text(actor.get("type"), 20)
    metadata["created_at"] = _text(entry.get("created_at"), 40)
    if kind == "pr":
        merger = _object(entry.get("merged_by"))
        if merger.get("type") == "User" and (login := _login(merger)):
            metadata["merged_by"] = {"login": login, "user_id": _number(merger.get("id"))}
    if user_id := _number(actor.get("id")):
        metadata["github_user_id"] = user_id
    return {
        "project": project["slug"], "kind": kind, "source_id": str(ident),
        "title": title or f"{kind} {ident}", "url": f"https://github.com/{repo}/{endpoint}/{ident}",
        "status": status, "updated_at": updated, "metadata": metadata,
    }


def _query(project, kind, page, *, since=None):
    params = {"per_page": PAGE_SIZE, "page": page}
    repo = project["repo"]
    if kind == "repository_issues":
        params.update(state="all", sort="created" if since is None else "updated", direction="asc")
        if since is not None:
            params["since"] = _utc(since).replace("+00:00", "Z")
        return f"{API}/repos/{repo}/issues?{urlencode(params)}", "core"
    if kind == "issue":
        params.update(state="all", sort="updated", direction="desc")
        return f"{API}/repos/{repo}/issues?{urlencode(params)}", "core"
    endpoint = {"pr": "pulls", "commit": "commits", "test": "actions/runs"}[kind]
    if kind == "pr":
        params.update(state="all", sort="updated", direction="desc")
    return f"{API}/repos/{repo}/{endpoint}?{urlencode(params)}", "core"


def _validated_item(item, page_checked_at):
    """A successful page check confirms only revisions actually present on that page."""
    if page_checked_at is None or not source_revision(item):
        return item
    return {**item, "revision_checked_at": _utc(page_checked_at)}


class _Sync:
    def __init__(self, db, refresh, projects=(), *, anonymous=False, time_budget=45):
        self.db = db
        self.refresh = refresh
        self.token = None if anonymous else (
            os.environ.get("PORTBRIDGE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN"))
        self.context = "authenticated" if self.token else "anonymous"
        self.opener = build_opener(NoRedirect())
        self.deadline = time.monotonic() + time_budget
        self.public_checks = {}
        self.repository_metadata = {}
        self.transport_failure = None
        self.transport_failures = 0
        self.repositories = {project["repo"].lower(): project["repo"] for project in projects}
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS github_cache (
                url TEXT PRIMARY KEY,
                etag TEXT,
                fetched_at REAL NOT NULL,
                items TEXT NOT NULL,
                has_next INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS github_rate_limit (
                context TEXT NOT NULL,
                resource TEXT NOT NULL,
                resume_at REAL NOT NULL,
                PRIMARY KEY (context, resource)
            );
        """)

    def _pause(self, resource, resume_at):
        with self.db:
            self.db.execute("""
                INSERT INTO github_rate_limit VALUES (?, ?, ?)
                ON CONFLICT(context, resource) DO UPDATE SET resume_at = max(resume_at, excluded.resume_at)
            """, (self.context, resource, resume_at))

    def _rate_headers(self, resource, headers, status):
        now = time.time()
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset", "")
        if remaining == "0":
            self._pause(resource, float(reset) if reset.isdigit() else now + 60)
        retry = headers.get("Retry-After")
        if status in (403, 429, 503) and retry:
            try:
                resume_at = now + int(retry) if retry.isdigit() else parsedate_to_datetime(retry).timestamp()
            except (ValueError, TypeError, OverflowError):
                resume_at = now + 60
            self._pause(resource, max(resume_at, now + 1))
        elif status == 429:
            self._pause(resource, now + 60)

    def _request(self, url, resource, etag):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com":
            raise ValueError("GitHub sync permits only https://api.github.com")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "PortBridge/0.1 (read-only repository metadata)",
        }
        if validator := _etag(etag):
            headers["If-None-Match"] = validator
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        redirected_id = None
        attempt = 0
        while attempt < 2:
            if self.transport_failures >= 2:
                raise Unavailable("GitHub connection paused after repeated failures", reason=self.transport_failure,
                                  attempted=False)
            http_status = None
            limit = self.db.execute("SELECT resume_at FROM github_rate_limit WHERE context=? AND resource=?",
                                    (self.context, resource)).fetchone()
            if limit and limit[0] > time.time():
                raise Unavailable(f"GitHub API paused until {_utc(limit[0])}", reason="rate_limit",
                                  attempted=False, retry_at=_utc(limit[0]))
            left = self.deadline - time.monotonic()
            if left <= 0:
                raise Unavailable("GitHub request time budget exhausted", reason="budget", attempted=False)
            try:
                request = Request(url, headers=headers, method="GET")
                with self.opener.open(request, timeout=min(8.0, left)) as response:
                    self.transport_failures = 0
                    self._rate_headers(resource, response.headers, response.status)
                    data = response.read(MAX_RESPONSE + 1)
                    if len(data) > MAX_RESPONSE:
                        raise Unavailable("GitHub metadata exceeds page size budget")
                    payload = json.loads(data)
                    if redirected_id and _number(_object(payload).get("id")) != redirected_id:
                        raise Unavailable("GitHub repository redirect changed identity", reason="invalid_payload")
                    return payload, response.headers
            except HTTPError as e:
                with e:
                    self._rate_headers(resource, e.headers, e.code)
                    if e.code == 304:
                        self.transport_failures = 0
                        return NOT_MODIFIED, e.headers
                    # Resolve repository metadata by stable numeric ID after a verified GitHub move.
                    # Never follow redirects for other requests or attach a token to a new host.
                    if e.code == 301 and not redirected_id and re.fullmatch(rf"/repos/{REPO.pattern}", parsed.path):
                        target = re.fullmatch(rf"{re.escape(API)}/repositories/([1-9][0-9]*)",
                                              e.headers.get("Location", ""))
                        if target:
                            redirected_id = int(target[1])
                            url = target[0]
                            headers.pop("If-None-Match", None)
                            continue
                    http_status = e.code
                    failure = f"GitHub HTTP {e.code}"
                    retryable = e.code in (500, 502, 503, 504) and not e.headers.get("Retry-After")
                    detail = b""
                    if e.code == 403:
                        try:
                            detail = e.read(4096).lower()
                        except (OSError, HTTPException):
                            pass
                    is_limited = (e.code == 429 or (e.code == 403 and (
                        b"rate limit" in detail or e.headers.get("X-RateLimit-Remaining") == "0"
                        or bool(e.headers.get("Retry-After")))))
                    if is_limited:
                        reset = self.db.execute(
                            "SELECT resume_at FROM github_rate_limit WHERE context=? AND resource=?",
                            (self.context, resource),
                        ).fetchone()
                        if not reset or reset[0] <= time.time():
                            self._pause(resource, time.time() + 60)
                        failure += " (rate limited)"
                        raise Unavailable(failure, http_status=e.code, reason="rate_limit",
                                          retry_at=_utc(reset[0] if reset and reset[0] > time.time()
                                                        else time.time() + 60))
            except (TimeoutError, URLError, OSError, HTTPException) as error:
                cause = error.reason if isinstance(error, URLError) else error
                reason = "timeout" if isinstance(cause, TimeoutError) else "connection"
                if attempt:
                    self.transport_failure = reason
                    self.transport_failures += 1
                    raise Unavailable("GitHub connection failed or timed out", reason=reason) from error
                failure, retryable = "GitHub connection failed or timed out", True
            except (ValueError, UnicodeError) as e:
                raise Unavailable("GitHub returned invalid JSON metadata", reason="invalid_payload") from e
            if attempt or not retryable:
                raise Unavailable(failure, http_status=http_status)
            attempt += 1
            time.sleep(0.25)
        raise Unavailable("GitHub request failed")

    def _require_public(self, repo, *, verify_anonymous=False, recheck=False):
        # Authenticated reads check visibility before listing metadata. Anonymous
        # callers may also need an explicit repository check for retained evidence.
        if not self.token and not verify_anonymous:
            return
        if recheck or repo not in self.public_checks:
            try:
                data, _ = self._request(f"{API}/repos/{repo}", "core", None)
                private = _object(data).get("private")
                visibility = _object(data).get("visibility", "public")
                if private is True or visibility in ("private", "internal"):
                    raise RepositoryNotPublic("repository is not public", reason="not_public")
                if private is not False or visibility != "public":
                    raise Unavailable("GitHub returned unexpected repository visibility")
            except Unavailable as e:
                self.public_checks[repo] = e
            else:
                self.public_checks[repo] = None
                self.repository_metadata[repo] = data
        if self.public_checks[repo]:
            raise self.public_checks[repo]

    def require_feed(self, repo, kind):
        metadata = self.repository_metadata.get(repo, {})
        flag = {"pr": "has_pull_requests", "issue": "has_issues"}.get(kind)
        if flag and metadata.get(flag) is False:
            raise FeedDisabled(f"GitHub {kind} feed is disabled by repository settings", reason="feed_disabled")

    def require_reference_feed(self, repo, kind):
        # An exact historical link is still useful when a repository has disabled new issues.
        if kind == "pr":
            self.require_feed(repo, kind)

    def active_repo(self, repo):
        name = self.repository_metadata.get(repo, {}).get("full_name")
        return name if isinstance(name, str) and REPO.fullmatch(name) else repo

    def public_access(self, repo, first_pages):
        if self.token:
            if repo not in self.public_checks:
                return None
            failure = self.public_checks[repo]
            if failure is None:
                return True
            if isinstance(failure, RepositoryNotPublic) or failure.http_status in PUBLIC_ACCESS_FAILURES:
                return False
            return None
        if any(state == "live" for state, _ in first_pages):
            return True
        # A single missing endpoint can describe the endpoint, rather than the repository.
        if sum(bool(error and error.http_status in PUBLIC_ACCESS_FAILURES) for _, error in first_pages) >= 2:
            return False
        return None

    def page(self, project, kind, number, *, since=None):
        url, resource = _query(project, kind, number, since=since)
        row = self.db.execute("SELECT etag, fetched_at, items, has_next FROM github_cache WHERE url=?",
                              (url,)).fetchone()
        cached = None
        current_schema = False
        if row:
            etag, fetched_at, encoded, has_next = row
            try:
                cached = json.loads(encoded)
                if not isinstance(cached, list):
                    cached = None
            except (TypeError, ValueError):
                pass
            current_schema = cached is not None and _current_signatures(cached, kind)
            if (fetched_at + CACHE_TTL > time.time() and current_schema and not self.refresh
                    and project.get("sync_status") != "unavailable"):
                return cached, has_next, "cached", fetched_at, None
        try:
            self._require_public(project["repo"])
            self.require_feed(project["repo"], kind)
            active = self.active_repo(project["repo"])
            request_url, _ = _query({**project, "repo": active}, kind, number, since=since)
            same_target = request_url == url
            raw, headers = self._request(request_url, resource, row[0] if current_schema and same_target else None)
            if raw is NOT_MODIFIED:
                if not current_schema:
                    raise Unavailable("GitHub returned 304 without a compatible cached page")
                items = cached
                has_next = row[3]
                etag = _etag(headers.get("ETag")) or row[0]
            else:
                if kind == "test":
                    records = _object(raw).get("workflow_runs")
                else:
                    records = raw
                if not isinstance(records, list):
                    raise Unavailable("GitHub returned unexpected metadata", reason="invalid_payload")
                if len(records) > PAGE_SIZE or any(not isinstance(record, dict) for record in records):
                    raise Unavailable("GitHub returned an incomplete or invalid page", reason="incomplete_page")
                items = []
                for record in records[:PAGE_SIZE]:
                    if not isinstance(record, dict) or (kind == "issue" and "pull_request" in record):
                        continue
                    item_kind = ("pr" if "pull_request" in record else "issue") if kind == "repository_issues" else kind
                    item = _item(record, item_kind, project, self.repositories,
                                 repository_issues=kind == "repository_issues")
                    if item is not None:
                        items.append(item)
                # Follow pagination numerically and ignore the untrusted URLs inside Link.
                has_next = 'rel="next"' in headers.get("Link", "")
                etag = _etag(headers.get("ETag"))
            fetched_at = time.time()
            if raw is not NOT_MODIFIED:
                for item in items:
                    item["fetched_at"] = _utc(fetched_at)
            with self.db:
                self.db.execute("""
                    INSERT INTO github_cache VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET etag=excluded.etag, fetched_at=excluded.fetched_at,
                        items=excluded.items, has_next=excluded.has_next
                """, (url, etag, fetched_at, json.dumps(items, ensure_ascii=False), has_next))
            return items, has_next, "live", fetched_at, None
        except Unavailable as e:
            if e.http_status == 301 and not self.token and project["repo"] not in self.public_checks:
                try:
                    self._require_public(project["repo"], verify_anonymous=True)
                except Unavailable:
                    pass
                else:
                    if self.active_repo(project["repo"]) != project["repo"]:
                        return self.page(project, kind, number, since=since)
            if kind == "pr" and e.http_status == 404 and not self.token:
                try:
                    self._require_public(project["repo"], verify_anonymous=True)
                    self.require_feed(project["repo"], kind)
                except FeedDisabled as disabled:
                    e = disabled
                except Unavailable:
                    pass
            if isinstance(e, FeedDisabled):
                return cached or [], False, "disabled", row[1] if cached is not None else None, e
            if cached is not None:
                return cached, row[3], "stale", row[1], e
            return [], False, "error", None, e


def _status(states):
    states = set(states)
    if states == {"disabled"}:
        return "disabled"
    if states <= {"live", "cached"}:
        return "ok"
    if states == {"stale"}:
        return "stale"
    if states == {"error"}:
        return "error"
    return "partial"


def collection_order(project, attempts=None):
    attempt = attempts.get(project["slug"]) if attempts is not None else project.get("last_attempt")
    stamp = _timestamp(attempt or project.get("last_success"))
    priority = project.get("priority", 0)
    return stamp, -(priority if type(priority) is int else 0), project["slug"]


def source_failure(warning):
    if not warning:
        return None
    return {"reason": warning.reason, "http_status": warning.http_status, "message": str(warning),
            "retry_at": warning.retry_at}


def collect(projects: list[dict], db_path: Path, *, refresh=False, pages=1) -> dict:
    """Collect recent issue, PR, commit and workflow-run metadata.

    Input projects use slug (or id) and repo (or repository/repo_full_name) as owner/name.
    The response contains normalized items, human-readable warnings, and augmented projects
    with sync_status, last_success (latest known successful page time in UTC), and per-kind sources.
    Existing cached pages remain available if an endpoint fails. An item's fetched_at is the
    UTC time when its response body arrived, retained across stale reads and HTTP 304 responses.
    Repository-level access failures are separate from the per-kind cached result states.
    The caller owns catalog storage.
    """
    if type(pages) is not int or not 1 <= pages <= 5:
        raise ValueError("pages must be an integer from 1 to 5")
    checked = [_project(entry) for entry in projects]
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path, timeout=8)
    result = {"items": [], "warnings": [], "projects": []}
    try:
        # A recent sweep requests four endpoint kinds per repository.
        sync = _Sync(db, refresh, checked, time_budget=90)
        # With a shared time limit, fixed seed order can starve the same repositories on every sweep.
        for project in sorted(checked, key=collection_order):
            source_data = {}
            first_pages = []
            results = []
            seen = set()
            for kind in ("issue", "pr", "commit", "test"):
                states, times, attempts = [], [], []
                failures = []
                count = 0
                for index in range(1, pages + 1):
                    items, has_next, state, stamp, warning = sync.page(project, kind, index)
                    if index == 1 and kind != "issue":
                        first_pages.append((state, warning))
                    states.append(state)
                    if state == "live" or (warning and warning.attempted):
                        attempts.append(time.time())
                    if stamp is not None:
                        times.append(stamp)
                    for item in items:
                        key = (kind, item["source_id"])
                        if key not in seen:
                            seen.add(key)
                            # Multiple project slugs may refer to the same API repository.
                            results.append({
                                **_validated_item(item, stamp), "project": project["slug"],
                                "fetched_at": item.get("fetched_at") or _utc(stamp),
                            })
                            count += 1
                    if warning:
                        failures.append(source_failure(warning))
                        if state != "disabled":
                            fallback = " (using stale cache)" if state == "stale" else ""
                            result["warnings"].append(f"{project['repo']} {kind} page {index}: {warning}{fallback}")
                        # Leave the next page and cursor for recovery instead of repeating a failed request.
                        break
                    if not has_next:
                        break
                source_data[kind] = {
                    "sync_status": _status(states),
                    "last_success": _utc(max(times, default=None)),
                    "last_attempt": _utc(max(attempts, default=None)),
                    "item_count": count,
                    "pages_checked": len(states),
                    "pages_confirmed": sum(state in {"live", "cached"} for state in states),
                    "more_available": bool(has_next),
                    "errors": failures,
                }
            flags = {source["sync_status"] for source in source_data.values()} - {"disabled"}
            status = next(iter(flags), "ok") if len(flags) <= 1 else "partial"
            access = sync.public_access(project["repo"], first_pages)
            if access is False or (access is None and project.get("sync_status") == "unavailable"):
                status = "unavailable"
            result["projects"].append({
                **project,
                "sync_status": status,
                "last_success": max((x["last_success"] for x in source_data.values() if x["last_success"]),
                                    default=None),
                "last_attempt": max((x["last_attempt"] for x in source_data.values() if x["last_attempt"]),
                                    default=None),
                "availability": ("unavailable" if status == "unavailable" else
                                 "archived" if sync.repository_metadata.get(project["repo"], {}).get("archived") is True
                                 else "public" if access else project.get("availability", "unknown")),
                "github_id": _number(sync.repository_metadata.get(project["repo"], {}).get("id"))
                             or project.get("github_id"),
                "current_repo": sync.active_repo(project["repo"]),
                "sources": source_data,
            })
            result["items"].extend(results)
    finally:
        db.close()
    return result


def _history_table(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS github_history (
            slug TEXT NOT NULL,
            repo TEXT NOT NULL,
            mode TEXT NOT NULL,
            revision INTEGER NOT NULL,
            next_page INTEGER NOT NULL,
            complete INTEGER NOT NULL,
            started_at INTEGER NOT NULL,
            since INTEGER,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (slug, repo, mode)
        )
    """)


def _history_db(db_path):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=8)
    db.row_factory = sqlite3.Row
    _history_table(db)
    return db


def backfill_status(db_path: Path, *, mode="backfill") -> list[dict]:
    """Read persisted backfill (or incremental) cursor state per project."""
    with closing(_history_db(db_path)) as db:
        rows = db.execute("SELECT * FROM github_history WHERE mode=? ORDER BY slug, repo", (mode,)).fetchall()
    return [
        {"slug": row["slug"], "repo": current_repository(row["repo"]), "mode": row["mode"], "next_page": row["next_page"],
         "complete": bool(row["complete"]), "since": _utc(row["since"]),
         "started_at": _utc(row["started_at"]), "updated_at": _utc(row["updated_at"])}
        for row in rows
    ]


def revision_references(records, *, sources=(), limit=PAIR_CHECK_LIMIT):
    """Choose a bounded set of exact PR lookups from already indexed leads."""
    index = RelatedIndex(records)
    origins = [canonical_url(source) for source in sources] or [None]
    selected = set(origins)
    targets = []
    for origin in origins:
        for match in index.matches({}, origin=origin, limit=250):
            for side in ("left", "right"):
                url = canonical_url(match[side]["url"])
                row = index.rows[url]
                if url not in selected and row["kind"] == "pr" and not source_revision(row):
                    targets.append(row["url"])
                    selected.add(url)
                    if len(targets) >= limit:
                        return targets
    return targets


def find_public_projects(db_path, queries):
    """Return bounded names from successful, complete searches of public repositories."""
    result = {}
    with closing(sqlite3.connect(db_path, timeout=8)) as db:
        sync = _Sync(db, False)
        for key, query in queries.items():
            params = urlencode({"q": f"{query} is:public archived:false fork:false", "per_page": 10})
            try:
                raw, _ = sync._request(f"{API}/search/repositories?{params}", "search", None)
            except Unavailable:
                continue
            response = _object(raw)
            items = response.get("items")
            if response.get("incomplete_results") is not False or not isinstance(items, list):
                continue
            result[key] = [item["full_name"] for item in items[:10] if isinstance(item, dict)
                           and item.get("private") is False and item.get("visibility", "public") == "public"
                           and item.get("archived") is False and item.get("fork") is False
                           and isinstance(item.get("full_name"), str) and REPO.fullmatch(item["full_name"])]
    return result


def find_public_forks(catalog, projects, *, limit=4):
    """Return bounded candidate links from a rotating slice of tracked parents."""
    checked = sorted((_project(project) for project in projects
                      if project.get("availability") == "public"), key=lambda project: project["slug"])
    if not checked:
        return None
    batch = min(limit, len(checked))
    offset = (int(time.time()) // 3600 * batch) % len(checked)
    selected = (checked + checked)[offset:offset + batch]
    candidates = set()
    with closing(sqlite3.connect(catalog.path, timeout=8)) as db:
        sync = _Sync(db, False, time_budget=20)
        for project in selected:
            repo = project["repo"]
            try:
                sync._require_public(repo)
                raw, _ = sync._request(f"{API}/repos/{repo}/forks?per_page=10&sort=newest", "core", None)
            except Unavailable:
                return None
            if not isinstance(raw, list) or len(raw) > 10:
                return None
            for entry in raw:
                row = _object(entry)
                name = row.get("full_name")
                if (row.get("private") is False and row.get("visibility", "public") == "public"
                        and isinstance(name, str) and REPO.fullmatch(name)):
                    candidates.add(name)
    return candidates


def public_source_revisions(db_path, sources):
    """Check exact, approved public PR or commit URLs without indexing their contents."""
    from .exchange_fields import REVISION, _source

    revisions = {}
    with closing(sqlite3.connect(db_path, timeout=8)) as db:
        sync = _Sync(db, False)
        for source in sources:
            parts = urlsplit(_source(source)).path.strip("/").split("/")
            owner, repo, kind, ident = parts
            endpoints = {"pull": "pulls", "commit": "git/commits"}
            if kind not in endpoints:
                raise ValueError("use a pull request or commit")
            name = current_repository(f"{owner}/{repo}")
            revisions[source] = None
            try:
                sync._require_public(name)
                raw, _ = sync._request(f"{API}/repos/{name}/{endpoints[kind]}/{ident}", "core", None)
            except Unavailable:
                continue
            data = _object(raw)
            if kind == "pull":
                if _number(data.get("number")) != int(ident):
                    continue
                revision = _sha(_object(data.get("head")).get("sha"))
            else:
                revision = _sha(data.get("sha"))
                if revision != ident.casefold():
                    continue
            if REVISION.fullmatch(revision or ""):
                revisions[source] = revision
    return revisions


def refresh_references(projects, db_path, references, *, refresh=False, skip_unavailable=False, anonymous=False):
    """Recheck exact public Issue, PR and CI links already in reviewed cards."""
    checked = [_project(project) for project in projects]
    by_repo = {project["repo"].lower(): project for project in checked}
    watched = {}
    for url in references:
        parsed = urlsplit(url)
        parts = parsed.path.strip("/").split("/")
        if parsed.scheme != "https" or parsed.netloc != "github.com" or len(parts) < 4:
            continue
        project = by_repo.get(current_repository("/".join(parts[:2])).lower())
        if not project:
            continue
        path = "/".join(parts[2:])
        match = re.fullmatch(r"(issues|pull)/([1-9][0-9]*)|actions/runs/([1-9][0-9]*)(?:/job/([1-9][0-9]*))?", path)
        if not match:
            continue
        collection, number, run, job = match.groups()
        if collection:
            kind = "pr" if collection == "pull" else "issue"
            endpoint = f"{'pulls' if kind == 'pr' else 'issues'}/{number}"
        else:
            kind = "test"
            endpoint = f"actions/jobs/{job}" if job else f"actions/runs/{run}"
        repo = project["repo"]
        target = f"https://github.com/{repo}/{path}"
        watched[target] = (project, kind, f"{API}/repos/{repo}/{endpoint}", run, job)

    result = {"items": [], "warnings": [], "references": []}
    with closing(sqlite3.connect(db_path, timeout=8)) as db:
        sync = _Sync(db, refresh, checked, anonymous=anonymous)
        for target, (project, kind, endpoint, run, job) in watched.items():
            cached = db.execute("SELECT etag, fetched_at, items FROM github_cache WHERE url=?", (endpoint,)).fetchone()
            try:
                cached_items = json.loads(cached[2]) if cached else []
            except (TypeError, ValueError):
                cached_items, cached = [], None
            if not isinstance(cached_items, list):
                cached_items, cached = [], None
            if skip_unavailable and project.get("sync_status") == "unavailable":
                result["references"].append({"url": target, "status": "retained", "reason": "repository_unavailable"})
                continue
            current_schema = cached and _current_signatures(cached_items, kind)
            if current_schema and cached[1] + CACHE_TTL > time.time() and not refresh:
                result["items"].extend(_validated_item(item, cached[1]) for item in cached_items)
                continue
            checked_at = cached[1] if current_schema else None
            try:
                sync._require_public(project["repo"])
                sync.require_reference_feed(project["repo"], kind)
                raw, headers = sync._request(endpoint, "core", cached[0] if current_schema else None)
                now = time.time()
                if raw is NOT_MODIFIED and current_schema:
                    items, etag = cached_items, _etag(headers.get("ETag")) or cached[0]
                elif isinstance(raw, dict):
                    item = _item(raw, kind, project, sync.repositories)
                    if not item or (job and (str(raw.get("id")) != job or str(raw.get("run_id")) != run)):
                        raise Unavailable("GitHub returned a different source")
                    if job:
                        item["source_id"] = f"job-{job}"
                        item["metadata"]["scope"] = "workflow_job"
                    elif item["url"].lower() != target.lower():
                        raise Unavailable("GitHub returned a different source")
                    item.update(url=target, fetched_at=_utc(now))
                    items, etag = [item], _etag(headers.get("ETag"))
                else:
                    raise Unavailable("GitHub returned unexpected source data")
                with db:
                    db.execute("""INSERT INTO github_cache VALUES (?, ?, ?, ?, 0)
                                  ON CONFLICT(url) DO UPDATE SET etag=excluded.etag, fetched_at=excluded.fetched_at,
                                  items=excluded.items""", (endpoint, etag, now, json.dumps(items, ensure_ascii=True)))
                checked_at = now
            except Unavailable as error:
                result["warnings"].append(f"{target}: {error}")
                result["references"].append({"url": target, "status": "retained" if cached_items else "unavailable",
                                             **source_failure(error)})
                items = cached_items
            result["items"].extend(_validated_item(item, checked_at) for item in items)
    return result


def _history_anchor_table(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS github_history_anchor (
            slug TEXT NOT NULL,
            repo TEXT NOT NULL,
            mode TEXT NOT NULL,
            members TEXT NOT NULL,
            PRIMARY KEY (slug, repo, mode)
        )
    """)


def _history_cursor(db, project, mode, started):
    slug, repo = project["slug"], repository_identity(project["repo"])
    lookup = """SELECT github_history.*, github_history_anchor.members FROM github_history
                LEFT JOIN github_history_anchor USING (slug, repo, mode)
                WHERE slug=? AND repo=? AND mode=?"""
    previous = db.execute(lookup, (slug, repo, mode)).fetchone()
    since = None
    if mode == "incremental":
        historical = db.execute(lookup, (slug, repo, "backfill")).fetchone()
        since = (historical["started_at"] - UPDATE_OVERLAP if historical
                 else (previous["started_at"] if previous else started) - INITIAL_UPDATE_WINDOW)
    if previous is not None:
        cursor = dict(previous)
        members = cursor.pop("members")
        saved = json.loads(members) if members else None
        version = saved.get("signature_version") if isinstance(saved, dict) else None
        if saved is None or (mode == "backfill" and version != SIGNATURE_VERSION):
            # Replay history in bounded batches so old bodies can supply the
            # newly indexed signatures. Previously saved observations stay readable.
            cursor.update(next_page=1, complete=False, since=since, anchor=[])
        else:
            cursor["anchor"] = saved["members"] if isinstance(saved, dict) else saved
        return cursor
    return {"slug": slug, "repo": repo, "mode": mode, "revision": 0, "next_page": 1,
            "complete": False, "started_at": started, "since": since, "updated_at": started, "anchor": []}


def _page_members(items, mode):
    return [[item["kind"], item["source_id"], item["updated_at"] if mode == "incremental" else ""]
            for item in items]


def _advance_incremental(cursor, items, has_next, started):
    since = cursor["since"]
    latest = max((_timestamp(item["updated_at"]) for item in items), default=0)
    cutoff = started - UPDATE_OVERLAP
    if not has_next:
        cursor.update(next_page=1, since=max(since, cutoff))
        return False

    # Move by time on ordinary pages: offset pagination over an editable list
    # can skip entries when an earlier issue is updated between requests. Keep
    # the final timestamp in scope because multiple issues can share a second.
    boundary = min(latest - 1, cutoff)
    if boundary > since:
        cursor.update(next_page=1, since=boundary)
    else:
        # Several pages can share the same timestamp. Walk those pages without
        # advancing the time boundary until the timestamp group has been read.
        cursor["next_page"] += 1
    return True


def _collect_history(projects, db_path, *, mode, pages):
    if type(pages) is not int or not 1 <= pages <= 50:
        raise ValueError("pages must be an integer from 1 to 50")
    checked = [_project(entry) for entry in projects]
    result = {"items": [], "warnings": [], "projects": [], "checkpoint": [], "history": []}
    started = int(time.time())
    with closing(_history_db(db_path)) as db:
        sync = _Sync(db, True, checked)
        _history_anchor_table(db)
        attempts = {}
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='history_sync'").fetchone():
            attempts = {row["slug"]: json.loads(row["payload"]).get("last_attempt") for row in
                        db.execute("SELECT slug, payload FROM history_sync WHERE mode=?", (mode,))}
        for project in sorted(checked, key=lambda project: collection_order(project, attempts)):
            cursor = _history_cursor(db, project, mode, started)
            if cursor["complete"]:
                result["history"].append({"slug": project["slug"], "status": "complete", "warning": None})
                result["projects"].append({**project, "sync_status": "ok", "last_success": _utc(cursor["updated_at"]),
                                           "sources": {}})
                continue
            states, times, records = [], [], {}
            last_attempt = None
            last_error = None
            failure = None
            checkpoint_changed = False
            for _ in range(pages):
                number = cursor["next_page"]
                items, has_next, state, stamp, warning = sync.page(
                    project, "repository_issues", number, since=cursor["since"],
                )
                states.append(state)
                if state == "live" or (warning and warning.attempted):
                    last_attempt = _utc(time.time())
                if stamp is not None:
                    times.append(stamp)
                for item in items:
                    key = (item["kind"], item["source_id"])
                    previous = records.get(key)
                    if previous is None or item["updated_at"] >= previous["updated_at"]:
                        records[key] = {**item, "project": project["slug"],
                                        "fetched_at": item.get("fetched_at") or _utc(stamp)}
                if warning:
                    result["warnings"].append(f"{project['repo']} {mode} page {number}: {warning}")
                    failure = str(warning)
                    last_error = source_failure(warning)
                    break
                if number > 1:
                    prior, _, _, _, boundary_error = sync.page(
                        project, "repository_issues", number - 1, since=cursor["since"],
                    )
                    if boundary_error or _page_members(prior, mode) != cursor["anchor"]:
                        if not boundary_error:
                            cursor.update(next_page=1, anchor=[])
                            checkpoint_changed = True
                        reason = str(boundary_error) if boundary_error else "page boundary changed; will replay the current window"
                        result["warnings"].append(f"{project['repo']} {mode} page {number}: {reason}")
                        failure = reason
                        last_error = source_failure(boundary_error) or {"reason": "changing_page", "message": reason}
                        states[-1] = "partial"
                        has_next = True
                        break
                if mode == "backfill":
                    cursor.update(next_page=number + 1, complete=not has_next)
                else:
                    has_next = _advance_incremental(cursor, items, has_next, started)
                cursor["anchor"] = _page_members(items, mode) if cursor["next_page"] > 1 else []
                checkpoint_changed = True
                if not has_next:
                    break
            if checkpoint_changed:
                result["checkpoint"].append({**cursor, "updated_at": started})
            source_status, success = _status(states), _utc(max(times, default=None))
            history_status = ("unavailable" if failure and source_status in {"error", "stale"}
                              else "partial" if failure or has_next else "complete")
            result["history"].append({"slug": project["slug"], "status": history_status,
                                      "next_page": cursor["next_page"], "warning": failure,
                                      "last_attempt": last_attempt, "last_success": success, "error": last_error})
            source = {
                "sync_status": source_status, "last_success": success, "pages_checked": len(states),
                "more_available": not cursor["complete"] if mode == "backfill" else bool(has_next),
            }
            result["projects"].append({
                **project, "sync_status": source_status, "last_success": success,
                "sources": {
                    kind: {**source, "item_count": sum(item_key[0] == kind for item_key in records)}
                    for kind in ("issue", "pr")
                },
            })
            result["items"].extend(records.values())
    return result


def backfill(projects: list[dict], db_path: Path, *, pages=1) -> dict:
    """Read up to pages per project from oldest to newest, without advancing the cursor.

    The repository endpoint includes issues and PRs sorted by creation date.
    A changed page boundary causes a replay before confirming the end.
    Save the returned observations before calling commit_backfill. Repeating a
    batch after a crash is safe when the caller upserts by observation ID.
    """
    return _collect_history(projects, db_path, mode="backfill", pages=pages)


def incremental(projects: list[dict], db_path: Path, *, pages=1) -> dict:
    """Read updated issues and PRs with a time cursor and a short replay overlap.

    Starts at the first existing backfill batch time with overlap, or 24 hours
    ago on first use. Save observations before committing its checkpoint.
    """
    return _collect_history(projects, db_path, mode="incremental", pages=pages)


def commit_backfill(db_path: Path, checkpoint: list[dict]) -> None:
    """Commit progress only after the caller has durably upserted observations.

    A revision check lets concurrent or repeated saves replay observations
    without allowing a late writer to roll back a project's cursor.
    """
    if not checkpoint:
        return
    with closing(_history_db(db_path)) as db, db:
        _history_anchor_table(db)
        for cursor in checkpoint:
            changed = db.execute("""INSERT INTO github_history VALUES
                (:slug, :repo, :mode, :revision + 1, :next_page, :complete, :started_at, :since, :updated_at)
                ON CONFLICT(slug, repo, mode) DO UPDATE SET
                    revision=excluded.revision, next_page=excluded.next_page, complete=excluded.complete,
                    since=excluded.since, updated_at=excluded.updated_at
                WHERE github_history.revision = :revision""", cursor).rowcount
            if changed:
                anchor = {"members": cursor["anchor"], "signature_version": SIGNATURE_VERSION}
                db.execute("""INSERT INTO github_history_anchor VALUES (?, ?, ?, ?)
                    ON CONFLICT(slug, repo, mode) DO UPDATE SET members=excluded.members""",
                    (cursor["slug"], cursor["repo"], cursor["mode"], json.dumps(anchor)))
