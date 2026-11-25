# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch only the public text inputs named by the exact VIctory #1971 allowlist."""

from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
REPOSITORY = "https://raw.githubusercontent.com/thatirishguyyy/VIctory/"
PIN = "1ae8ad326ef6b4fe6e5ac1c5555079fafb78575a"
LIMIT = 512 * 1024


def main():
    manifest = json.loads((ROOT / "source-manifest.json").read_text(encoding="utf-8"))
    if manifest["revision"] != PIN or len(manifest["files"]) != 13:
        raise ValueError("unexpected source manifest")
    for name, expected in manifest["files"].items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or path.suffix not in (".rs", ".toml", ".md", ""):
            raise ValueError(f"invalid source path {name}")
        local = ROOT / "upstream" / path
        if not local.resolve().is_relative_to((ROOT / "upstream").resolve()):
            raise ValueError(f"source path resolves outside the proof: {name}")
        if local.is_file():
            data = local.read_bytes()
        else:
            url = REPOSITORY + PIN + "/" + name
            with urlopen(url, timeout=20) as response:
                if response.geturl() != url:
                    raise ValueError(f"unexpected redirect for {name}")
                data = response.read(LIMIT + 1)
        if len(data) > LIMIT or sha256(data).hexdigest() != expected:
            raise ValueError(f"public source hash did not match for {name}")
        data.decode("utf-8")
        if not local.exists():
            local.parent.mkdir(parents=True, exist_ok=True)
            with local.open("xb") as output:
                output.write(data)
        print(name)


if __name__ == "__main__":
    main()
