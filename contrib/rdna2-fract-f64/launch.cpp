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

using Result = std::array<std::uint32_t, 22>;

static Result read_probe(hipModule_t module, const char* name) {
    hipFunction_t kernel{};
    check(hipModuleGetFunction(&kernel, module, name), name);

    Result result{};
    void* device_result = nullptr;
    check(hipMalloc(&device_result, sizeof(result)), "allocate output");
    check(hipMemset(device_result, 0xaa, sizeof(result)), "initialize output");
    void* arguments[]{&device_result};
    check(hipModuleLaunchKernel(kernel, 1, 1, 1, 32, 1, 1, 0, nullptr, arguments, nullptr),
          "launch one Wave32");
    check(hipDeviceSynchronize(), "synchronize device");
    check(hipMemcpy(result.data(), device_result, sizeof(result), hipMemcpyDeviceToHost), "read output");
    check(hipFree(device_result), "free output");

    return result;
}

static std::uint64_t value(const Result& result, int i) {
    return (std::uint64_t{result[2 * i + 1]} << 32) | result[2 * i];
}

static void print_result(const Result& result, const char* label) {
    std::printf("%s initial_exec=%08" PRIx32 " d1-d10=", label, result[0]);
    for (int i = 1; i <= 10; ++i) {
        std::printf(i == 1 ? "%016" PRIx64 : ",%016" PRIx64, value(result, i));
    }
    std::printf("\n");
}

static bool valid(const Result& result) {
    // Finite controls, equal under every hypothesis.
    const bool complete = std::find(result.begin() + 2, result.end(), 0xaaaaaaaa) == result.end();
    return complete && result[0] == UINT32_MAX && result[1] == 0 &&
           value(result, 1) == 0x3fd0000000000000 && value(result, 2) == 0x3fe8000000000000 &&
           value(result, 4) == 0x3fefffffffffffff && value(result, 10) == 0;
}

int main(int argc, char** argv) {
    if (argc != 2) {
        std::fprintf(stderr, "Usage: %s fract_f64_probe.hsaco\n", argv[0]);
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
    const Result ieee1 = read_probe(module, "fract_f64_ieee1");
    const Result ieee0 = read_probe(module, "fract_f64_ieee0");
    check(hipModuleUnload(module), "unload module");
    if (!valid(ieee1) || !valid(ieee0)) {
        std::fprintf(stderr, "Probe controls failed or output is incomplete\n");
        return 1;
    }
    print_result(ieee1, "ieee1");
    print_result(ieee0, "ieee0");
}
