# SPDX-License-Identifier: MIT
"""Check the public XCL pixel entry point and its translated-disk-cache separation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(cache):
    return {
        path.relative_to(cache).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(cache.rglob("*.bin"))
    }


def run(args):
    out = args.output.resolve()
    cache = out / "cache"
    out.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        raise ValueError("select a fresh output directory for the cold/warm cache test")
    cache.mkdir()
    first = {}
    rows = []
    for i, mode in enumerate(("whole", "project", "whole", "project")):
        before = snapshot(cache)
        destination = out / f"{i}-{mode}.dxil"
        env = dict(os.environ, XCL_DIRECT_DXIL="all", XCL_DXIL_CACHE=str(cache),
                   XCL_DIRECT_PIXEL_MASK_PROJECTION=str(int(mode == "project")))
        trial = subprocess.run([str(args.observer.resolve()), str(args.fixture.resolve()), str(destination)],
                               capture_output=True, env=env, check=True)
        (out / f"{i}-{mode}.log").write_bytes(trial.stdout + trial.stderr)
        expected = args.whole if mode == "whole" else args.project
        digest = sha(destination)
        if digest != sha(expected):
            raise AssertionError(f"{mode} differs from its corresponding offline output")
        after = snapshot(cache)
        added = sorted(after.keys() - before.keys())
        if i < 2:
            if len(added) != 1 or any(after[k] != v for k, v in before.items()):
                raise AssertionError("a cold run must create one distinct immutable entry")
            first[mode] = added[0]
        elif after != before:
            raise AssertionError("a warm hit changed the cache")
        rows.append({"mode": mode, "warm": i >= 2, "sha256": digest,
                     "dxil_bytes": destination.stat().st_size, "cache_entry": first[mode],
                     "cache_file_count": len(after)})
    if first["whole"] == first["project"]:
        raise AssertionError("the modes alias the same cache entry")
    report = {"observer_sha256": sha(args.observer), "fixture_sha256": sha(args.fixture),
              "runs": rows}
    (out / "evidence.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("observer", "fixture", "whole", "project", "output"):
        parser.add_argument(name, type=Path)
    run(parser.parse_args())
