"""Record publication freshness and verify that GitHub Pages serves this build."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from time import sleep
from urllib.request import Request, urlopen

from .activity import source_time
from .backup import checkpoint_count
from .export import VERSIONED_SNAPSHOTS


PUBLIC_DATA = "https://akimfomin.github.io/PortBridge/data/"
FILES = ("site", "lab")
STALE_AFTER_MINUTES = 90
VERIFY_DELAYS = (0, 2, 4, 8, 16, 24, 32)


def public_snapshot(name, cache_key=None):
    suffix = f"?portbridge={cache_key}" if cache_key else ""
    request = Request(f"{PUBLIC_DATA}{name}.json{suffix}", headers={
        "Accept": "application/json", "Accept-Encoding": "identity", "Cache-Control": "no-cache",
        "User-Agent": "PortBridge-Pages-Verification",
    })
    return urlopen(request, timeout=5)


def checksum(stream):
    digest = sha256()
    for chunk in iter(lambda: stream.read(64 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def publication_freshness(generated_at, now):
    generated = source_time(generated_at)
    if generated is None or (now - generated).total_seconds() < -300:
        return "unavailable", ""
    age_minutes = max(0, int((now - generated).total_seconds() / 60))
    status = "stale" if age_minutes >= STALE_AFTER_MINUTES else "fresh"
    return status, generated.isoformat(timespec="seconds")


def output_value(key, value):
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        print(f"{key}={value}", file=output)


def write_summary(*lines):
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
        print(*lines, sep="\n", file=summary)


def probe_publication():
    payload = {}
    try:
        with public_snapshot("site") as response:
            # The manifest contains release metadata, not the search index.
            payload = json.loads(response.read(64 * 1024))
    except (OSError, ValueError, HTTPException):
        pass
    stamp = payload.get("generated_at") if isinstance(payload, dict) else None
    status, generation = publication_freshness(stamp, datetime.now(timezone.utc))
    previous_count = ""
    try:
        name = (payload.get("snapshots", {}).get("health") if isinstance(payload, dict)
                and isinstance(payload.get("snapshots"), dict) else None)
        name = name.removesuffix(".json") if isinstance(name, str) and re.fullmatch(r"health-[a-f0-9]{24}\.json", name) else "health"
        with public_snapshot(name) as response:
            health = json.loads(response.read(1024 * 1024))
        count = health.get("observation_count") if isinstance(health, dict) else None
        if type(count) is int and count >= 0:
            previous_count = str(count)
    except (OSError, ValueError, HTTPException):
        pass
    output_value("previous_status", status)
    output_value("previous_generation", generation)
    output_value("previous_count", previous_count)
    write_summary("## GitHub Pages before this build",
                  f"- Publication freshness: {status} (stale after {STALE_AFTER_MINUTES} minutes)",
                  f"- Previous public snapshot time: {generation or 'unavailable'}")
    if status == "stale":
        print(f"::warning::The previous public snapshot is at least {STALE_AFTER_MINUTES} minutes old.")


def publication_guard(previous_count, health):
    candidate = health.get("observation_count")
    if type(previous_count) is not int or previous_count < 0:
        return False, "Previous public observation count is unavailable."
    if type(candidate) is not int or candidate < previous_count:
        return False, f"Candidate has {candidate} observations; the public snapshot has {previous_count}."
    return True, f"Retained {candidate} observations against {previous_count} in the previous snapshot."


def guard_export():
    health = json.loads(Path("dist/data/health.json").read_bytes())
    previous = os.environ.get("PORTBRIDGE_PREVIOUS_COUNT", "")
    try:
        previous = int(previous)
    except ValueError:
        previous = None
    ready, detail = publication_guard(previous, health)
    output_value("ready", str(ready).lower())
    write_summary("## Publication safeguard", f"- {detail}",
                  "- Proceeding with publication." if ready else "- Retaining the previous publication.")
    if not ready:
        print(f"::warning::{detail} Previous publication retained.")


def validate_checkpoint():
    minimum = os.environ.get("PORTBRIDGE_MIN_CHECKPOINT_COUNT", "0") or "0"
    try:
        count = checkpoint_count(os.environ["PORTBRIDGE_CHECKPOINT"])
        if count < int(minimum):
            raise ValueError("checkpoint has fewer observations than the current publication")
    except (OSError, sqlite3.Error, ValueError) as error:
        raise SystemExit(f"Catalog checkpoint unavailable: {error}") from error
    print(f"Validated public catalog checkpoint with {count} observations.")


def schedule_gaps(runs):
    times = sorted(value for row in runs if isinstance(row, dict)
                   if (value := source_time(row.get("createdAt"))) is not None)
    return [round((second - first).total_seconds() / 60, 1) for first, second in zip(times, times[1:])]


def summarize_operations():
    health = json.loads(Path("dist/data/health.json").read_bytes())
    age = health["source_totals"]["age"]
    lines = ["## GitHub source and schedule health",
             f"- Source data under two hours old: {age.get('fresh', 0)} of {len(health['sources'])}",
             f"- Older or unknown: {age.get('stale', 0)} / {age.get('unknown', 0)}",
             f"- Last successful GitHub data: {health.get('last_success') or 'unknown'}",
             f"- Snapshot generated: {health['publication']['generated_at']}"]
    try:
        runs = json.loads(Path(".portbridge/scheduled-runs.json").read_bytes())
    except (OSError, ValueError):
        runs = []
    gaps = schedule_gaps(runs) if isinstance(runs, list) else []
    if gaps:
        lines.append(f"- Recent scheduled intervals in minutes: {', '.join(map(str, gaps))} (configured: 30)")
    else:
        lines.append("- Scheduled intervals: unknown")
    write_summary(*lines)


def record_export():
    for name in FILES:
        with Path(f"dist/data/{name}.json").open("rb") as stream:
            output_value(f"{name}_sha256", checksum(stream))


def verify_publication(expected, request=public_snapshot, pause=sleep):
    """Retry both canonical public files during brief deployment propagation."""
    remaining = FILES
    for delay in VERIFY_DELAYS:
        if delay:
            pause(delay)
        matches = []
        for name in FILES:
            try:
                with request(name) as response:
                    if checksum(response) == expected[name]:
                        matches.append(name)
            except (OSError, HTTPException):
                continue
        remaining = tuple(name for name in FILES if name not in matches)
        if not remaining:
            break
    return remaining


def verify_linked_snapshots(site_sha256, request=public_snapshot):
    """Verify the immutable files read by browsers for the published generation."""
    with request("site") as response:
        manifest = response.read(64 * 1024 + 1)
    if len(manifest) > 64 * 1024 or sha256(manifest).hexdigest() != site_sha256:
        return ("site",)
    site = json.loads(manifest)
    assets = site.get("snapshots", {})
    pointer = site.get("browse_index", {})
    generation = pointer.get("generation", "")
    expected = set(VERSIONED_SNAPSHOTS)
    if (set(assets) not in (expected, expected - {"source-code"}) or pointer.get("version") != 1
            or not isinstance(generation, str) or not re.fullmatch(r"[0-9a-f]{24}", generation)):
        return ("site manifest",)

    def check(name):
        file = assets[name]
        match = re.fullmatch(rf"{name}-([0-9a-f]{{24}})\.json", file) if isinstance(file, str) else None
        if match is None:
            return name
        try:
            with request(file.removesuffix(".json")) as response:
                return None if checksum(response).startswith(match[1]) else name
        except (OSError, HTTPException):
            return name

    with ThreadPoolExecutor(max_workers=4) as executor:
        failed = [name for name in executor.map(check, assets) if name]
    try:
        with request(f"browse-{generation}-index") as response:
            browse = json.loads(response.read(64 * 1024))
        if (browse.get("generation") != generation or browse.get("version") != 1
                or set(browse.get("kinds", {})) != {"matches", "sources"}):
            failed.append("browse index")
    except (OSError, ValueError, HTTPException):
        failed.append("browse index")
    search = site.get("search_index") or {}
    if "manifest" in search:
        generation = search.get("generation")
        name = search.get("manifest")
        if (not isinstance(generation, str) or not re.fullmatch(r"[0-9a-f]{24}", generation)
                or name != f"preflight-{generation}-index.json"):
            failed.append("search manifest")
        else:
            try:
                with request(name.removesuffix(".json")) as response:
                    index = json.loads(response.read(64 * 1024))
                if index.get("version") != 1 or index.get("generation") != generation:
                    failed.append("search manifest")
            except (OSError, ValueError, AttributeError, HTTPException):
                failed.append("search manifest")
    return tuple(failed)


def verify_export():
    expected = {name: os.environ[f"EXPECTED_{name.upper()}_SHA256"] for name in FILES}
    if not all(len(value) == 64 and all(char in "0123456789abcdef" for char in value)
               for value in expected.values()):
        raise SystemExit("The build did not record the expected public checksums.")
    previous = os.environ["PREVIOUS_STATUS"]
    def request(name):
        return public_snapshot(name, expected["site"][:24])

    failed = verify_publication(expected, request=request)
    if not failed:
        for delay in (0, 2, 4, 8):
            if delay:
                sleep(delay)
            try:
                failed = verify_linked_snapshots(expected["site"], request=request)
            except (OSError, ValueError, AttributeError, TypeError, HTTPException):
                failed = ("site manifest",)
            if not failed:
                break
    headline = "## GitHub Pages verification"
    if failed:
        write_summary(headline, "- Unverified public JSON: " + ", ".join(f"{name}.json" for name in failed))
        raise SystemExit("GitHub Pages did not return a consistent public snapshot.")
    write_summary(headline, "- Public site.json, lab.json and all linked snapshots match this build.",
                  f"- Previous public snapshot: {os.environ['PREVIOUS_GENERATION'] or 'unavailable'}")
    if previous == "stale":
        write_summary("- Publication recovered from a stale public snapshot.")


if __name__ == "__main__":
    commands = {"probe": probe_publication, "record": record_export, "guard": guard_export, "verify": verify_export,
                "checkpoint": validate_checkpoint, "ops": summarize_operations}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit("Usage: python -m portbridge.pages_health {probe,record,guard,verify,checkpoint,ops}")
    commands[sys.argv[1]]()
