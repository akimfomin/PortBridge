# SPDX-License-Identifier: MIT
"""Check source hashes, recorded frame equivalence and Vulkan statistics without a GPU."""

import gzip
import json
from hashlib import sha256
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent


def main():
    modules = json.loads((HERE / "modules.json").read_bytes())
    records = json.loads((HERE / "measurements.json").read_bytes())
    render = records["renderer_runs"]
    for n, model in ((71, "mlp_combo"), (73, "mlp_morpheus_combo")):
        output_hashes = set()
        stats = {}
        for variant in ("whole", "strict", "gamma", "native"):
            capture = records["capture_runs"][f"{n}-{variant}-same-pso"]
            raw = capture["gpu"]
            assert raw["capture_statistics"] and raw["root_and_readback_guards_intact"]
            (fragment,) = [
                s
                for s in raw["executables"]
                if s["name"] == "FS" and s["stage_flags"] == 16
            ]
            native_stats = {s["name"]: s["value"] for s in fragment["statistics"]}
            stats[variant] = {
                "fs_bytes": native_stats["Binary Size"],
                "registers": native_stats["Register Count"],
            }
            if variant == "native":
                trials = [render[model + suffix] for suffix in (".frame", ".frame2")]
                for trial in trials:
                    assert trial["output_sha256"] == capture["rgba32f_sha256"]
                ordinary = [trial["gpu"] for trial in trials]
            else:
                identity = modules[str(n)][variant]
                original = gzip.decompress(
                    (HERE / "modules" / f"nerf{n}-{variant}.spv.gz").read_bytes()
                )
                assert sha256(original).hexdigest() == identity["input_spirv"]
                trials = [
                    rec
                    for key, rec in render.items()
                    if key.startswith(f"{n}-{variant}-frame-ordinary")
                ]
                assert trials
                for trial in trials:
                    assert (
                        trial["fragment_sha256"] == identity["ordinary_bounded_spirv"]
                    )
                    assert trial["output_sha256"] == capture["rgba32f_sha256"]
                    assert (
                        trial["native_sha256"]
                        == render[model + ".frame"]["output_sha256"]
                    )
                    output_hashes.add(trial["output_sha256"])
                ordinary = [trial["gpu"] for trial in trials]
                diagnostic = render[f"{n}-{variant}-frame-typed"]
                assert (
                    diagnostic["fragment_sha256"]
                    == identity["diagnostic_bounded_spirv"]
                )
                assert diagnostic["output_sha256"] == capture["rgba32f_sha256"]
                assert diagnostic["metrics"]["diagnostic_alpha"] == 0
                for trial in [*trials, diagnostic]:
                    for target in ("native", "cpu"):
                        metrics = trial["metrics"][target]
                        assert (
                            metrics["exact_alpha"] == 57600
                            and metrics["exact_clear_rgba"] == 5095
                        )
                        assert metrics["max_abs"] <= 1e-4
            assert all(
                not run["capture_statistics"] and run["root_and_readback_guards_intact"]
                for run in ordinary
            )
            stats[variant]["median_group_us_by_worker"] = [
                round(1000 * median(run["gpu_ms_per_draw"]), 3) for run in ordinary
            ]
        assert len(output_hashes) == 1
        print(
            json.dumps(
                {
                    "model": model,
                    "common_translated_rgba32f": output_hashes.pop(),
                    "fragment": stats,
                }
            )
        )


if __name__ == "__main__":
    main()
