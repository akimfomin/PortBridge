"""Shared validation for private exchange data."""

from datetime import datetime, timezone
import re
from urllib.parse import urlsplit


TOKEN = re.compile(r"pbx_[A-Za-z0-9_-]{43}")
REVISION = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")
NUMBER = r"[1-9][0-9]{0,18}"
OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]{1,100}")
ISSUE_OR_PR = re.compile(rf"(?:issues|pull)/{NUMBER}")
ACTIONS = re.compile(rf"actions/runs/{NUMBER}(?:/(?:job|attempts)/{NUMBER})?")
COMMENT = re.compile(rf"(?:issuecomment-|discussion_r|pullrequestreview-){NUMBER}")
EXTERNAL_LINK = re.compile(r"(?i)(?:[a-z][a-z0-9+.-]*://|\bwww\.)")
MAX_SQL_INTEGER = (1 << 63) - 1


class AuthError(Exception):
    """A bearer token is absent or invalid."""


class PermissionDenied(AuthError):
    """An authenticated principal lacks permission for the operation."""


class Conflict(Exception):
    """The requested change conflicts with an existing record."""


def _timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds") if value is not None else None


def _text(value, label, limit, *, optional=False):
    if (not isinstance(value, str) or len(value) > limit or (value and not value.isprintable()) or
            EXTERNAL_LINK.search(value)):
        raise ValueError(f"{label} must be single-line text of at most {limit} characters without links")
    if TOKEN.search(value):
        raise ValueError(f"{label} must not include an exchange bearer token")
    normalized = value.strip()
    if not normalized and not optional:
        raise ValueError(f"{label} is required")
    return normalized


def _integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer between {low} and {high}")
    return value


def _source(value):
    if (not isinstance(value, str) or len(value) > 300 or not value.isascii() or
            any(not 33 <= ord(character) <= 126 for character in value)):
        raise ValueError("source_url must be a public GitHub issue, pull request, commit, or Actions permalink")
    parsed = urlsplit(value)
    parts = parsed.path.split("/", 3)
    if len(parts) != 4 or parts[0]:
        raise ValueError("source_url must be a public GitHub issue, pull request, commit, or Actions permalink")
    _, owner, repo, route = parts
    issue = ISSUE_OR_PR.fullmatch(route)
    commit = route.startswith("commit/") and REVISION.fullmatch(route[7:])
    if (parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or "?" in value or
            OWNER.fullmatch(owner) is None or REPOSITORY.fullmatch(repo) is None or repo in {".", ".."} or
            not (issue or commit or ACTIONS.fullmatch(route)) or
            ("#" in value and not (issue and COMMENT.fullmatch(parsed.fragment)))):
        raise ValueError("source_url must be a public GitHub issue, pull request, commit, or Actions permalink")
    return f"https://github.com/{owner}/{repo}/{route}" + (f"#{parsed.fragment}" if parsed.fragment else "")
