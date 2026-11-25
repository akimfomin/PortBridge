"""Prepare a bounded real-Vulkan A/B for the checker admission patch."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TOOLS = REPO.parent / "Leonida-portable-vulkan" / "tools"
GENERATED = HERE / "generated"
FIXTURES = GENERATED / "spirv"
BASE = "507029d1ea8dc65f1fabb68739605d6821843bf1"
CHECKER = Path("runtime/test/vk_pipeline_check.cpp")
GATE = Path("runtime/test/large_module_gate.h")
HEADERS = TOOLS / "Vulkan-Headers-6802bb4733b63ed5efd3adb308a6c885ef180ea1" / "include"
VULKAN_TOOLS = TOOLS / "khronos-shader-tools" / "install" / "bin"
COMPILER = TOOLS / "llvm-mingw-20261117-ucrt-x86_64" / "bin" / "clang++.exe"
THRESHOLD, SIZE_LIMIT = 300, 1024
ADAPTER = "NVIDIA GeForce RTX 4070 Ti SUPER"
LARGE = tuple(f"large_{i}" for i in range(4))
SMALL = tuple(f"small_{i}" for i in range(2))
NAMES = LARGE + SMALL
VARIANTS = ("baseline", "candidate")
MODES = ("stock", "observed")

ASM = """OpCapability Shader
OpMemoryModel Logical GLSL450
OpEntryPoint GLCompute %main "main"
OpExecutionMode %main LocalSize {lanes} 1 1
%void = OpTypeVoid
%fn = OpTypeFunction %void
%main = OpFunction %void None %fn
%entry = OpLabel
{padding}OpReturn
OpFunctionEnd
"""


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO, timeout=10)


def digest(value):
    return sha256(value).hexdigest()


def insert(source, anchor, replacement):
    if source.count(anchor) != 1:
        raise RuntimeError(f"Expected one upstream hook anchor: {anchor!r}")
    return source.replace(anchor, replacement)


def observed_source(blob):
    source = blob.decode("utf-8").replace("\r\n", "\n")
    anchor = "    auto record_pipe = [&]"
    source = insert(source, anchor, "    std::atomic<unsigned> pb_hold_slots{0};\n" + anchor)
    anchor = "            st.pipes_ok++;\n"
    source = insert(source, anchor, anchor + '            std::printf("PB_PIPE_OK %s\\n", name.c_str());\n')
    anchor = "            const auto code = leonida::read_spirv_words(f, file_size);\n"
    source = insert(source, anchor, '''            const bool pb_hold = isolated && pb_hold_slots.fetch_add(1, std::memory_order_relaxed) < 2;
            if (pb_hold) std::printf("PB_HOLD_BEGIN %s\\n", name.c_str());
''' + anchor)
    anchor = "            if (++done % 1000 == 0) {\n"
    source = insert(source, anchor, '''            // The actual Vulkan calls and object cleanup have finished. Keep the original permit
            // live for a bounded observation window before its usual end-of-iteration release.
            if (pb_hold) {
                std::this_thread::sleep_for(std::chrono::milliseconds(1000));
                std::printf("PB_HOLD_END %s\\n", name.c_str());
            }
''' + anchor)
    return source.encode("utf-8")


def prepare():
    if git("rev-parse", "HEAD").decode().strip() != BASE:
        raise RuntimeError("The candidate checkout no longer has the recorded baseline")
    changed = set(git("diff", "--name-only", BASE, "--", "runtime").decode().splitlines())
    expected = {CHECKER.as_posix(), GATE.as_posix(), "runtime/test/large_module_gate_test.cpp"}
    if changed != expected:
        raise RuntimeError(f"Unexpected runtime changes in the candidate: {sorted(changed)}")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    fixture_index = {}
    for lanes, name in enumerate(NAMES, start=1):
        assembly = ASM.format(lanes=lanes, padding="OpNop\n" * 96 if name in LARGE else "")
        (FIXTURES / f"{name}.spvasm").write_text(assembly, encoding="ascii", newline="\n")
        fixture_index[name] = {"stage": "cs", "subgroup_size": None, "features": []}
    write_json(FIXTURES / "index.json", fixture_index)
    source_hashes = {}
    for variant in VARIANTS:
        originals = {
            path: git("show", f"{BASE}:{path.as_posix()}") if variant == "baseline" else (REPO / path).read_bytes()
            for path in (CHECKER, GATE)
        }
        for mode in MODES:
            folder = GENERATED / f"{variant}-{mode}"
            folder.mkdir(exist_ok=True)
            source = originals[CHECKER] if mode == "stock" else observed_source(originals[CHECKER])
            (folder / CHECKER.name).write_bytes(source)
            (folder / GATE.name).write_bytes(originals[GATE])
            source_hashes[folder.name] = {CHECKER.name: digest(source), GATE.name: digest(originals[GATE])}
    write_json(GENERATED / "source-hashes.json", {"baseline": BASE, "sources": source_hashes})


def assemble():
    manifest = {}
    for name in NAMES:
        source = FIXTURES / f"{name}.spvasm"
        module = source.with_suffix(".spv")
        subprocess.run([str(VULKAN_TOOLS / "spirv-as.exe"), "--target-env", "vulkan1.1", str(source), "-o", str(module)],
                       check=True, timeout=8)
        subprocess.run([str(VULKAN_TOOLS / "spirv-val.exe"), "--target-env", "vulkan1.1", str(module)],
                       check=True, timeout=8)
        content = module.read_bytes()
        if not 0 < len(content) <= SIZE_LIMIT or (len(content) > THRESHOLD) != (name in LARGE):
            raise RuntimeError(f"Incorrect fixture class or size for {name}: {len(content)} bytes")
        manifest[name] = {"bytes": len(content), "sha256": digest(content)}
    write_json(GENERATED / "fixture-hashes.json", manifest)


def build(mode):
    provenance = json.loads((GENERATED / "source-hashes.json").read_text(encoding="utf-8"))
    for variant in VARIANTS:
        folder = GENERATED / f"{variant}-{mode}"
        for name, expected in provenance["sources"][folder.name].items():
            if digest((folder / name).read_bytes()) != expected:
                raise RuntimeError(f"Generated source changed: {folder / name}")
        source = folder / CHECKER.name
        target = folder / "vk_pipeline_check.exe"
        subprocess.run([str(COMPILER), "-std=c++20", "-O1", "-pthread", "-static", "-DWIN32_LEAN_AND_MEAN",
                        "-DNOMINMAX", "-isystem", str(HEADERS), "-I", str(REPO / CHECKER.parent),
                        str(source), "-o", str(target)], check=True, timeout=120)


def observe(stdout, expected_early):
    events = re.findall(r"^PB_(HOLD_BEGIN|HOLD_END|PIPE_OK) ((?:large|small)_\d)$", stdout, re.M)
    successes = [name for event, name in events if event == "PIPE_OK"]
    holders = [name for event, name in events if event == "HOLD_BEGIN"]
    releases = [name for event, name in events if event == "HOLD_END"]
    if sorted(successes) != sorted(NAMES) or len(holders) != 2 or sorted(holders) != sorted(releases):
        raise RuntimeError(f"Incomplete pipeline or permit events: {events}")
    for name in holders:
        if not events.index(("HOLD_BEGIN", name)) < events.index(("PIPE_OK", name)) < events.index(("HOLD_END", name)):
            raise RuntimeError(f"The holder did not complete an actual Vulkan pipeline before release: {name}")
    first_release = next(index for index, (event, _) in enumerate(events) if event == "HOLD_END")
    early = [name for event, name in events[:first_release] if event == "PIPE_OK" and name in SMALL]
    if bool(early) != expected_early:
        raise RuntimeError(f"Unexpected scheduling observation: small jobs before holder release = {early}, events = {events}")
    return {"events": events, "small_pipeline_completed_before_first_release": early}


def run(mode):
    fixture_hashes = json.loads((GENERATED / "fixture-hashes.json").read_text(encoding="utf-8"))
    for name in NAMES:
        content = (FIXTURES / f"{name}.spv").read_bytes()
        expected = fixture_hashes[name]
        if len(content) != expected["bytes"] or digest(content) != expected["sha256"]:
            raise RuntimeError(f"Unvalidated fixture {name}")
        if not 0 < len(content) <= SIZE_LIMIT or (len(content) > THRESHOLD) != (name in LARGE):
            raise RuntimeError(f"Incorrect fixture class or size for {name}")
    env = dict(os.environ, LEONIDA_VK_DEVICE=ADAPTER)
    env.pop("VK_PIPELINE_CHECK_SIMULATE_CRASH", None)
    results = {}
    for variant in VARIANTS:
        folder = GENERATED / f"{variant}-{mode}"
        target = (folder / "vk_pipeline_check.exe").resolve(strict=True)
        command = [str(target), str(FIXTURES), "--jobs", "4", "--large-parallel", "2",
                   "--large-module-bytes", str(THRESHOLD), "--max-bytes", str(SIZE_LIMIT), "--stage", "cs"]
        proc = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=12)
        (folder / "run.log").write_text(proc.stdout + "\n[stderr]\n" + proc.stderr, encoding="utf-8", newline="\n")
        if (proc.returncode or f"device: {ADAPTER} (" not in proc.stderr
                or "cs: 6 modules ok, 0 failed" not in proc.stdout
                or "cs pipelines: 6 ok, 0 failed, 0 skipped" not in proc.stdout
                or f"large modules checked within the memory budget: 4 (over {THRESHOLD} bytes)" not in proc.stdout):
            raise RuntimeError(f"Vulkan validation failed for {variant} {mode}. See {folder / 'run.log'}")
        results[variant] = {"command": command, "exe_sha256": digest(target.read_bytes()), "pipeline_count": 6}
        if mode == "observed":
            results[variant] |= observe(proc.stdout, variant == "candidate")
        print(f"{variant} {mode}: {results[variant]}")
        write_json(GENERATED / f"{mode}-results.json", results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "assemble", "build", "run"))
    parser.add_argument("--mode", choices=MODES, default="stock")
    args = parser.parse_args()
    if args.action in ("prepare", "assemble"):
        {"prepare": prepare, "assemble": assemble}[args.action]()
    else:
        {"build": build, "run": run}[args.action](args.mode)


if __name__ == "__main__":
    main()
