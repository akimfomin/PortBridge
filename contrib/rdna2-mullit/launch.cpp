#include <hip/hip_runtime_api.h>

#include <algorithm>
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

int main(int argc, char** argv) {
    if (argc != 2) {
        std::fprintf(stderr, "Usage: %s mullit_probe.hsaco\n", argv[0]);
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
    hipFunction_t kernel{};
    check(hipModuleLoad(&module, argv[1]), "load assembled module");
    check(hipModuleGetFunction(&kernel, module, "mullit_probe"), "get mullit_probe");

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
    check(hipModuleUnload(module), "unload module");

    // c1 is 2 * 3 with S2 = 1.0: 6.0 under every hypothesis.
    const bool complete = std::find(result.begin(), result.end(), 0xaaaaaaaa) == result.end();
    if (result[0] != UINT32_MAX || result[1] != 0x40c00000 || !complete) {
        std::fprintf(stderr, "Probe controls failed or output is incomplete\n");
        return 1;
    }

    // c1..c14 in the order of mullit_probe.s.
    std::printf("initial_exec=%08" PRIx32 " c1-c14=", result[0]);
    for (int i = 1; i <= 14; ++i) {
        std::printf(i == 1 ? "%08" PRIx32 : ",%08" PRIx32, result[i]);
    }
    std::printf("\n");
}
