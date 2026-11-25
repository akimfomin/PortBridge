// SPDX-License-Identifier: MIT
#include <hip/hip_runtime_api.h>

#include <array>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string_view>

struct Row {
    std::uint32_t value;
    std::uint32_t tag;
};
static_assert(sizeof(Row) == 8);

constexpr std::array<std::uint32_t, 17> inputs{
    0x0000ffaf, 0x0000ffef, 0x00007ff7, 0x00008009, 0x0000ffff,
    0x477ff000, 0xc77ff000, 0x501502f9, 0x3f803000, 0x33c00000,
    0x33000001, 0x7f800001, 0x7f802000,
    0x00007c01, 2051, 65535, 0x00012345,
};

constexpr std::array<const char*, inputs.size()> names{
    "a1", "a2", "a3", "a4", "a5",
    "b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8",
    "c1", "c2", "c3", "c4",
};

static void check(hipError_t status, const char* operation) {
    if (status != hipSuccess) {
        std::fprintf(stderr, "%s: %s\n", operation, hipGetErrorString(status));
        std::exit(1);
    }
}

int main(int argc, char** argv) {
    if (argc != 2) {
        std::fprintf(stderr, "Usage: %s d16_probe.hsaco\n", argv[0]);
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

    std::array<Row, inputs.size() + 1> rows{};
    void* input = nullptr;
    void* output = nullptr;
    check(hipMalloc(&input, sizeof(inputs)), "allocate inputs");
    // V# holds a 48-bit byte address. Reject rather than truncating a pointer.
    constexpr std::uint64_t descriptor_limit = std::uint64_t{1} << 48;
    const auto address = reinterpret_cast<std::uintptr_t>(input);
    if (address > descriptor_limit - sizeof(inputs)) {
        std::fprintf(stderr, "The complete input range does not fit in a 48-bit V# pointer\n");
        check(hipFree(input), "free inputs");
        return 2;
    }
    check(hipMemcpy(input, inputs.data(), sizeof(inputs), hipMemcpyHostToDevice), "upload inputs");
    check(hipMalloc(&output, sizeof(rows)), "allocate output");
    check(hipMemset(output, 0, sizeof(rows)), "initialize output");

    hipModule_t module{};
    hipFunction_t kernel{};
    check(hipModuleLoad(&module, argv[1]), "load code object");
    check(hipModuleGetFunction(&kernel, module, "d16_probe"), "get d16_probe");
    void* arguments[]{&input, &output};
    check(hipModuleLaunchKernel(kernel, 1, 1, 1, 32, 1, 1, 0, nullptr, arguments, nullptr),
          "launch one wave");
    check(hipDeviceSynchronize(), "synchronize device");
    check(hipMemcpy(rows.data(), output, sizeof(rows), hipMemcpyDeviceToHost), "read output");
    check(hipModuleUnload(module), "unload code object");
    check(hipFree(output), "free output");
    check(hipFree(input), "free inputs");

    for (std::size_t i = 0; i < rows.size(); ++i) {
        if (rows[i].tag != 0x44313600u + i) {
            std::fprintf(stderr, "Missing or misplaced result row: %zu\n", i);
            return 1;
        }
    }
    if (rows[0].value != UINT32_MAX) {
        std::fprintf(stderr, "Expected full initial EXEC for one Wave32 group\n");
        return 1;
    }
    // A5 has an agreed low-half conversion. Keep unexpected upper halves in
    // the report, which specifically measures what happened to those bits.
    if ((rows[5].value & 0xffffu) != 0x3c00u) {
        std::fprintf(stderr, "A5 control failed: %08" PRIx32 "\n", rows[5].value);
        return 1;
    }

    std::printf("device=%s arch=%s warp=%d HIP-runtime=%d HIP-driver=%d\n",
                properties.name, properties.gcnArchName, properties.warpSize, runtime, driver);
    std::printf("initial_exec=%08" PRIx32, rows[0].value);
    for (std::size_t i = 0; i < names.size(); ++i) {
        std::printf(" %s=%08" PRIx32, names[i], rows[i + 1].value);
    }
    std::printf("\n");
}
