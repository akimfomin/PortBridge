# SPDX-License-Identifier: GPL-2.0-only
"""Fetch only the pinned public XCL files required by this experiment."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
REVISION = "3283da481077c1962f13f1b4078841662f7a4ccb"
BASE = f"https://raw.githubusercontent.com/xcl-dev/xcl/{REVISION}/"
MAX_BYTES = 1024 * 1024


def verified_copy(filename, sha256):
    source = PurePosixPath(filename)
    if source.is_absolute() or ".." in source.parts or str(source) != filename:
        raise ValueError(f"Unexpected source path {filename!r}")
    target = ROOT / "upstream" / Path(*source.parts)
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == sha256:
        return filename
    request = Request(BASE + filename, headers={"User-Agent": "PortBridge XCL scratch replay"})
    with urlopen(request, timeout=20) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError(f"Hash or size differs for {filename}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return filename


def main():
    manifest = ROOT / "SOURCE.json"
    raw = manifest.read_bytes()
    source = json.loads(raw)
    if source["revision"] != REVISION:
        raise ValueError("Unexpected source revision")
    with ThreadPoolExecutor(max_workers=4) as pool:
        names = list(pool.map(lambda entry: verified_copy(*entry), source["sha256"].items()))
    (ROOT / "upstream" / "SOURCE.json").write_bytes(raw)
    print(f"Verified {len(names)} original XCL inputs at {REVISION}")


if __name__ == "__main__":
    main()
