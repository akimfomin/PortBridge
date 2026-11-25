# SPDX-License-Identifier: GPL-2.0-only
"""Build the pinned XCL fixture probe and validate every generated DXIL piece."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from textwrap import dedent

ROOT = Path(__file__).resolve().parent
DXIL = "crates/xcl/src/gpu/dxil"
SOURCE_PATH = ROOT / "upstream"
SOURCES = ("bitstream.rs", "container.rs", "module.rs", "module/opt.rs", "ops.rs", "shader.rs")
MAIN = """\
#![allow(dead_code)]
mod gpu {
    pub mod dxil {
        mod bitstream;
        mod container;
        mod module;
        mod ops;
        mod shader;
        mod validate {
            pub const VALVER: (u32, u32) = (1, 8);
            // run.py validates every blob with the real DXV after emission.
            pub fn validate(_: &[u8]) -> Result<(), String> { Ok(()) }
        }
        pub fn run(out: &std::path::Path) { module::split::pb_run(out); }
    }
}
fn main() {
    let out = std::env::args_os().nth(1).unwrap();
    gpu::dxil::run(std::path::Path::new(&out));
}
"""


def verified_sources():
    info = json.loads((SOURCE_PATH / "SOURCE.json").read_text(encoding="utf-8"))
    for path, expected in info["sha256"].items():
        data = (SOURCE_PATH / path).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"Pinned source hash differs: {path}")
    return info["revision"]


def instrumented_emitter(source):
    edits = {
        "        let src = &self.m;\n        let mut dst = self.dispatch_piece();": (
            "        pb_census::begin(stage);\n"
            "        let src = &self.m;\n        let mut dst = self.dispatch_piece();"
        ),
        "                    let words = src.pack(v, *values.get(&v)?, &mut dst.m);": (
            "                    let words = src.pack(v, *values.get(&v)?, &mut dst.m);\n"
            "                    pb_census::write(v, words.len().try_into().unwrap());"
        ),
        "            let words = (slot..slot + self.transport_words(v)?)": (
            "            pb_census::read(v, self.transport_words(v)?);\n"
            "            let words = (slot..slot + self.transport_words(v)?)"
        ),
    }
    for old, new in edits.items():
        if source.count(old) != 1:
            raise ValueError("The pinned emitter no longer matches the probe points")
        source = source.replace(old, new)
    return source + """
mod pb_census { include!("census.rs"); }
pub(crate) fn pb_run(out: &std::path::Path) { pb_census::run(out); }
"""


def native_wave32_fixture(source):
    definition = source[source.index("    fn compare(threads: u32) {"):]
    body = definition[definition.index("        let group = lw.s.group_id(0);"):]
    body = dedent(body[:body.index("        let chain = lw.s.split_compute(")])
    # This is compare(32). Its guest-Wave64-only exchange arm is unreachable.
    split_only = (
        "    if split && round == 8 {\n"
        "        let other_half = lw.exchange(lw.half);\n"
        "        value = lw.add(value, other_half);\n"
        "    }\n"
    )
    if body.count(split_only) != 1:
        raise ValueError("The pinned Wave32 fixture no longer matches its extraction points")
    body = body.replace(split_only, "")
    return '''
fn wave32_loops(out: &Path) {
    let threads = 32;
    let mut lw = Lw::new();
    let tid = lw.s.flattened_thread_id_in_group();
    let mem = lw.mems[0];
''' + "".join(f"    {line}\n" if line else "\n" for line in body.splitlines()) + '''
    let plan = lw.s.m.dispatch_plan(40).unwrap();
    assert!(plan.blocks.len() >= 3);
    assert!(ranges(&lw.s.m, &plan).iter().any(|life| life.words == 2));
    compare("upstream-wave32-loops", &lw.s, &plan, 40, None, out);
}
'''


def original_fixtures(source):
    original = source[source.index("    fn check_persistent_payload(reuse_hole: bool) {"):]
    mix = dedent(original[original.index("        fn mix("):original.index("        fn expected_mix(")])
    body = original[original.index("        let offset = lw.shlc(tid, 2);"):]
    body = dedent(body[:body.index("        let chain = lw.s.split_compute(")])
    return mix + """
fn persistent(reuse_hole: bool, out: &Path) {
    let mut lw = Lw::new();
    let tid = lw.s.flattened_thread_id_in_group();
    let mem = lw.mems[0];
""" + "".join(f"    {line}\n" if line else "\n" for line in body.splitlines()) + """
    let (name, overlap) = if reuse_hole {
        ("upstream-overlap", Some((saved, replacement)))
    } else {
        ("upstream-skip-middle", None)
    };
    compare(name, &lw.s, &plan, limit, overlap, out);
}
"""


def stage_sources(build):
    destination = build / "gpu" / "dxil"
    origin = SOURCE_PATH / DXIL
    for name in SOURCES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin / name, target)
    source = (origin / "module/split.rs").read_text(encoding="utf-8")
    file = destination / "module/split.rs"
    file.write_text(instrumented_emitter(source), encoding="utf-8")
    harness = (ROOT / "census.rs").read_text(encoding="utf-8")
    if harness.count("// UPSTREAM_FIXTURE") != 1:
        raise ValueError("Missing fixture insertion point")
    file.with_name("census.rs").write_text(harness.replace("// UPSTREAM_FIXTURE", original_fixtures(source) + native_wave32_fixture(source)), encoding="utf-8")
    (build / "main.rs").write_text(MAIN, encoding="utf-8")


def report_for(output):
    fixtures = {}
    for line in output.splitlines():
        values = line.split(",")
        if values[0] == "life":
            _, name, value, begin, end, words, fixed, strict = values
            fixtures[name]["intervals"].append({
                "value": int(value), "first_piece": int(begin), "last_piece": int(end), "words": int(words),
                "fixed_slot": int(fixed), "strict_slot": int(strict),
            })
        else:
            name, pieces, fixed, strict, peak, reads, writes, checks, negative = values
            fixtures[name] = {
                "pieces": int(pieces), "fixed_dwords_per_group": int(fixed) * 32,
                "strict_dwords_per_group": int(strict) * 32, "peak_lower_bound_dwords_per_group": int(peak) * 32,
                "static_payload_dwords_read": int(reads), "static_payload_dwords_written": int(writes),
                "checked_scratch_dwords_per_order_and_layout": int(checks), "incorrect_alias_negative_control_mismatches": int(negative),
                "intervals": [],
            }
    return fixtures


def run(rustc, linker, dxv):
    revision = verified_sources()
    with tempfile.TemporaryDirectory(prefix="pb-xcl-2126-census-") as temp:
        build = Path(temp)
        stage_sources(build)
        exe = build / "probe.exe"
        subprocess.run([str(rustc), "--edition=2024", "-D", "warnings", "-C", f"linker={linker}",
                        str(build / "main.rs"), "-o", str(exe)], cwd=build, check=True, timeout=30)
        assets = build / "assets"
        assets.mkdir()
        result = subprocess.run([str(exe), str(assets)], cwd=build, check=True, timeout=8,
                                capture_output=True, text=True)
        fixtures = report_for(result.stdout)
        validated = {}
        for shader in sorted(assets.glob("*.dxil")):
            process = subprocess.run([str(dxv), str(shader)], check=True, capture_output=True,
                                     text=True, timeout=8, cwd=build)
            output = process.stdout + process.stderr
            if "validation succeeded" not in output.casefold():
                raise ValueError(f"DXV did not report validation success for {shader.name}")
            validated[shader.name] = {
                "sha256": hashlib.sha256(shader.read_bytes()).hexdigest(),
                "bytes": shader.stat().st_size,
            }
        if len(validated) != sum(fixture["pieces"] * 2 for fixture in fixtures.values()):
            raise ValueError("Unexpected number of validated pieces")
        toolchain = subprocess.check_output([str(rustc), "--version"], text=True, timeout=5).strip()
        validator = hashlib.sha256(dxv.read_bytes()).hexdigest()
        return {"upstream_revision": revision, "rustc_version": toolchain, "dxv_sha256": validator,
                "fixtures": fixtures, "validated_dxil": validated}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for tool in ("rustc", "linker", "dxv"):
        parser.add_argument(f"--{tool}", type=Path, required=True)
    params = parser.parse_args()
    print(json.dumps(run(*(getattr(params, tool).resolve(strict=True)
                           for tool in ("rustc", "linker", "dxv"))), indent=2))
