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
        std::fprintf(stderr, "Usage: %s fminmax_probe.hsaco\n", argv[0]);
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
    check(hipModuleGetFunction(&kernel, module, "fminmax_probe"), "get fminmax_probe");

    std::array<std::uint32_t, 20> result{};
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

    // Final memory words. Words 1-3 and 10-11 are padding and are not printed.
    const auto list = [&](const char* name, int first, int last) {
        std::printf(" %s=", name);
        for (int i = first; i <= last; ++i) {
            std::printf(i == first ? "%08" PRIx32 : ",%08" PRIx32, result[i]);
        }
    };
    std::printf("initial_exec=%08" PRIx32, result[0]);
    list("global_fmin", 4, 6);
    list("global_fmax", 7, 9);
    list("ds_min", 12, 15);
    list("ds_max", 16, 19);
    std::printf("\n");
    // Number-only global cases agree under every hypothesis: min(5, 3) = 3.0 and max(3, 5) = 5.0.
    // The LDS words must match the gfx1036 measurement: a quiet NaN loses to a number either way.
    const std::uint32_t lds[8]{0x3f800000, 0x3f800000, 0x40400000, 0x40a00000,
                               0x3f800000, 0x3f800000, 0x40a00000, 0x40a00000};
    bool controls = result[0] == UINT32_MAX && result[6] == 0x40400000 && result[9] == 0x40a00000;
    for (int i = 0; i < 8; ++i) {
        controls = controls && result[12 + i] == lds[i];
    }
    if (!controls) {
        std::fprintf(stderr, "Probe controls failed\n");
        return 1;
    }
}
