# SPDX-License-Identifier: MIT
"""Replay stored RDNA inputs through the isolated XCL root-UAV read-switch prototype."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess

from fixture_census import command, describe, hash_file
from open_pixel_census import error_text

CONFIG = ("wave", "spi_ps_input_ena", "interpolants", "color_mask", "depth_mode")
ENABLE = "XCL_DXIL_SWITCH_READ_FUSION"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("input", "xcl", "dxc", "dxv", "patch", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    for key, value in vars(args).items():
        setattr(args, key, value.resolve())
    manifest = json.loads(args.input.read_text(encoding="utf-8"))
    args.out.mkdir()
    rows = []
    for index, fixture in enumerate(manifest["observations"]):
        if "rdna" not in fixture:
            continue
        folder = f"{index:03d}"
        directory = args.out / folder
        directory.mkdir()
        source = args.input.parent / folder / "shader.rdna2"
        config = fixture["rdna"]
        if hash_file(source) != config["sha256"]:
            raise ValueError(f"{source}: input hash changed")
        # The census writes short case folders to avoid Windows DXC path limits.
        rdna = directory / "shader.rdna2"
        shutil.copyfile(source, rdna)
        row = {key: fixture[key] for key in ("group", "source", "entry", "source_sha256", "rdna")}
        for arm in ("off", "on"):
            env = {key: value for key, value in os.environ.items() if not key.startswith("XCL_")}
            env["XCL_DXC_DIR"] = str(args.dxc.parent)
            if arm == "on":
                env[ENABLE] = "1"
            target = directory / f"{arm}.dxil"
            try:
                fields = [str(config.get(key, -1)) for key in CONFIG]
                command([args.xcl, rdna, target, *fields, "root-4"], env=env)
                row[arm] = describe(target, args.dxc, args.dxv)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                row[arm] = {"error": error_text(error, directory.parent.parent)}
        rows.append(row)
    summary = Counter()
    for row in rows:
        off, on = row["off"], row["on"]
        state = ("failed" if "error" in off or "error" in on else
                 "changed" if off["sha256"] != on["sha256"] else "identical")
        summary[(row["group"], state)] += 1
    evidence = {
        "base_xcl": manifest["xcl"], "window_layout": "four root UAVs", "switch": ENABLE + "=1",
        "corpus_manifest_sha256": hash_file(args.input),
        "test_executable_sha256": hash_file(args.xcl), "prototype_patch_sha256": hash_file(args.patch),
        "dxc_sha256": hash_file(args.dxc), "dxv_sha256": hash_file(args.dxv), "observations": rows,
    }
    (args.out / "root-switch.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
