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

int main(int argc, char** argv) {
    if (argc != 2) {
        std::fprintf(stderr, "Usage: %s carry_probe.hsaco\n", argv[0]);
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
    check(hipModuleGetFunction(&kernel, module, "carry_probe"), "get carry_probe");

    std::array<std::uint32_t, 6> result{};
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

    std::printf("initial_exec=%08" PRIx32 " sum_e32=%08" PRIx32 " sum_e64=%08" PRIx32
                " carry_e32=%08" PRIx32 " carry_e64=%08" PRIx32 " compare_vcc=%08" PRIx32 "\n",
                result[0], result[1], result[2], result[3], result[4], result[5]);
    if (result[0] != UINT32_MAX || result[1] != 0 || result[2] != 0 ||
        (result[3] & 1) == 0 || (result[4] & 1) == 0 || result[5] != 1) {
        std::fprintf(stderr, "Probe controls failed\n");
        return 1;
    }
}
