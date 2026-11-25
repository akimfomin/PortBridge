"""Compile exact launchers with an instrumented CPU stub. No HIP SDK or GPU required."""

import argparse
import os
import re
from pathlib import Path
import subprocess
import tempfile


HIP_HEADER = r'''
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string_view>

using hipError_t = int;
using hipModule_t = const char*;
using hipFunction_t = const char*;
using hipStream_t = void*;
constexpr hipError_t hipSuccess = 0;
constexpr int hipMemcpyDeviceToHost = 1;
struct hipDeviceProp_t { char name[64]; char gcnArchName[64]; int warpSize; };

inline const char* current_case;
inline const char* hipGetErrorString(hipError_t) { return "CPU test stub failure"; }
inline hipError_t hipGetDevice(int* device) { *device = 0; return 0; }
inline hipError_t hipGetDeviceProperties(hipDeviceProp_t* props, int) {
    std::strcpy(props->name, "CPU mock only");
    std::strcpy(props->gcnArchName, "gfx1030");
    props->warpSize = 32;
    return 0;
}
inline hipError_t hipRuntimeGetVersion(int* version) { *version = 0; return 0; }
inline hipError_t hipDriverGetVersion(int* version) { *version = 0; return 0; }
inline hipError_t hipModuleLoad(hipModule_t* module, const char* name) {
    *module = name;
    current_case = name;
    return 0;
}
inline hipError_t hipModuleGetFunction(hipFunction_t* fn, hipModule_t, const char* name) {
    *fn = name;
    return 0;
}
inline hipError_t hipMalloc(void** pointer, std::size_t bytes) {
    *pointer = std::malloc(bytes);
    return *pointer ? 0 : 1;
}
inline hipError_t hipMemset(void* pointer, int value, std::size_t bytes) {
    std::memset(pointer, value, bytes);
    return 0;
}
inline hipError_t hipModuleLaunchKernel(hipFunction_t fn, unsigned, unsigned, unsigned, unsigned,
                                        unsigned, unsigned, unsigned, hipStream_t,
                                        void** args, void**) {
    auto* output = static_cast<std::uint32_t*>(*static_cast<void**>(args[0]));
    const std::string_view name = fn;
    const std::string_view scenario = current_case;
    const auto separator = scenario.find(':');
    int hole = -1;
    if (separator != std::string_view::npos && scenario.substr(0, separator) == name)
        hole = std::atoi(current_case + separator + 1);
    const auto write = [&](int slot, std::uint32_t value) {
        if (slot != hole) output[slot] = value;
    };
    const auto fill = [&](int begin, int end) {
        for (int slot = begin; slot < end; ++slot) write(slot, 0x11220000u + slot);
    };
    if (name == "mullit_probe") {
        fill(1, 15);
        write(1, 0x40c00000);
    } else if (name == "fminmax_probe") {
        fill(4, 10);
        write(6, 0x40400000);
        write(9, 0x40a00000);
        const std::uint32_t controls[]{0x3f800000, 0x3f800000, 0x40400000, 0x40a00000,
                                       0x3f800000, 0x3f800000, 0x40a00000, 0x40a00000};
        for (int i = 0; i < 8; ++i) write(12 + i, controls[i]);
    } else if (name == "inline16_probe") {
        fill(1, 13);
        write(4, 5);
    } else if (name == "fma_nan_ieee0" || name == "fma_nan_ieee1") {
        fill(1, 15);
        write(1, 0x40e00000);
    } else if (name == "fract_f64_ieee0" || name == "fract_f64_ieee1") {
        fill(2, 22);
        write(1, 0);
        write(2, 0);
        write(3, 0x3fd00000);
        write(4, 0);
        write(5, 0x3fe80000);
        write(8, 0xffffffff);
        write(9, 0x3fefffff);
        write(20, 0);
        write(21, 0);
    } else {
        return 1;
    }
    write(0, 0xffffffff);
    return 0;
}
inline hipError_t hipDeviceSynchronize() { return 0; }
inline hipError_t hipMemcpy(void* dst, const void* src, std::size_t bytes, int) {
    std::memcpy(dst, src, bytes);
    return 0;
}
inline hipError_t hipFree(void* pointer) { std::free(pointer); return 0; }
inline hipError_t hipModuleUnload(hipModule_t) { return 0; }
'''


# These slots include execution and numeric controls but omit documented padding.
PROBES = {
    "rdna2-mullit": (("mullit_probe", range(15)),),
    "rdna2-float-atomic-nan": (("fminmax_probe", (0, *range(4, 10), *range(12, 20))),),
    "rdna2-inline-float-16bit-int": (("inline16_probe", range(13)),),
    "rdna2-fma-nan": (("fma_nan_ieee1", range(15)), ("fma_nan_ieee0", range(15))),
    "rdna2-fract-f64": (("fract_f64_ieee1", range(22)), ("fract_f64_ieee0", range(22))),
}
REPORT = re.compile(r"^(?:ieee[01] )?initial_exec=", re.MULTILINE)


def assert_case(executable, scenario, status, expected_lines):
    result = subprocess.run([str(executable), scenario], capture_output=True, text=True, timeout=5)
    if (result.returncode != status or len(REPORT.findall(result.stdout)) != expected_lines or
            "aaaaaaaa" in result.stdout):
        raise AssertionError(f"{executable.name} {scenario}: exit={result.returncode}\n"
                             f"{result.stdout}{result.stderr}")


def run(source, compiler):
    covered = 0
    with tempfile.TemporaryDirectory(prefix="portbridge-hip-host-") as temp:
        folder = Path(temp)
        headers = folder / "hip"
        headers.mkdir()
        (headers / "hip_runtime_api.h").write_text(HIP_HEADER, encoding="ascii")
        for probe, kernels in PROBES.items():
            launcher = source / "contrib" / probe / "launch.cpp"
            executable = folder / (probe + (".exe" if os.name == "nt" else ""))
            command = [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(folder)]
            if os.name == "nt":
                command.append("-static")
            subprocess.run([*command, str(launcher), "-o", str(executable)], check=True, timeout=30)
            assert_case(executable, "complete", 0, len(kernels))
            for kernel, slots in kernels:
                for slot in slots:
                    assert_case(executable, f"{kernel}:{slot}", 1, 0)
                    covered += 1
    print(f"CPU-only: {len(PROBES)} complete-output controls and {covered} single-word omission cases passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="PortBridge worktree to check")
    parser.add_argument("--cxx", default="clang++", help="GNU-style C++17 compiler")
    args = parser.parse_args()
    run(args.source.resolve(), args.cxx)


if __name__ == "__main__":
    main()
