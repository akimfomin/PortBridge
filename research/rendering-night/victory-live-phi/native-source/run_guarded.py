# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the CPU readback oracle, or run the fixed native batch after approval."""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


GIB = 1 << 30
INPUTS = (0x13579bdf, 0x2468ace0)
WORKER = Path(__file__).resolve().with_name("victory_phi_readback.exe")
CASES = [(arm, width, seeds) for width in (2, 16) for seeds in (1, 2)
         for arm in ("control", "candidate")]
CASE_NAMES = {f"{arm}-{width}-{seeds}": (arm, width, seeds) for arm, width, seeds in CASES}


class Performance(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint32)] + [
        (name, ctypes.c_size_t) for name in (
            "commit_total", "commit_limit", "commit_peak", "memory_total", "memory_available",
            "system_cache", "kernel_total", "kernel_paged", "kernel_nonpaged", "page_size")
    ] + [(name, ctypes.c_uint32) for name in ("handles", "processes", "threads")]


def check_memory():
    get = ctypes.WinDLL("psapi", use_last_error=True).GetPerformanceInfo
    get.argtypes = (ctypes.POINTER(Performance), ctypes.c_uint32)
    get.restype = ctypes.c_int
    memory = Performance()
    memory.size = ctypes.sizeof(memory)
    if not get(ctypes.byref(memory), memory.size):
        raise ctypes.WinError(ctypes.get_last_error())
    commit = (memory.commit_limit - memory.commit_total) * memory.page_size
    physical = memory.memory_available * memory.page_size
    if commit < 4 * GIB or physical < 6 * GIB:
        raise RuntimeError(f"Memory below guard (commit {commit / GIB:.2f} GiB, RAM {physical / GIB:.2f} GiB)")
    return {"commit_bytes_available": commit, "ram_bytes_available": physical}


def expected_words(width, seeds):
    registers = [INPUTS[i % seeds] for i in range(width)]
    for _ in range(3):
        registers = registers[1:] + registers[:1]
    return registers


def check_output(output, width, seeds):
    lines = re.findall(r"^OUT ([0-9a-f]{8}(?: [0-9a-f]{8})*)$", output, re.MULTILINE)
    if len(lines) != 1:
        raise ValueError("Expected exactly one OUT line")
    words = [int(word, 16) for word in lines[0].split()]
    if words != expected_words(width, seeds):
        raise ValueError(f"Unexpected words for {width} registers and {seeds} seeds: {words}")
    return words


def self_test():
    assert check_output("OUT 13579bdf 13579bdf\n", 2, 1) == [INPUTS[0], INPUTS[0]]
    assert check_output("OUT 2468ace0 13579bdf\n", 2, 2) == [INPUTS[1], INPUTS[0]]
    assert len(expected_words(16, 2)) == 16
    for output in ["", "OUT 13579bdf 2468ace0\n", "OUT 2468ace0 13579bdf\nOUT 2468ace0 13579bdf\n"]:
        try:
            check_output(output, 2, 2)
        except ValueError:
            continue
        raise AssertionError(f"Unexpected acceptance: {output!r}")
    print("CPU oracle passed fixed and rejection cases")


def checkpoint(output, report):
    temporary = output / "readback.json.tmp"
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output / "readback.json")


def readback(output, selected):
    digest = hashlib.sha256(WORKER.read_bytes()).hexdigest()
    output.mkdir()
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("VICTORY_", "PORTBRIDGE_VICTORY_"))}
    env["PORTBRIDGE_VICTORY_READBACK"] = "1"
    report = {"worker_sha256": digest, "adapter_luid": None, "status": "in_progress", "results": []}
    for name, (arm, width, seeds) in CASE_NAMES.items():
        if selected and name not in selected:
            continue
        try:
            memory = check_memory()
            log = output / f"{name}.log"
            try:
                child = subprocess.run([str(WORKER), arm, str(width), str(seeds)], env=env, timeout=10,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            except subprocess.TimeoutExpired as error:
                log.write_bytes(error.stdout or b"")
                raise RuntimeError(f"Stopped after a 10 second process timeout: {name}") from error
            log.write_bytes(child.stdout)
            child.check_returncode()
            text = child.stdout.decode("utf-8").replace("\r\n", "\n")
            devices = re.findall(r"^ADAPTER NVIDIA GeForce RTX 4070 Ti SUPER LUID ([0-9a-f]{8}:[0-9a-f]{8})$",
                                 text, re.MULTILINE)
            device = report["adapter_luid"]
            if len(devices) != 1 or (device is not None and device != devices[0]):
                raise RuntimeError(f"Inconsistent native adapter evidence: {name}")
            report["adapter_luid"] = devices[0]
            words = check_output(text, width, seeds)
        except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
            report.update(status="stopped", case=name, error=str(error))
            checkpoint(output, report)
            raise
        report["results"].append({"case": name, "words": words, **memory})
        checkpoint(output, report)
        print(f"{name}: {len(words)} words agree", flush=True)
    report["status"] = "complete"
    checkpoint(output, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="CPU comparator only")
    parser.add_argument("--approved-native", action="store_true", help="Run only with the allocated native GPU slot")
    parser.add_argument("--output", type=Path, help="New output directory")
    parser.add_argument("--case", action="append", choices=CASE_NAMES,
                        help="Select a fixed case. Repeat to select several")
    args = parser.parse_args()
    if args.self_test and not args.approved_native:
        self_test()
    elif args.approved_native and not args.self_test and args.output:
        readback(args.output, set(args.case or ()))
    else:
        parser.error("Select --self-test or --approved-native with --output")


if __name__ == "__main__":
    main()
