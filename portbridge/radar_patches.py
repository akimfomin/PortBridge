"""Bounded fingerprints of immutable public commit diffs."""

import shutil
from subprocess import TimeoutExpired
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from .github import NoRedirect, REPO
from .matching import canonical_url, current_repository, source_revision
from .patch_identity import MAX_PATCH, patch_bytes

PROBES = 4
RETRY = 24 * 3600


def digest_commit(repo, revision, git):
    req = Request(f"https://github.com/{repo}/commit/{revision}.diff",
                  headers={"User-Agent": "PortBridge/0.1 read-only pinned diff"})
    with build_opener(NoRedirect()).open(req, timeout=2.5) as response:
        data = response.read(MAX_PATCH + 1)
    if b"diff --git " not in data:
        raise ValueError("No unified Git diff")
    return patch_bytes(data, git)


def apply_cached(rows, cached):
    for row in rows.values():
        revision = source_revision(row)
        if revision and (saved := cached.get(revision)) and saved[0]:
            row["metadata"].update(patch_id=saved[0], patch_revision=revision)


def sample(catalog, changed, rows, cached, now):
    git = shutil.which("git")
    if not git:
        return 0
    scope = []
    for _, row, _ in changed:
        terms = row["metadata"].get("technical") or {}
        for value in terms.get("references", []):
            peer = rows.get(canonical_url(value))
            if peer is not None and row["project"] != peer["project"]:
                scope.extend((row, peer))
    probes = {}
    for row in scope:
        rev = source_revision(row)
        slug = "/".join(urlsplit(row["url"]).path.split("/")[1:3])
        if rev and REPO.fullmatch(slug) and (rev not in cached or not cached[rev][0] and cached[rev][1] + RETRY <= now):
            probes.setdefault(rev, current_repository(slug))
        if len(probes) >= PROBES:
            break
    for rev, slug in probes.items():
        try:
            digest = digest_commit(slug, rev, git)
        except (OSError, ValueError, TimeoutExpired):
            digest = None
        cached[rev] = (digest, now)
    with catalog.connect() as db:
        db.executemany("REPLACE INTO radar_patch_cache VALUES(?,?,?)",
                       [(rev, *cached[rev]) for rev in probes])
    apply_cached(rows, cached)
    return len(probes)
