"""Compile the exact before/after worker code against deterministic CPU-only fixture steps."""

import argparse
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
REPO = HERE.parent
WORKER = "runtime/test/vk_pipeline_check.cpp"
HEADER = "runtime/test/large_module_gate.h"


def base_file(path):
    return subprocess.run(["git", "show", f"HEAD:{path}"], cwd=REPO, check=True,
                          capture_output=True, text=True, encoding="utf-8", timeout=5).stdout


def insert_sources(template, source, header, output):
    start = source.index("    auto worker = [&] {")
    end = source.index("            const std::string& name = *work[k].first;", start)
    gate_start = source.index("            const bool isolated = large_module_bytes", end)
    gate_end = source.index("            {   // in flight", gate_start)
    decl = "    const bool budgeted_work ="
    if decl in source:
        decl_start = source.index(decl)
        decl_end = source.index("work.size());\n", decl_start) + len("work.size());")
        setup = source[decl_start:decl_end]
    else:
        setup = ""
    generated = (template.replace("@WORKER_LOOP@", source[start:end].rstrip())
                 .replace("@GATE_STEP@", source[gate_start:gate_end].rstrip()).replace("@QUEUE_SETUP@", setup))
    wait = "        cv_.wait(l, [&] { return admits_locked(estimate); });"
    if header.count(wait) != 1:
        raise RuntimeError("Expected exactly one production blocking admission")
    observed = "        if (!admits_locked(estimate)) ::record_wait_for_test();\n" + wait
    (output / "large_module_gate.h").write_text(header.replace(wait, observed), encoding="utf-8", newline="\n")
    (output / "worker_probe.cpp").write_text(generated, encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler")
    args = parser.parse_args()
    template = (HERE / "worker_probe.cpp.in").read_text(encoding="utf-8")
    results = {}
    for variant in ("baseline", "candidate"):
        read = base_file if variant == "baseline" else lambda path: (REPO / path).read_text(encoding="utf-8")
        output = HERE / f"worker-probe-{variant}"
        output.mkdir(exist_ok=True)
        insert_sources(template, read(WORKER), read(HEADER), output)
        executable = output / "worker_probe.exe"
        subprocess.run([args.compiler, "-std=c++20", "-O2", "-Wformat=2", "-pthread", "-static",
                        str(output / "worker_probe.cpp"), "-o", str(executable)], check=True, timeout=25)
        run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
        print(f"{variant} exit {run.returncode}\n{run.stdout}", end="")
        first = "saturated: FAIL, first=waited, order= 0 1" if variant == "baseline" else "saturated: PASS, first=small, order= 1 0"
        expected_exit = 1 if variant == "baseline" else 0
        if run.returncode != expected_exit or first not in run.stdout or run.stdout.count(": PASS,") != (3 if variant == "baseline" else 4):
            raise RuntimeError(f"Unexpected worker observation on {variant}: {run.stdout}\n{run.stderr}")
        results[variant] = {"exit": run.returncode, "report": run.stdout.splitlines()}
    report = {"revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
              "fixture": "production selection and admission statements, synthetic job classification and completion",
              "results": results}
    (HERE / "production-regression.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
