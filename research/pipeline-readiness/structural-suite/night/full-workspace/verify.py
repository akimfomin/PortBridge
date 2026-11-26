# SPDX-License-Identifier: MIT
"""Recompute the public Rust totals and verify the positive authored guest draw."""
import gzip
import hashlib
import json
from pathlib import Path
import re


def verify(directory):
    summary = json.loads((directory / "workspace.json").read_bytes())
    payload = gzip.decompress((directory / "workspace.log.gz").read_bytes())
    assert hashlib.sha256(payload).hexdigest() == summary["redacted_text_sha256"]
    text = payload.decode("utf-8")
    stats = list(re.finditer(
        r"(?m)^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out",
        text,
    ))
    assert len(stats) == summary["cargo_targets"]
    for index, key in enumerate(("passed", "failed", "ignored", "measured", "filtered"), start=2):
        assert sum(int(m[index]) for m in stats) == summary["rust_harness_totals"][key]
    assert text.count("SKIPPED ") == summary["explicit_skip_records"]
    assert len(summary["skip_records"]) == summary["explicit_skip_records"]
    for marker, expected in summary["guest_e2e_markers"].items():
        assert expected > 0 and text.count(marker) == expected
    print(directory.name, summary["revision"], summary["rust_harness_totals"], "skip records", len(summary["skip_records"]))


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    for name in ("carry", "projection"):
        verify(root / name)
