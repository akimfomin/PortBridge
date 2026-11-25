"""Measure exact ShaderLibrary::load paths in separate matched Windows processes."""

import argparse
import ctypes
from ctypes import wintypes
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess


HERE = Path(__file__).resolve().parent
VARIANTS = ("baseline", "candidate", "combined", "combined-stream")
ORDERS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))


class PerformanceInformation(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD),
        *[(name, ctypes.c_size_t) for name in (
            "commit_total", "commit_limit", "commit_peak", "physical_total", "physical_available",
            "system_cache", "kernel_total", "kernel_paged", "kernel_nonpaged", "page_size",
        )],
        ("handle_count", wintypes.DWORD),
        ("process_count", wintypes.DWORD),
        ("thread_count", wintypes.DWORD),
    ]


def headroom():
    stat = PerformanceInformation()
    stat.size = ctypes.sizeof(stat)
    query = ctypes.WinDLL("psapi.dll", use_last_error=True).GetPerformanceInfo
    query.argtypes = [ctypes.POINTER(PerformanceInformation), wintypes.DWORD]
    query.restype = wintypes.BOOL
    if not query(ctypes.byref(stat), stat.size):
        raise ctypes.WinError(ctypes.get_last_error())
    return tuple(
        pages * stat.page_size / 2**30
        for pages in (stat.commit_limit - stat.commit_total, stat.physical_available)
    )


def sample(executable, directory, info):
    child = subprocess.run(
        [executable, directory, str(info["entries"]), str(info["richness"])],
        check=True, capture_output=True, text=True, timeout=10,
    )
    record = json.loads(child.stdout)
    if record["verified"] != info["entries"]:
        raise ValueError("incomplete fixture comparison")
    return record


def comparison(pairs, original, candidate):
    return {
        field: {
            "original": median(pair["samples"][original][field] for pair in pairs),
            "candidate": median(pair["samples"][candidate][field] for pair in pairs),
            "paired_candidate_over_original": median(
                pair["samples"][candidate][field] / pair["samples"][original][field] for pair in pairs
            ),
        }
        for field in ("load_ms", "peak_working_set", "peak_commit")
    }


def execute(fixture_dir, target):
    fixtures = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    targets = {name: HERE / f"{name}-load.exe" for name in VARIANTS}
    output = {"binaries": {name: sha256(exe.read_bytes()).hexdigest()
                           for name, exe in targets.items()}, "fixtures": []}
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        for info in fixtures:
            directory = fixture_dir / info["name"]
            actual = sha256((directory / "index.json").read_bytes()).hexdigest()
            assert actual == info["sha256"]
            pairs = []
            commit, physical = headroom()
            if commit < 3 or physical < 6:
                raise SystemExit("CPU measurement admission failed")
            warmup = {name: sample(exe, directory, info) for name, exe in targets.items()}
            for i in range(8):
                commit, physical = headroom()
                if commit < 3 or physical < 6:
                    raise SystemExit("CPU measurement admission failed")
                order = ORDERS[i % len(ORDERS)]
                measurements = {}
                for index in order:
                    name = VARIANTS[index]
                    measurements[name] = sample(targets[name], directory, info)
                pairs.append({"order": [VARIANTS[index] for index in order], "samples": measurements})
            output["fixtures"].append({
                **info, "warmup": warmup, "pairs": pairs,
                "stream_on_main": comparison(pairs, "baseline", "candidate"),
                "stream_with_other_changes": comparison(pairs, "combined", "combined-stream"),
            })
            stream.seek(0)
            stream.write(json.dumps(output, indent=2) + "\n")
            stream.truncate()
            stream.flush()
            print(info["name"], json.dumps({
                "main": output["fixtures"][-1]["stream_on_main"],
                "combined": output["fixtures"][-1]["stream_with_other_changes"],
            }), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    execute(args.fixtures.resolve(strict=True), args.result)
