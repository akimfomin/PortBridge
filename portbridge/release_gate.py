"""Check a static publication candidate before packaging or deployment."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from .catalog import public_url
from .export import EXPORT_FILES, RELEASE_FILES, release_inventory_digest
from .integrations import SCHEMA
from .pages_health import checksum, verify_linked_snapshots


def verify_files(path):
    """Compare the candidate to the exporter's in-memory inventory, including generated shards."""
    try:
        inventory = json.loads((path / RELEASE_FILES).read_bytes())
        files = inventory["files"]
        if (inventory["version"] != 1 or not isinstance(files, dict)
                or inventory["sha256"] != release_inventory_digest(files)
                or not (EXPORT_FILES - {RELEASE_FILES}).issubset(files)):
            return [RELEASE_FILES]
    except (OSError, ValueError, TypeError, KeyError):
        return [RELEASE_FILES]

    missing = set(files)
    failed = []
    for item in path.rglob("*"):
        name = item.relative_to(path).as_posix()
        if item.is_symlink() or item.name.startswith(".env") or item.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".pem", ".key"}:
            failed.append(name)
        elif name in files and item.is_file():
            try:
                with item.open("rb") as stream:
                    if checksum(stream) != files[name]:
                        failed.append(name)
            except OSError:
                failed.append(name)
            missing.discard(name)
        elif not item.is_dir() and name != RELEASE_FILES:
            failed.append(name)
    return sorted(set(failed) | missing)


def audit(path):
    failed = verify_files(path)
    if failed:
        return failed
    data = path / "data"
    read = lambda name: json.loads((data / (name + ".json")).read_bytes())
    manifest = read("site")
    site_digest = sha256((data / "site.json").read_bytes()).hexdigest()
    failed = list(verify_linked_snapshots(site_digest, request=lambda name: (data / (name + ".json")).open("rb")))
    from .code_search import MAX_INDEX_BYTES, SCHEMA_VERSION
    code_name = manifest["snapshots"].get("source-code")
    if not code_name or not (data / code_name).is_file() or (data / code_name).stat().st_size > MAX_INDEX_BYTES:
        failed.append("source-code snapshot")
    elif read(code_name.removesuffix(".json")).get("version") != SCHEMA_VERSION:
        failed.append(code_name)
    partner = read(manifest["snapshots"]["partner"].removesuffix(".json"))
    if partner != read("partner") or partner.get("schema_version") != SCHEMA:
        failed.append("partner contract")
    rows = partner["items"]
    if len({row["id"] for row in rows}) != len(rows):
        failed.append("duplicate partner rows")
    for row in rows:
        if not public_url(row.get("source")) or row.get("kind") not in {"task", "result"}:
            failed.append("partner item " + row["id"])
    for name in ("lab", "radar", "impact", "partner"):
        snapshot = data / manifest["snapshots"][name]
        scope = snapshot.read_bytes().lower()
        if any(value in scope for value in (b"m5-fixture", b"test-only-local-principal", b"synthetic-staging-only")):
            failed.append("staging marker in " + name)
    return failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    failed = audit(args.directory)
    if failed:
        raise SystemExit("Publication gate failed: " + ", ".join(failed))
    print("Publication gate passed: all exported file checksums, partner contract and staging exclusions")


if __name__ == "__main__":
    main()
