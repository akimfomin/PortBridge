// SPDX-License-Identifier: MIT
#include <hip/hip_runtime_api.h>
#include "results.hpp"

#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string_view>

static void check(hipError_t status, const char* operation) {
    if (status != hipSuccess) {
        std::fprintf(stderr, "%s: %s\n", operation, hipGetErrorString(status));
        std::exit(1);
    }
}

int main(int argc, char** argv) {
    if (argc != 2) {
        std::fprintf(stderr, "Usage: %s pack_probe.hsaco\n", argv[0]);
        return 2;
    }

    int device = 0, runtime = 0, driver = 0;
    hipDeviceProp_t properties{};
    check(hipGetDevice(&device), "get device");
    check(hipGetDeviceProperties(&properties, device), "get properties");
    const std::string_view arch(properties.gcnArchName);
    if (properties.warpSize != 32 || arch.size() < 7 || arch.substr(0, 6) != "gfx103" ||
        arch[6] < '0' || arch[6] > '6' || (arch.size() > 7 && arch[7] != ':')) {
        std::fprintf(stderr, "A physical gfx103x Wave32 device is required\n");
        return 2;
    }
    check(hipRuntimeGetVersion(&runtime), "get runtime version");
    check(hipDriverGetVersion(&driver), "get driver API version");

    hipModule_t module{};
    hipFunction_t kernel{};
    check(hipModuleLoad(&module, argv[1]), "load code object");
    check(hipModuleGetFunction(&kernel, module, "pack_probe"), "get pack_probe");
    Rows captures[2]{};
    void* output = nullptr;
    check(hipMalloc(&output, sizeof(Rows)), "allocate output");
    void* arguments[]{&output};
    for (int pass = 0; pass < 2; ++pass) {
        check(hipMemset(output, pass == 0 ? 0 : 0xff, sizeof(Rows)), "initialize output");
        check(hipModuleLaunchKernel(kernel, 1, 1, 1, 32, 1, 1, 0, nullptr, arguments, nullptr),
              "launch one wave");
        check(hipDeviceSynchronize(), "synchronize device");
        check(hipMemcpy(captures[pass].data(), output, sizeof(Rows), hipMemcpyDeviceToHost),
              "read output");
    }
    check(hipFree(output), "free output");
    check(hipModuleUnload(module), "unload code object");

    if (const char* error = validate(captures[0], captures[1])) {
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    const Rows& rows = captures[0];

    std::printf("device=%s arch=%s warp=%d HIP-runtime=%d HIP-driver=%d\n",
                properties.name, properties.gcnArchName, properties.warpSize, runtime, driver);
    std::printf("initial_exec=%08" PRIx32 " control=%08" PRIx32 " a1-a4=", rows[0].value, rows[1].value);
    for (std::size_t i = 2; i < rows.size(); ++i) {
        std::printf(i == 2 ? "%08" PRIx32 : ",%08" PRIx32, rows[i].value);
    }
    std::printf("\n");
}
