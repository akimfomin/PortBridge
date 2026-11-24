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
        std::fprintf(stderr, "Usage: %s bpermute_probe.hsaco\n", argv[0]);
        return 2;
    }

    int device = 0;
    int runtime = 0;
    int driver = 0;
    hipDeviceProp_t info{};
    check(hipGetDevice(&device), "get device");
    check(hipGetDeviceProperties(&info, device), "get device properties");
    check(hipRuntimeGetVersion(&runtime), "get runtime version");
    check(hipDriverGetVersion(&driver), "get driver API version");
    std::printf("device=%s arch=%s default_warp=%d HIP-runtime=%d HIP-driver=%d\n",
                info.name, info.gcnArchName, info.warpSize, runtime, driver);
    if (std::strncmp(info.gcnArchName, "gfx1036", 7) != 0 ||
        (info.gcnArchName[7] && info.gcnArchName[7] != ':')) {
        std::fprintf(stderr, "The module targets gfx1036\n");
        return 2;
    }

    hipModule_t module{};
    hipFunction_t kernel{};
    check(hipModuleLoad(&module, argv[1]), "load assembled module");
    check(hipModuleGetFunction(&kernel, module, "bpermute_probe"), "get bpermute_probe");

    std::array<std::array<std::uint32_t, 4>, 64> result{};
    static_assert(sizeof(result) == 1024);
    void* device_result = nullptr;
    check(hipMalloc(&device_result, sizeof(result)), "allocate output");
    check(hipMemset(device_result, 0xaa, sizeof(result)), "initialize output sentinel");
    void* arguments[]{&device_result};
    check(hipModuleLaunchKernel(kernel, 1, 1, 1, 64, 1, 1, 0, nullptr, arguments, nullptr),
          "launch one 64-thread workgroup");
    check(hipDeviceSynchronize(), "synchronize device");
    check(hipMemcpy(result.data(), device_result, sizeof(result), hipMemcpyDeviceToHost), "read output");
    check(hipFree(device_result), "free output");
    check(hipModuleUnload(module), "unload module");

    unsigned invalid = 0;
    unsigned differences = 0;
    unsigned full_wave_pairs = 0;
    for (unsigned lane = 0; lane < result.size(); ++lane) {
        const auto [observed_lane, low, high, exec] = result[lane];
        const auto expected = 0xa5000000u | (lane ^ 1u);
        const auto low_address_tag = 0xa5000000u | ((lane & 31u) ^ 1u);
        const auto high_address_tag = low_address_tag | 32u;
        const bool valid = observed_lane == lane && exec == UINT32_MAX &&
                           low != 0xaaaaaaaau && high != 0xaaaaaaaau;
        invalid += !valid;
        differences += valid && (low != expected || high != expected);
        full_wave_pairs += valid && low == low_address_tag && high == high_address_tag;
        std::printf("lane=%2u id=%08" PRIx32 " low=%08" PRIx32 " bit7=%08" PRIx32
                    " full_exec=%08" PRIx32 " expected=%08" PRIx32 "%s\n",
                    lane, observed_lane, low, high, exec, expected,
                    !valid ? " CONTROL-FAILED" : low != expected || high != expected ? " DIFFERENT" : "");
    }
    std::printf("valid_rows=%zu/%zu differing_pairs=%u full_wave_pairs=%u\n",
                result.size() - invalid, result.size(), differences, full_wave_pairs);
    if (invalid != 0) {
        std::fprintf(stderr, "Lane, full EXEC, or readback controls failed\n");
        return 1;
    }
    if (differences != 0) {
        std::fprintf(stderr, "Observed data differs from the documented same-half result\n");
        return 3;
    }
}
