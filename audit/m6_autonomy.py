"""Measure scheduled deliveries and match verification receipts to their run attempts."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API = "https://api.github.com/repos/akimfomin/PortBridge/actions/"
RECEIPT = "portbridge-scheduled-publication-v1"


def stamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Use a timestamp with timezone")
    return parsed.astimezone(timezone.utc)


def pages(route, key, query, since):
    for page in range(1, 11):
        url = API + route + "?" + urlencode({**query, "per_page": 100, "page": page})
        with urlopen(Request(url, headers={"User-Agent": "PortBridge-public-autonomy-audit"}), timeout=20) as res:
            rows = json.load(res)[key]
        yield from rows
        if len(rows) < 100 or min(stamp(row["created_at"]) for row in rows) < since:
            return
    raise ValueError("API page budget reached; observed coverage is incomplete")


def checked_receipt(run, artifact_id, payload, now):
    if (not isinstance(payload, dict) or payload.get("GITHUB_RUN_ID") != str(run["id"])
            or type(run.get("run_attempt")) is not int
            or payload.get("GITHUB_RUN_ATTEMPT") != str(run["run_attempt"])
            or payload.get("GITHUB_SHA") != run.get("head_sha")
            or any(not isinstance(payload.get(key), str) or not re.fullmatch(r"[a-f0-9]{64}", payload[key])
                   for key in ("SITE_SHA256", "LAB_SHA256"))):
        return None
    try:
        checked_at = stamp(payload.get("verified_at", ""))
    except (AttributeError, ValueError):
        return None
    if not stamp(run["created_at"]) <= checked_at <= now:
        return None
    return {"at": checked_at.isoformat(), "triggered_at": run["created_at"],
            "url": run["html_url"], "sha": run["head_sha"], "artifact_id": artifact_id,
            "attempt": run["run_attempt"]}


def expected_slots(start, end, minutes):
    hour = start.replace(minute=0, second=0, microsecond=0)
    count = 0
    while hour < end:
        count += sum(start <= hour + timedelta(minutes=minute) < end for minute in minutes)
        hour += timedelta(hours=1)
    return count


def measure(start, now, runs, artifacts, payloads=None, minutes=(13, 43)):
    end = start + timedelta(days=7)
    if now < start:
        raise ValueError("Rollout timestamp is in the future")
    payloads = payloads or {}
    receipts = {}
    for row in artifacts:
        if row["name"] == RECEIPT and not row["expired"] and row.get("workflow_run"):
            receipts.setdefault(row["workflow_run"]["id"], []).append(row["id"])
    observed = sorted((row for row in runs if start <= stamp(row["created_at"]) < min(end, now)
                       and row["event"] == "schedule" and row["head_branch"] == "main"),
                      key=lambda row: row["created_at"])
    buckets = [0] * 7
    checked = []
    metadata_only = []
    late = []
    for run in observed:
        if run["conclusion"] != "success" or run["id"] not in receipts:
            continue
        receipt = next((delivery for ident in sorted(receipts[run["id"]], reverse=True)
                        if (delivery := checked_receipt(run, ident, payloads.get(ident), now))), None)
        if receipt and stamp(receipt["at"]) < end:
            checked.append(receipt)
            buckets[(stamp(receipt["at"]) - start).days] += 1
        elif not receipt:
            metadata_only.append(run["html_url"])
        else:
            late.append(receipt)
    checked.sort(key=lambda row: stamp(row["at"]))
    dates = [start, *(stamp(row["at"]) for row in checked), min(end, now)]
    return {"start_utc": start.isoformat(), "end_utc": end.isoformat(),
            "elapsed_days": round((min(end, now) - start).total_seconds() / 86400, 3),
            "expected_slots_elapsed": expected_slots(start, min(end, now), minutes),
            "scheduled_runs": len(observed), "verified_publications": checked,
            "successful_run_with_listed_artifact_only": metadata_only,
            "verified_after_window": late,
            "scheduled_without_success_receipt": [r["html_url"] for r in observed
                if r["id"] not in receipts or r["conclusion"] != "success"],
            "verified_per_24h": buckets,
            "longest_observed_gap_hours": round(max((b-a).total_seconds() for a,b in zip(dates,dates[1:])) / 3600, 2),
            "seven_intervals_observed": now >= end and all(buckets)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, type=stamp, help="UTC rollout timestamp from the release report")
    parser.add_argument("--snapshot", type=Path, help="saved public run and artifact metadata as JSON")
    parser.add_argument("--receipts", type=Path, help="directory containing downloaded receipt JSON named by artifact ID")
    parser.add_argument("--at", type=stamp, help="observation cutoff for a reproducible replay")
    args = parser.parse_args()
    if args.snapshot:
        snapshot = json.loads(args.snapshot.read_bytes())
        runs, artifacts = snapshot["runs"], snapshot["artifacts"]
    else:
        runs = pages("workflows/pages.yml/runs", "workflow_runs",
                     {"branch": "main", "event": "schedule", "created": ">=" + args.since.isoformat()}, args.since)
        artifacts = pages("artifacts", "artifacts", {"name": RECEIPT}, args.since)
    receipts = {int(path.stem): json.loads(path.read_bytes()) for path in args.receipts.glob("*.json")
                if path.stem.isascii() and path.stem.isdigit()} if args.receipts else {}
    print(json.dumps(measure(args.since, args.at or datetime.now(timezone.utc), runs, artifacts, receipts), indent=2))


if __name__ == "__main__":
    main()
