# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the exact public first-use/eager cache control flow with fake Vulkan."""

import argparse
from hashlib import sha256
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
HEAD = "eb6a08cd359d98b5777e70d54d0ae8a75879495a"


def source(repo, file):
    return subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{HEAD}:{file}"], timeout=15,
    ).decode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--clang", type=Path, required=True)
    args = parser.parse_args()
    body = source(args.repo, "runtime/shims/d3d12_vulkan_device.cpp")
    start = "        if(device_.info.first_use_backend_pipelines && (!pipeline_info.stage.pNext"
    assert body.count(start) == 1, "Expected the exact public compute branch"
    offset = body.index(start)
    end = body.index("        // The code base:", offset)
    compute = body[offset:end]
    assert compute.count("vkCreateComputePipelines") == 2
    assert compute.count("save_session_pipeline_cache") == 1
    profile = source(args.repo, "runtime/src/main.cpp")
    assert '{L"LEONIDA_PIPELINE_COMPILE", L"on-demand"}' in profile
    assert 'info.prepare_on_bind = mode == "on-demand"' in body
    assert 'info.first_use_backend_pipelines = info.prepare_on_bind || mode == "first-use";' in body
    workload = HERE / "checkpoint_probe.cpp"
    marker = "        // INSERT EXACT PUBLIC CONTROL AND MATERIALIZE BRANCHES\n"
    template = (HERE / "checkpoint_probe.cpp.in").read_text(encoding="utf-8")
    assert template.count(marker) == 1
    workload.write_text(template.replace(marker, compute), encoding="utf-8", newline="\n")
    executable = HERE / "checkpoint_probe.exe"
    subprocess.run(
        [str(args.clang.resolve(strict=True)), "-std=c++20", "-O2", "-Wall", "-Wextra",
         "-Werror", "-static", str(workload), "-o", str(executable)],
        check=True, timeout=25,
    )
    output = subprocess.check_output([executable], timeout=4, text=True, encoding="utf-8")
    data = f"Public head {HEAD}\nCompute branch SHA-256 {sha256(compute.encode()).hexdigest()}\n{output}"
    (HERE / "checkpoint-result.log").write_text(data, encoding="utf-8", newline="\n")
    print(data, end="")


if __name__ == "__main__":
    main()
