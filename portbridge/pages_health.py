"""Record publication freshness and verify that GitHub Pages serves this build."""
from datetime import datetime, timezone
from hashlib import sha256
from http.client import HTTPException
import json
import os
from pathlib import Path
import sys
from time import sleep
from urllib.request import Request, urlopen

from .activity import source_time


PUBLIC_DATA = "https://akimfomin.github.io/PortBridge/data/"
FILES = ("site", "lab")
STALE_AFTER_MINUTES = 90
VERIFY_DELAYS = (0, 2, 4, 8, 16, 30)


def public_snapshot(name):
    request = Request(f"{PUBLIC_DATA}{name}.json", headers={
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
    output_value("previous_status", status)
    output_value("previous_generation", generation)
    write_summary("## GitHub Pages before this build",
                  f"- Publication freshness: {status} (stale after {STALE_AFTER_MINUTES} minutes)",
                  f"- Previous public snapshot time: {generation or 'unavailable'}")
    if status == "stale":
        print(f"::warning::The previous public snapshot is at least {STALE_AFTER_MINUTES} minutes old.")


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


def verify_export():
    expected = {name: os.environ[f"EXPECTED_{name.upper()}_SHA256"] for name in FILES}
    if not all(len(value) == 64 and all(char in "0123456789abcdef" for char in value)
               for value in expected.values()):
        raise SystemExit("The build did not record the expected public checksums.")
    previous = os.environ["PREVIOUS_STATUS"]
    failed = verify_publication(expected)
    headline = "## GitHub Pages verification"
    if failed:
        write_summary(headline, "- Unverified public JSON: " + ", ".join(f"{name}.json" for name in failed))
        raise SystemExit("GitHub Pages did not return the expected build for both public JSON files.")
    write_summary(headline, "- Public site.json and lab.json match this build.",
                  f"- Previous public snapshot: {os.environ['PREVIOUS_GENERATION'] or 'unavailable'}")
    if previous == "stale":
        write_summary("- Publication recovered from a stale public snapshot.")


if __name__ == "__main__":
    commands = {"probe": probe_publication, "record": record_export, "verify": verify_export}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit("Usage: python -m portbridge.pages_health {probe,record,verify}")
    commands[sys.argv[1]]()
