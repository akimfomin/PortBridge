# SPDX-License-Identifier: MIT
"""Compare D3D12 cache representations on known, small generated programs."""

import argparse
from hashlib import sha256
from itertools import permutations
import json
from pathlib import Path
from statistics import median
import struct
import shutil
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "liveness-shared"
SELECTOR = "NVIDIA GeForce RTX 4070 Ti SUPER"
ORDERS = ("library-first", "blob-first")
CACHE_OPERATIONS = tuple(permutations(("plain", "blobs", "library")))


def run(exe, root_signature, programs, order, archive=None):
    mode = "library-archive" if archive else "library-smoke"
    command = [str(exe), mode, SELECTOR, str(root_signature), order]
    if archive:
        command.append(str(archive))
    command.extend(map(str, programs))
    process = subprocess.run(
        command, capture_output=True, text=True, timeout=9,
    )
    result = json.loads(process.stdout)
    if process.returncode or result.get("stage") != "complete" or not result["worker_reaped"]:
        raise RuntimeError(result)
    if result["pipelines"] != len(programs) or result["adapter"] != SELECTOR:
        raise RuntimeError(result)
    return result


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def verify_identity(observed, root, bundle, seed=None):
    if observed["root_sha256"] != root or observed["shader_sha256"] != bundle:
        raise RuntimeError("Worker loaded unexpected source-generated inputs")
    if seed is not None:
        for key in ("adapter_luid", "dxgi_driver_version"):
            if observed[key] != seed[key]:
                raise RuntimeError(f"{key} differs from the seed worker")


def archive_pair(index, pair, exe, root_signature, programs, root, bundle):
    with tempfile.TemporaryDirectory(prefix="shader-cache-archive-", dir=HERE) as folder:
        scratch = Path(folder).resolve(strict=True)
        if not scratch.is_relative_to(HERE):
            raise RuntimeError("Scratch directory escaped the benchmark")
        shared = scratch / f"{scratch.name}-seed.exe"
        shutil.copyfile(exe, shared)
        seed = run(shared, root_signature, programs, "seed", scratch)
        verify_identity(seed, root, bundle)
        pair["seed"] = seed
        caches = {name: scratch / f"{name}.blob" for name in ("library", *(f"p{i}" for i in range(6)))}
        if any(not path.is_file() for path in caches.values()):
            raise RuntimeError("Archive seed did not produce all seven expected files")
        if caches["library"].stat().st_size != seed["library_bytes"]:
            raise RuntimeError("Persisted library size disagrees with the seed")
        if sum(path.stat().st_size for name, path in caches.items() if name != "library") != seed["individual_cache_bytes"]:
            raise RuntimeError("Persisted blob sizes disagree with the seed")
        checksums = {name: digest(path) for name, path in caches.items()}
        pair["cached_sha256"] = checksums
        identities = ("same_filename", "fresh_filenames")
        if index % 2:
            identities = identities[::-1]
        for identity in identities:
            observations = pair[identity] = {}
            order = CACHE_OPERATIONS[index % len(CACHE_OPERATIONS)]
            if identity == "fresh_filenames":
                order = order[::-1]
            for operation in order:
                if any(digest(path) != checksums[name] for name, path in caches.items()):
                    raise RuntimeError("Cache bytes changed between worker launches")
                path = shared
                if identity == "fresh_filenames":
                    path = scratch / f"{scratch.name}-{operation}.exe"
                    shutil.copyfile(exe, path)
                observed = run(path, root_signature, programs, operation, scratch)
                verify_identity(observed, root, bundle, seed)
                observed["executable_name"] = path.name
                observations[operation] = observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=HERE / "portbridge-pso-library.exe")
    parser.add_argument("--result", type=Path, default=HERE / "library-smoke-results.json")
    parser.add_argument("--pairs", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--start-at", type=int, choices=range(8), default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--archive", action="store_true")
    args = parser.parse_args()
    exe = args.exe.resolve(strict=True)
    original = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    groups = {}
    for row in original:
        groups.setdefault(row["salt"], []).append(row)
    result = {"exe_sha256": digest(exe), "pairs": [], "status": "in_progress"}
    if args.start_at + args.pairs > len(groups):
        parser.error("the selected range exceeds the prepared input groups")
    for n, (salt, rows) in enumerate(groups.items()):
        if n < args.start_at:
            continue
        if n >= args.start_at + args.pairs:
            break
        root_signatures = [FIXTURES / row["root"] for row in rows]
        signatures = {digest(path) for path in root_signatures}
        programs = [FIXTURES / row[form]["file"] for row in rows for form in ("short", "long")]
        inputs = [path.read_bytes() for path in programs]
        hashes = [sha256(code).hexdigest() for code in inputs]
        if len(signatures) != 1 or len(programs) != 6 or len(set(hashes)) != len(programs):
            raise RuntimeError(f"Unexpected fixtures for salt {salt}")
        if any(not 32 <= len(code) <= 4096 for code in inputs):
            raise RuntimeError(f"Input size outside the smoke budget for salt {salt}")
        bundle = sha256(b"".join(struct.pack("<I", len(code)) + code for code in inputs)).hexdigest()
        root = signatures.pop()
        pair = {
            "salt": salt,
            "root_sha256": root,
            "bundle_sha256": bundle,
            "shader_sha256": {path.name: value for path, value in zip(programs, hashes)},
        }
        result["pairs"].append(pair)
        if args.dry_run:
            continue
        try:
            if args.archive:
                archive_pair(n, pair, exe, root_signatures[0], programs, root, bundle)
            else:
                orders = ORDERS if n % 2 == 0 else ORDERS[::-1]
                for order in orders:
                    pair[order] = run(exe, root_signatures[0], programs, order)
                    verify_identity(pair[order], root, bundle)
                left, right = (pair[order] for order in ORDERS)
                verify_identity(right, root, bundle, left)
        except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
            result["status"] = "stopped"
            result["error"] = str(error)
            args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            raise
        args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.dry_run:
        print(f"Checked {len(result['pairs'])} sets of six input files")
        return
    if args.archive:
        metric = {
            "plain": lambda row: row["warm_create_ms"],
            "blobs": lambda row: row["individual_replay_ms"],
            "library": lambda row: row["library_open_ms"] + row["library_replay_ms"],
        }
        result["median_replay_ms"] = {
            identity: {
                mode: median(measure(pair[identity][mode]) for pair in result["pairs"])
                for mode, measure in metric.items()
            }
            for identity in ("same_filename", "fresh_filenames")
        }
    else:
        processes = [pair[order] for pair in result["pairs"] for order in ORDERS]
        measures = ("individual_cache_bytes", "library_bytes", "library_open_ms",
                    "library_replay_ms", "individual_replay_ms", "warm_create_ms")
        result["medians"] = {key: median(row[key] for row in processes) for key in measures}
    result["status"] = "complete"
    args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["median_replay_ms" if args.archive else "medians"]))


if __name__ == "__main__":
    main()
