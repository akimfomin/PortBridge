"""Bounded, serialized cache comparison and Windows directory-entry controls."""

import argparse
import fnmatch
import heapq
import importlib.util
import json
import os
from pathlib import Path
import re
from statistics import median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns


def load_module(root, name):
    spec = importlib.util.spec_from_file_location(name, root / "PrototypeScarlett/emu/shader_cache.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def children(folder):
    try:
        with os.scandir(folder) as entries:
            return list(entries)
    except OSError:
        # Same enumeration behavior as the two wildcard components in Python 3.12.
        return []


suffix = re.compile(fnmatch.translate("*.dxil"),
                    re.IGNORECASE if os.path.normcase("Aa") != "Aa" else 0).match


def entry_data(folder):
    if not folder.is_dir():
        return
    for shard in children(folder):
        try:
            if not shard.is_dir():
                continue
        except OSError:
            continue
        for entry in children(shard.path):
            if suffix(entry.name):
                yield Path(entry.path), entry.stat()


def scandir_alternative(parent):
    class ScannedCache(parent):
        def prune(self):
            records = [(info.st_mtime, index, info.st_size, path)
                       for index, (path, info) in enumerate(entry_data(self.folder))]
            total = sum(size for _, _, size, _ in records)
            if total > self.limit:
                heapq.heapify(records)
                while records and total > self.limit:
                    _, _, size, path = heapq.heappop(records)
                    path.unlink(missing_ok=True)
                    total -= size
            self._total = total

    return ScannedCache


SIZE = 4096
PAYLOAD = b"DXBC" + bytes(SIZE - 4)
INSERTS = 16
ROUNDS = 6


def path(cache, number):
    return cache._path(f"{number:064x}")


def elapsed(cache_type, folder, entries):
    cache = cache_type(folder, entries * SIZE)
    for number in range(entries):
        cache.put(f"{number:064x}", PAYLOAD)
        os.utime(path(cache, number), (1_600_000_000 + number,) * 2)
    start = perf_counter_ns()
    for number in range(entries, entries + INSERTS):
        cache.put(f"{number:064x}", PAYLOAD)
    duration = perf_counter_ns() - start
    files = list(folder.glob("*/*.dxil"))
    assert len(files) == entries
    assert sum(file.stat().st_size for file in files) == entries * SIZE
    assert not any(path(cache, number).exists() for number in range(INSERTS))
    return duration / INSERTS / 1_000_000


def benchmark_pair(folder, entries, candidates):
    samples = {name: [] for name, _ in candidates}
    for round_number in range(ROUNDS):
        order = candidates if round_number % 2 == 0 else candidates[::-1]
        for name, cache_type in order:
            value = elapsed(cache_type, folder / f"{entries}-{name}-{round_number}", entries)
            samples[name].append(value)
    return {"resident": entries, "inserts_per_sample": INSERTS,
            "median_ms_per_put": {key: round(median(values), 4) for key, values in samples.items()},
            "samples_ms_per_put": {key: [round(value, 4) for value in values]
                                    for key, values in samples.items()}}


def filesystem_controls(folder):
    shard = folder / "aa"
    shard.mkdir(parents=True)
    for name in ["normal.dxil", "upper.DXIL", "dotted.DXİL", "dotless.DXıL", "ignore.txt"]:
        (shard / name).write_bytes(PAYLOAD)
    (shard / "directory.dxil").mkdir()
    target = folder.parent / "symlink-target"
    target.mkdir()
    (target / "other.dxil").write_bytes(PAYLOAD)
    links = {}
    for link, destination, is_directory in [
        (shard / "regular-link.dxil", target / "other.dxil", False),
        (folder / "dir-link", target, True),
    ]:
        try:
            link.symlink_to(destination, target_is_directory=is_directory)
        except OSError as error:
            links[link.name] = f"unavailable: {error.winerror or error.errno}"
        else:
            links[link.name] = "created"

    def compare(parent):
        baseline = [(path, path.stat().st_mtime, path.stat().st_size)
                    for path in parent.glob("*/*.dxil")]
        scanned = [(path, info.st_mtime, info.st_size) for path, info in entry_data(parent)]
        assert baseline == scanned
        return [path.relative_to(parent).as_posix() for path, _, _ in baseline]

    found = compare(folder)
    previous = Path.cwd()
    try:
        os.chdir(folder.parent)
        assert compare(Path(folder.name)) == found
    finally:
        os.chdir(previous)
    assert compare(folder / "nonexistent") == []
    assert compare(shard / "normal.dxil") == []

    disappeared = shard / "disappeared.dxil"
    disappeared.write_bytes(PAYLOAD)
    cached = next(entry for entry in children(shard) if entry.name == disappeared.name)
    disappeared.unlink()

    def stat_outcome(operation):
        try:
            return f"ok ({operation().st_size} bytes)"
        except OSError as error:
            return type(error).__name__

    return {"matching_absolute_and_relative": found, "links": links,
            "missing_and_file_root_yield_empty": True,
            "after_enumerated_regular_file_is_removed": {
                "path_stat": stat_outcome(disappeared.stat),
                "scandir_entry_stat": stat_outcome(cached.stat),
            }}


parser = argparse.ArgumentParser()
parser.add_argument("baseline", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
base_module = load_module(args.baseline, "cache_base")
current_module = load_module(root, "cache_patched")
scanned = scandir_alternative(current_module.ShaderCache)
with TemporaryDirectory(prefix="portbridge-cache-compare-") as raw:
    folder = Path(raw)
    controls = filesystem_controls(folder / "control")
    pairs = []
    for index, pair in enumerate([
        [("base", base_module.ShaderCache), ("one_pass", current_module.ShaderCache)],
        [("one_pass", current_module.ShaderCache), ("scandir", scanned)],
    ]):
        pairs.extend(benchmark_pair(folder / str(index), entries, pair) for entries in (64, 256))
print(json.dumps({"controls": controls, "paired": pairs}, indent=2))

