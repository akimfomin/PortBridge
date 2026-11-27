"""Select public source files from reviewed directories in an immutable Git tree."""

from hashlib import sha256
import json
import os
from pathlib import PurePosixPath
import re
from urllib.request import Request, build_opener

MAX_TREE_BYTES = 4_000_000
MAX_FILE_BYTES = 1_150_000
MAX_SELECTED = 16
CACHE = "code-tree-selection-v4:"
BLOB_SHA = re.compile(r"[0-9a-f]{40}")
SOURCE_PATH = re.compile(r"(?:[A-Za-z0-9_-][A-Za-z0-9_+.-]*/)*[A-Za-z0-9_-][A-Za-z0-9_+.-]*")
EXTENSIONS = {".c", ".cpp", ".h", ".hpp", ".rs", ".py", ".adoc", ".rst"}
FAMILIES = tuple(re.compile(pattern) for pattern in (
    r"wsi|present|surface|swapchain", r"sync|semaphore|fence|barrier",
    r"shader|pipeline|wave", r"memory|resource|heap", r"descriptor|binding",
    r"render|image|texture|vertex", r"command|queue|copy",
    r"validat|regression|replay", r"hoist|licm|optimizer|optimize",
    r"renderpass|render_pass", r"interface|layout", r"subgroup|builtin", r"^resources?$",
    r"vertex", r"builtin", r"timeline",
))
EXCLUDE = re.compile(r"(?:^|[/_.-])(?:generated|headers|external|third.party|vendor|secret|keys?|auth|drm)(?:$|[/_.-])", re.I)


def cache_key(group):
    rules = json.dumps([group["directories"], group["limit"], group["files"], group.get("scoped", False)],
                       sort_keys=True).encode()
    suffix = sha256(rules).hexdigest()[:12]
    return f"{CACHE}{group['repo']}@{group['revision']}:{suffix}"


def valid_file(group, path):
    return (isinstance(path, str) and SOURCE_PATH.fullmatch(path)
            and any(path.startswith(directory + "/") and not EXCLUDE.search(path[len(directory) + 1:])
                    for directory in group["directories"])
            and PurePosixPath(path).suffix in EXTENSIONS)


def _fetch_tree(repo, sha, *, recursive):
    from .github import NoRedirect
    suffix = "?recursive=1" if recursive else ""
    address = f"https://api.github.com/repos/{repo}/git/trees/{sha}{suffix}"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "PortBridge-readonly-code-index"}
    token = os.environ.get("PORTBRIDGE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    with build_opener(NoRedirect()).open(Request(address, headers=headers), timeout=8) as response:
        body = response.read(MAX_TREE_BYTES + 1)
    if len(body) > MAX_TREE_BYTES:
        raise ValueError("Source tree exceeds the response budget")
    tree = json.loads(body)
    if not isinstance(tree, dict) or tree.get("truncated") is not False or not isinstance(tree.get("tree"), list):
        raise ValueError("Incomplete Git tree")
    return tree


def fetch_tree(group):
    repo, revision = group["repo"], group["revision"]
    if not group.get("scoped"):
        return _fetch_tree(repo, revision, recursive=True)

    # GitHub can truncate a large recursive tree. Walk only reviewed paths
    # and cache each common parent for the duration of this scope refresh.
    known = {}
    files = []
    for directory in group["directories"]:
        sha = revision
        for part in directory.split("/"):
            if sha not in known:
                known[sha] = {row["path"]: row["sha"] for row in _fetch_tree(repo, sha, recursive=False)["tree"]
                              if row.get("type") == "tree" and BLOB_SHA.fullmatch(row.get("sha", ""))}
            sha = known[sha].get(part)
            if not sha:
                raise ValueError("Approved source directory missing at the pinned revision")
        files.extend({**row, "path": f"{directory}/{row['path']}"}
                     for row in _fetch_tree(repo, sha, recursive=True)["tree"] if row.get("type") == "blob")
    return {"tree": files, "truncated": False}


def select(group, tree):
    if not isinstance(tree, dict) or tree.get("truncated") is not False or not isinstance(tree.get("tree"), list):
        raise ValueError("Incomplete Git tree")
    candidates = []
    excluded = set(group.get("already_indexed", ()))
    for entry in tree["tree"]:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        size = entry.get("size")
        digest = entry.get("sha")
        if (entry.get("type") != "blob" or entry.get("mode") != "100644"
                or not valid_file(group, path) or path in excluded or type(size) is not int
                or not 0 < size <= MAX_FILE_BYTES or not isinstance(digest, str) or not BLOB_SHA.fullmatch(digest)):
            continue
        stem = PurePosixPath(path).stem.casefold()
        families = [index for index, pattern in enumerate(FAMILIES) if pattern.search(stem)]
        if families:
            candidates.append((len(stem), path.count("/"), path, digest, families))
    ranked = sorted(candidates)
    selected = {}
    for family in range(len(FAMILIES)):
        best = next((row for row in ranked if family in row[-1]), None)
        if best:
            selected[best[2]] = best[3]
    for _, _, path, digest, _ in ranked:
        if len(selected) >= group["limit"]:
            break
        selected.setdefault(path, digest)
    return [{"path": path, "blob": digest} for path, digest in list(selected.items())[:group["limit"]]]
