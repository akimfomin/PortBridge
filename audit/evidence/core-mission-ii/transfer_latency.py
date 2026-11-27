"""Measure gaps between publicly observed transfers and timestamped PortBridge leads."""
import argparse
from datetime import datetime
import json
from pathlib import Path


def stamp(value):
    return datetime.fromisoformat(value) if value else None


def measure(row):
    start, external, clue = (stamp(row[name]) for name in ("public_at", "external_at", "portbridge_at"))
    if bool(clue) != bool(row["portbridge_receipt"]):
        raise ValueError(f"{row['id']}: a dated PortBridge lead requires a permalink")
    if start and any(observed and observed < start for observed in (external, clue)):
        raise ValueError(f"{row['id']}: observation predates source availability")
    if external and not row["external"]:
        raise ValueError(f"{row['id']}: dated transfer requires a permalink")
    return {"id": row["id"],
            "source_to_transfer_seconds": int((external - start).total_seconds()) if start and external else None,
            "source_to_portbridge_seconds": int((clue - start).total_seconds()) if start and clue else None,
            "portbridge_lead_seconds": int((external - clue).total_seconds()) if external and clue else None,
            "earlier_portbridge_receipt_verified": bool(external and clue and clue < external)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    args = parser.parse_args()
    rows = json.loads(args.events.read_bytes())
    print(json.dumps([measure(row) for row in rows], indent=2))


if __name__ == "__main__":
    main()
