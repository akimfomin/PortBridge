"""Verify the retained GPU and compiler receipts and print the per-case measurements."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median


def check_cold(samples, manifest, blocks):
    expected = {(case["id"], name) for case in manifest["cases"] for name in case["arms"]}
    groups = defaultdict(list)
    for row in samples:
        key = row["id"], row["arm"]
        if key not in expected or row.get("error") or row["guard_exit"] != 0:
            raise ValueError(f"Failed or unknown sample {key}")
        groups[key].append(row)
    if set(groups) != expected:
        raise ValueError("Missing cold pipeline arm")
    for key, runs in sorted(groups.items()):
        if sorted(r["block"] for r in runs) != list(range(blocks)):
            raise ValueError(f"Missing or duplicated block for {key}")
        sizes = {r["opaque_cache_bytes"] for r in runs}
        if len(sizes) != 1:
            raise ValueError(f"Unstable opaque blob size for {key}")
        print(f"  {key[0]:7} {key[1]:10} {median(r['native_create_ms'] for r in runs):8.2f} ms"
              f"   {sizes.pop():7} cached bytes")


def check_draws(draws):
    groups = defaultdict(list)
    for name, data in draws.items():
        camera, index, arm = name.removeprefix("ray800-").removesuffix(".json").split("-")
        draw = data["draw"]
        if (not draw["root_and_readback_guards_intact"] or data["vs_native_gl"]["pixels"] != 360000
                or draw["draws_per_interval"] != 8 or len(draw["gpu_ms_per_draw"]) != 5):
            raise ValueError(f"Incomplete draw for {name}")
        groups[camera].append((arm, data["output_sha256"], median(draw["gpu_ms_per_draw"])))
    if set(groups) != {"primary","secondary"}:
        raise ValueError("Both camera views are required")
    for camera, frames in sorted(groups.items()):
        count = Counter(mode for mode, _, _ in frames)
        if set(count) != {"source","project","inputs","window"} or set(count.values()) != {2}:
            raise ValueError(f"Missing draw arm for {camera}")
        if len({digest for mode,digest,_ in frames if mode != "source"}) != 1:
            raise ValueError(f"Translated readbacks differ on {camera}")
        print(camera, {arm:round(median(t for mode,_,t in frames if mode == arm),3) for arm in count})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?", type=Path,
                        default=Path(__file__).with_name("measurements.json.gz"))
    options = parser.parse_args()
    data = json.loads(gzip.decompress(options.archive.read_bytes()))
    rows = data["corpus"]["rows"]
    valid = [r for r in rows if "sha256" in r.get("project",{})]
    changed = [r for r in valid if r["window"]["dxil_bytes"] < r["project"]["dxil_bytes"]]
    print("Reduced DXIL", len(changed), "/", len(valid), "successful entries in", len(rows), "attempts")
    print("Distinct guest programs", len({r["guest_sha256"] for r in changed}), "/",
          len({r["guest_sha256"] for r in valid}))
    for label, trial in data["cold"].items():
        print(label)
        check_cold(trial["samples"], trial["manifest"], trial["identity"]["blocks"])
    for label, figures in data["vulkan"].items():
        print("Vulkan", label)
        check_draws(figures["draws"])
        for name, report in sorted(figures["pipelines"].items()):
            fs = next(e for e in report["physical_pipeline"]["executables"] if e["name"] == "FS")
            stats = {s["name"]:s["value"] for s in fs["statistics"]}
            print(name, "FS Binary Size",stats["Binary Size"],"registers",stats["Register Count"])


if __name__ == "__main__":
    main()
