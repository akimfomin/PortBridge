# SPDX-License-Identifier: MIT
"""CPU verification for the optional scratch probe and aggregate A/B report."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parent
BASE = "3283da481077c1962f13f1b4078841662f7a4ccb"
COMPACT_PATCH_SHA256 = "1622912180e565cb1708de9719bc2b0ba33922542b3fcd7277456efe0bfc3f3a"
RELATIVE_SPLIT = Path("crates/xcl/src/gpu/dxil/module/split.rs")
FIXTURES = ("upstream-wave32-loops", "four-piece-fragmentation")
EXPECTED = {"baseline": (288, 192), "candidate": (256, 160)}


def run(args, cwd, env=None):
    process = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=50)
    if process.returncode:
        raise RuntimeError(f"{args[0]} exited with {process.returncode}\n{process.stderr}")
    return process


def probe(census, build, patch, tools, fragment):
    build.mkdir()
    target = build / RELATIVE_SPLIT
    target.parent.mkdir(parents=True)
    target.write_bytes((census.SOURCE_PATH / RELATIVE_SPLIT).read_bytes())
    if patch is not None:
        run(["git", "apply", str(patch)], build)
    diagnostic = ROOT / "scratch-aggregate.patch"
    run(["git", "apply", "--check", str(diagnostic)], build)
    run(["git", "apply", str(diagnostic)], build)

    census.stage_sources(build)
    module = build / "gpu/dxil/module"
    (module / "split.rs").write_text(census.instrumented_emitter(target.read_text(encoding="utf-8")), encoding="utf-8")
    harness = module / "census.rs"
    text = harness.read_text(encoding="utf-8")
    start = text.index("fn compare(")
    end = text.index("\n}\n", start) + 3
    text = text[:start] + """
fn compare(_: &str, s: &Shader, plan: &Plan, limit: usize, _: Option<(Value, Value)>, _: &Path) {
    let chain = s.split_compute([32, 1, 1], None, limit).unwrap();
    assert_eq!(chain.pieces.len(), plan.blocks.len());
    assert!(chain.dwords_per_group > 0);
    drop(EVENTS.take());
}
""" + text[end:]
    start = text.index("pub(super) fn run(")
    end = text.index("\n}\n", start) + 3
    text = text[:start] + """
pub(super) fn run(out: &Path) {
    wave32_loops(out);
    fragmentation(out);
}
""" + text[end:]
    harness.write_text(text + fragment[:fragment.index("    let first_fit")] + "}\n", encoding="utf-8")
    exe = build / "probe.exe"
    rustc, linker = tools
    run([str(rustc), "--edition=2024", "-D", "warnings", "-C", f"linker={linker}", str(build / "main.rs"), "-o", str(exe)], build)
    env = os.environ.copy()
    env.pop("XCL_SCRATCH_AGGREGATE", None)
    default = run([str(exe), str(build)], build, env)
    assert not default.stdout and not default.stderr
    env["XCL_SCRATCH_AGGREGATE"] = "1"
    measured = run([str(exe), str(build)], build, env)
    assert not measured.stdout
    return measured.stderr.splitlines()


def verify_comparator(output_dir):
    values = []
    for index, name in enumerate(FIXTURES):
        for flavor, sizes in EXPECTED.items():
            multiplier = 1 if flavor == "baseline" else 0.98
            values.append({
                "case": name, "input": "synthetic", "build": flavor,
                "grid": [2, 1, 1], "pieces": 4, "scratch_dwords_per_group": sizes[index],
                "words_checked": 64, "different_words": 0,
                "gpu_us_rounds": [[(40 + round_no + sample / 10) * multiplier for sample in range(20)] for round_no in range(4)],
            })

    path = output_dir / "numeric-replay.jsonl"
    command = [sys.executable, "-I", "-B", str(ROOT / "compare.py"), str(path), "--synthetic"]

    def execute(rows):
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return subprocess.run(command, cwd=output_dir, capture_output=True, text=True, timeout=5)

    good = execute(values)
    assert good.returncode == 0, good.stderr
    summary = json.loads(good.stdout)
    assert summary["mode"] == "synthetic-injected-timings"
    assert [row["candidate_time_delta_percent"] for row in summary["results"]] == [-2, -2]
    assert "gpu_us_rounds" not in good.stdout
    rejected = (
        ("incomplete pair", values[:-1]),
        ("unexpected field", [dict(values[0], raw_shader="never-publish-this"), *values[1:]]),
        ("different dispatch grid", [dict(values[0], grid=[3, 1, 1]), *values[1:]]),
        ("non-finite timing", [dict(values[0], gpu_us_rounds=[[float("inf")] * 20] * 4), *values[1:]]),
    )
    for label, rows in rejected:
        invalid = execute(rows)
        assert invalid.returncode == 2 and not invalid.stdout, label
    difference = execute([dict(values[0], different_words=1), *values[1:]])
    assert difference.returncode == 1
    assert json.loads(difference.stdout)["output_check"] == "fail"
    return {"timings": "injected protocol numbers, no GPU run", "checks_passed": 6}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("census", "compact", "rustc", "linker"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    census_path, compact, rustc, linker = (
        path.resolve(strict=True) for path in (args.census, args.compact, args.rustc, args.linker)
    )
    spec = importlib.util.spec_from_file_location("census", census_path / "run.py")
    census = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(census)
    assert census.verified_sources() == BASE
    fragment = (compact / "fragmentation.rs").read_text(encoding="utf-8")
    candidate = compact / "xcl-2126-compact-slots.patch"
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == COMPACT_PATCH_SHA256
    result = {"revision": BASE, "cases": list(FIXTURES), "scratch_dwords_per_group": {}}
    with TemporaryDirectory(prefix="pb-xcl-private-replay-") as temp:
        work = Path(temp)
        for flavor, patch in (("baseline", None), ("candidate", candidate)):
            lines = probe(census, work / flavor, patch, (rustc, linker), fragment)
            expected = [f"XCL_SCRATCH_AGGREGATE pieces=4 scratch_dwords_per_group={size}" for size in EXPECTED[flavor]]
            assert lines == expected, (flavor, lines)
            result["scratch_dwords_per_group"][flavor] = list(EXPECTED[flavor])
        result["diagnostic_default"] = "silent"
        result["comparator"] = verify_comparator(work)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
