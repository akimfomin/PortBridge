# SPDX-License-Identifier: GPL-2.0-only
"""Run the bounded four-piece follow-up using the pinned census harness."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


HERE = Path(__file__).resolve().parent
CENSUS_SHA256 = {
    "census.rs": "67b959bae13dcb231d5c34cf385d19f365001778212447711e1a3b4ec4fc987d",
    "run.py": "4abd0dc3fb6397290ad2ccf7766e23298897e1fd33015fec99548688cca024b7",
}


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("The pinned census harness changed")
    return text.replace(old, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("census-dir", "rustc", "linker", "dxv"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    original = args.census_dir.resolve(strict=True)
    for name, expected in CENSUS_SHA256.items():
        if sha256((original / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Pinned census input changed: {name}")
    sys.path.insert(0, str(original))
    import run as census

    rustc, linker, dxv = (path.resolve(strict=True) for path in (args.rustc, args.linker, args.dxv))
    fragment = (HERE / "fragmentation.rs").read_text(encoding="utf-8")
    original_stage = census.stage_sources
    original_report = census.report_for

    def stage_sources(build):
        original_stage(build)
        target = build / "gpu/dxil/module/census.rs"
        harness = target.read_text(encoding="utf-8")
        harness = replace_once(harness, """fn strict(lives: &[Lifetime]) -> Layout {
    let mut ordered = lives.to_vec();
    ordered.sort_by_key(|l| (l.first, l.value));""", """fn strict(lives: &[Lifetime]) -> Layout {
    ordered_strict(lives, false)
}

fn ordered_strict(lives: &[Lifetime], prefer_longer: bool) -> Layout {
    let mut ordered = lives.to_vec();
    ordered.sort_by_key(|l| (l.first, std::cmp::Reverse(if prefer_longer { l.last } else { 0 }), l.value));""")
        harness = replace_once(harness, """    persistent(false, out);
    persistent(true, out);
    wave32_loops(out);
    disjoint(out);
}""", "    fragmentation(out);\n}")
        target.write_text(harness + "\n" + fragment, encoding="utf-8")

    def report_for(text):
        lines = text.splitlines()
        results = original_report("\n".join(line for line in lines
                                             if not line.startswith(("variant,", "slot,"))))
        for line in lines:
            row = line.split(",")
            if row[0] == "variant":
                _, name, stride, checks = row
                fixture = results[name]
                del fixture["incorrect_alias_negative_control_mismatches"]
                fixture["longer_first_dwords_per_group"] = int(stride) * 32
                fixture["longer_first_replay_words_per_order"] = int(checks)
                fixture["replay_mismatches"] = 0
            elif row[0] == "slot":
                _, name, value, slot = row
                life = next(life for life in results[name]["intervals"] if life["value"] == int(value))
                life["longer_first_slot"] = int(slot)
        return results

    revision = census.verified_sources()
    with TemporaryDirectory(prefix="pb-xcl-2126-fragmentation-") as temp:
        build = Path(temp)
        stage_sources(build)
        exe = build / "probe.exe"
        subprocess.run([str(rustc), "--edition=2024", "-D", "warnings", "-C", f"linker={linker}",
                        str(build / "main.rs"), "-o", str(exe)], cwd=build, check=True, timeout=30)
        assets = build / "assets"
        assets.mkdir()
        probe = subprocess.run([str(exe), str(assets)], cwd=build, timeout=8, capture_output=True, text=True)
        if probe.returncode:
            raise ValueError(f"CPU probe failed:\n{probe.stdout}{probe.stderr}")
        fixtures = report_for(probe.stdout)
        validated = {}
        for shader in sorted(assets.glob("*.dxil")):
            process = subprocess.run([str(dxv), str(shader)], check=True, capture_output=True, text=True, timeout=8)
            if "validation succeeded" not in (process.stdout + process.stderr).casefold():
                raise ValueError(f"DXV did not report validation success for {shader.name}")
            validated[shader.name] = sha256(shader.read_bytes()).hexdigest()
        name = "four-piece-fragmentation"
        if len(validated) != fixtures[name]["pieces"] * 3:
            raise ValueError("Unexpected number of validated pieces")
        result = {"upstream_revision": revision,
                  "rustc": subprocess.check_output([str(rustc), "--version"], text=True, timeout=5).strip(),
                  "dxv_sha256": sha256(dxv.read_bytes()).hexdigest(),
                  "fixtures": fixtures, "validated_dxil": validated}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
