#include <hip/hip_runtime_api.h>

#include <array>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

static void check(hipError_t status, const char* operation) {
    if (status != hipSuccess) {
        std::fprintf(stderr, "%s: %s\n", operation, hipGetErrorString(status));
        std::exit(1);
    }
}

// Runs one kernel of fma_nan_probe.s and prints its line. Returns false if a control fails.
static bool run(hipModule_t module, const char* name, const char* label) {
    hipFunction_t kernel{};
    check(hipModuleGetFunction(&kernel, module, name), name);

    std::array<std::uint32_t, 15> result{};
    void* device_result = nullptr;
    check(hipMalloc(&device_result, sizeof(result)), "allocate output");
    check(hipMemset(device_result, 0xaa, sizeof(result)), "initialize output");
    void* arguments[]{&device_result};
    check(hipModuleLaunchKernel(kernel, 1, 1, 1, 32, 1, 1, 0, nullptr, arguments, nullptr),
          "launch one Wave32");
    check(hipDeviceSynchronize(), "synchronize device");
    check(hipMemcpy(result.data(), device_result, sizeof(result), hipMemcpyDeviceToHost), "read output");
    check(hipFree(device_result), "free output");

    // f1..f14 in the order of fma_nan_probe.s.
    std::printf("%s initial_exec=%08" PRIx32 " f1-f14=", label, result[0]);
    for (int i = 1; i <= 14; ++i) {
        std::printf(i == 1 ? "%08" PRIx32 : ",%08" PRIx32, result[i]);
    }
    std::printf("\n");
    // f1 is 2 * 3 + 1: 7.0 under every hypothesis.
    return result[0] == UINT32_MAX && result[1] == 0x40e00000;
}

int main(int argc, char** argv) {
    if (argc != 2) {
        std::fprintf(stderr, "Usage: %s fma_nan_probe.hsaco\n", argv[0]);
        return 2;
    }

    int device = 0;
    int runtime = 0;
    int driver = 0;
    hipDeviceProp_t properties{};
    check(hipGetDevice(&device), "get device");
    check(hipGetDeviceProperties(&properties, device), "get device properties");
    check(hipRuntimeGetVersion(&runtime), "get runtime version");
    check(hipDriverGetVersion(&driver), "get driver API version");
    std::printf("device=%s arch=%s warp=%d HIP-runtime=%d HIP-driver=%d\n",
                properties.name, properties.gcnArchName, properties.warpSize, runtime, driver);
    if (properties.warpSize != 32 || std::strncmp(properties.gcnArchName, "gfx103", 6) != 0) {
        std::fprintf(stderr, "An RDNA2 gfx103x device in Wave32 mode is required\n");
        return 2;
    }

    hipModule_t module{};
    check(hipModuleLoad(&module, argv[1]), "load assembled module");
    const bool ieee1 = run(module, "fma_nan_ieee1", "ieee1");
    const bool ieee0 = run(module, "fma_nan_ieee0", "ieee0");
    check(hipModuleUnload(module), "unload module");
    if (!ieee1 || !ieee0) {
        std::fprintf(stderr, "Probe controls failed\n");
        return 1;
    }
}
