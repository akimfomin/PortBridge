"""Compare signed changed-line overlap in public patches without applying them."""

from collections import Counter
from pathlib import Path
import subprocess
import sys


def read_changes(data):
    counts = Counter()
    path = ""
    for line in data.splitlines():
        if line.startswith(b"diff --git "):
            path = ""
        elif line.startswith(b"+++ b/"):
            path = line.removeprefix(b"+++ b/")
        elif line.startswith(b"+++ "):
            path = b""
        elif path and line.startswith((b"+", b"-")) and not line.startswith(b"--- "):
            payload = line[1:].strip()
            if payload and not payload.startswith(b"//"):
                counts[(path, line[:1], b"".join(payload.split()))] += 1
    return counts


def main(paths):
    if len(paths) < 2:
        raise SystemExit("Pass the reference patch and at least one comparison patch")
    reference = None
    for name in paths:
        data = Path(name).read_bytes()
        patch_id = subprocess.run(["git", "patch-id", "--stable"], input=data, check=True,
                                  capture_output=True).stdout.decode("ascii").split()[0]
        changes = read_changes(data)
        if reference is None:
            reference = changes
        shared = reference & changes
        print(Path(name).name, patch_id, "changes", changes.total(), "shared", shared.total())


if __name__ == "__main__":
    main(sys.argv[1:])
