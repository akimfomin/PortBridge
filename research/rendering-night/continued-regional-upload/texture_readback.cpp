// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic color image using Continued's pinned XG address and test device.
#include "guard.h"
#include "vulkan_loader.h"
// The local Khronos validation layer predates the optional shader FMA feature.
// This fixture creates no shaders.
#undef VK_KHR_SHADER_FMA_EXTENSION_NAME
#include "vk_test_device.h"
#include "xg_xs_layout.h"

#include <array>
#include <cstdio>
#include <cstring>
#include <string_view>
#include <vector>

namespace {
using namespace std::chrono_literals;
using namespace rt::xg_xs;
constexpr std::uint32_t width = 512, height = 512, texel_bytes = 4;
constexpr std::uint32_t full_bytes = width * height * texel_bytes;
constexpr std::uint32_t partial_bytes = 2 * kTileBytes;
constexpr auto format = VK_FORMAT_R8G8B8A8_UNORM;
constexpr auto old_layout = VK_IMAGE_LAYOUT_GENERAL;
constexpr auto copy_dst = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
constexpr auto copy_src = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
constexpr auto color = VK_IMAGE_ASPECT_COLOR_BIT;
constexpr VkImageSubresourceRange range{color, 0, 1, 0, 1};
constexpr VkImageSubresourceLayers subresource{color, 0, 0, 1};
constexpr std::uint64_t limit = 512 * guard::mib;

struct Inputs {
    std::vector<std::uint8_t> original, expected, full, partial;
    std::array<VkBufferImageCopy, 2> boxes{};
};

std::array<std::uint8_t, 4> pixel(std::uint32_t x, std::uint32_t y) {
    return {std::uint8_t(x * 3 + y), std::uint8_t(y * 5 + (x >> 1)), std::uint8_t(x ^ y), 0xaa};
}

bool update(std::uint32_t x, std::uint32_t y) {
    return (x >= 256 && x < 384 && y >= 128 && y < 256) || (x < 128 && y >= 384);
}

bool inputs(Inputs& out) {
    ResourceDesc desc{};
    desc.dimension = kTexture2D;
    desc.width = width;
    desc.height = height;
    desc.depth_or_array = 1;
    desc.mips = 1;
    desc.format = DXGI_FORMAT_R8G8B8A8_UNORM;
    desc.samples = 1;
    desc.layout = kSwizzled | k64kbD;
    Texture t{};
    if (!build_texture(desc, t) || t.tile_width != 128 || t.tile_height != 128 ||
        t.layout.size != full_bytes || t.array != 1 || t.format.side != 1 ||
        t.format.bytes != texel_bytes || t.layout.planes != 1) return false;
    const auto& mip = t.layout.plane[0].mips[0];
    if (mip.in_tail || mip.offset || mip.padded_width != width || mip.padded_height != height) return false;

    out.original.resize(full_bytes);
    out.expected.resize(full_bytes);
    for (std::uint32_t y = 0; y < height; ++y)
        for (std::uint32_t x = 0; x < width; ++x) {
            const auto p = pixel(x, y);
            const auto at = (y * width + x) * texel_bytes;
            for (std::uint32_t c = 0; c < texel_bytes; ++c) {
                out.original[at + c] = p[c];
                out.expected[at + c] = update(x, y) ? std::uint8_t(p[c] ^ 0x5a) : p[c];
            }
        }

    std::vector<std::uint8_t> before(full_bytes), after(full_bytes);
    std::vector<std::uint64_t> columns;
    copy_elements<true>(t, 0, 0, out.original.data(), before.data(), width * texel_bytes, full_bytes, columns);
    copy_elements<true>(t, 0, 0, out.expected.data(), after.data(), width * texel_bytes, full_bytes, columns);
    out.full.resize(full_bytes);
    copy_elements<false>(t, 0, 0, after.data(), out.full.data(), width * texel_bytes, full_bytes, columns);
    if (out.full != out.expected) return false;

    // Exact byte compare against last uploaded snapshot. Notifications alone do not
    // cover arbitrary writes through persistent Map in the receiving runtime.
    const ElementAddress addresses(t);
    const auto tail = addresses.tail_origin(mip);
    const std::uint32_t tiles_across = width / t.tile_width;
    out.partial.resize(partial_bytes);
    std::uint32_t found{};
    for (std::uint32_t tile = 0; tile < full_bytes / kTileBytes; ++tile) {
        const auto storage = tile * kTileBytes;
        if (!std::memcmp(before.data() + storage, after.data() + storage, kTileBytes)) continue;
        if (found == out.boxes.size()) return false;
        const auto x = (tile % tiles_across) * t.tile_width;
        const auto y = (tile / tiles_across) * t.tile_height;
        if (!update(x, y)) return false;
        auto& box = out.boxes[found];
        box.bufferOffset = found * kTileBytes;
        box.imageSubresource = subresource;
        box.imageOffset = {std::int32_t(x), std::int32_t(y), 0};
        box.imageExtent = {t.tile_width, t.tile_height, 1};
        auto* packed = out.partial.data() + box.bufferOffset;
        for (std::uint32_t row = 0; row < t.tile_height; ++row)
            for (std::uint32_t column = 0; column < t.tile_width; ++column) {
                const auto at = addresses.offset(mip, tail, x + column, y + row, 0);
                if (at < storage || at + texel_bytes > storage + kTileBytes) return false;
                const auto to = (row * t.tile_width + column) * texel_bytes;
                std::memcpy(packed + to, after.data() + at, texel_bytes);
                if (std::memcmp(packed + to, out.expected.data() + ((y + row) * width + x + column) * texel_bytes,
                                texel_bytes)) return false;
            }
        ++found;
    }
    return found == out.boxes.size();
}

struct Report {
    enum Stage { plan, device, allocation, initialization, update_copy, readback, complete };
    Stage stage = plan;
    unsigned validation{};
    std::uint32_t bytes{}, regions{}, mismatch{}, driver{};
    std::uint64_t hash{};
};

void native(const Inputs& in, bool partial, Report& report) {
    vktest::Device device;
    report.stage = Report::device;
    if (device.initialize() != vktest::DeviceStatus::ready || !device.validation) return;
    VkPhysicalDeviceProperties props{};
    device.instance_fn<PFN_vkGetPhysicalDeviceProperties>("vkGetPhysicalDeviceProperties")(device.physical, &props);
    if (std::string_view(props.deviceName) != "NVIDIA GeForce RTX 4070 Ti SUPER" ||
        props.vendorID != 0x10de || props.apiVersion < VK_API_VERSION_1_3) return;
    report.driver = props.driverVersion;

    report.stage = Report::allocation;
    const auto image = device.image(format, width, height, 1, VK_IMAGE_USAGE_SAMPLED_BIT);
    void* upload_map{}, *read_map{};
    const auto upload = device.buffer(full_bytes, VK_BUFFER_USAGE_TRANSFER_SRC_BIT, &upload_map);
    const auto read = device.buffer(full_bytes, VK_BUFFER_USAGE_TRANSFER_DST_BIT, &read_map);
    const auto barrier = device.fn<PFN_vkCmdPipelineBarrier>("vkCmdPipelineBarrier");
    const auto copy_in = device.fn<PFN_vkCmdCopyBufferToImage>("vkCmdCopyBufferToImage");
    const auto copy_out = device.fn<PFN_vkCmdCopyImageToBuffer>("vkCmdCopyImageToBuffer");
    if (!image || !upload || !upload_map || !read || !read_map || !barrier || !copy_in || !copy_out ||
        vktest::validation_error_count()) return;
    constexpr VkBufferImageCopy whole{0, 0, 0, subresource, {0, 0, 0}, {width, height, 1}};
    const auto transition = [&](VkCommandBuffer cmd, VkImageLayout source, VkImageLayout dest,
                                VkPipelineStageFlags src_stage, VkAccessFlags src_access,
                                VkPipelineStageFlags dst_stage, VkAccessFlags dst_access) {
        const VkImageMemoryBarrier image_barrier{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER, nullptr,
            src_access, dst_access, source, dest, VK_QUEUE_FAMILY_IGNORED, VK_QUEUE_FAMILY_IGNORED, image, range};
        barrier(cmd, src_stage, dst_stage, 0, 0, nullptr, 0, nullptr, 1, &image_barrier);
    };
    constexpr auto transfer = VK_PIPELINE_STAGE_TRANSFER_BIT;
    constexpr auto all = VK_PIPELINE_STAGE_ALL_COMMANDS_BIT;
    constexpr auto top = VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT;
    constexpr auto write_access = VK_ACCESS_TRANSFER_WRITE_BIT;
    constexpr auto live_read = VK_ACCESS_SHADER_READ_BIT;
    constexpr auto live_access = VK_ACCESS_MEMORY_READ_BIT | VK_ACCESS_MEMORY_WRITE_BIT;

    report.stage = Report::initialization;
    std::memcpy(upload_map, in.original.data(), full_bytes);
    if (!device.run([&](VkCommandBuffer cmd) {
            transition(cmd, VK_IMAGE_LAYOUT_UNDEFINED, copy_dst, top, 0, transfer, write_access);
            copy_in(cmd, upload, image, copy_dst, 1, &whole);
            transition(cmd, copy_dst, old_layout, transfer, write_access, all, live_read);
            return true;
        }) || vktest::validation_error_count()) return;

    report.stage = Report::update_copy;
    const auto& payload = partial ? in.partial : in.full;
    report.bytes = std::uint32_t(payload.size());
    report.regions = partial ? std::uint32_t(in.boxes.size()) : 1u;
    std::memcpy(upload_map, payload.data(), payload.size());
    if (!device.run([&](VkCommandBuffer cmd) {
            // Whole overwrite can discard the prior copy. Warm partial reads need the real tracked layout.
            transition(cmd, partial ? old_layout : VK_IMAGE_LAYOUT_UNDEFINED, copy_dst,
                       partial ? all : top, partial ? live_access : 0, transfer, write_access);
            copy_in(cmd, upload, image, copy_dst, report.regions, partial ? in.boxes.data() : &whole);
            transition(cmd, copy_dst, old_layout, transfer, write_access, all, live_read);
            transition(cmd, old_layout, copy_src, all, live_access,
                       transfer, VK_ACCESS_TRANSFER_READ_BIT);
            copy_out(cmd, image, copy_src, read, 1, &whole);
            const VkMemoryBarrier to_host{VK_STRUCTURE_TYPE_MEMORY_BARRIER, nullptr, write_access,
                                          VK_ACCESS_HOST_READ_BIT};
            barrier(cmd, transfer, VK_PIPELINE_STAGE_HOST_BIT, 0, 1, &to_host, 0, nullptr, 0, nullptr);
            return true;
        }) || vktest::validation_error_count()) return;

    report.stage = Report::readback;
    const auto* final = static_cast<const std::uint8_t*>(read_map);
    report.hash = 14695981039346656037ull;
    for (std::uint32_t i = 0; i != full_bytes; ++i) {
        report.hash = (report.hash ^ final[i]) * 1099511628211ull;
        if (final[i] != in.expected[i]) ++report.mismatch;
    }
    if (!report.mismatch) report.stage = Report::complete;
}

bool worker(bool partial) {
    if (!guard::worker_limits(limit)) return false;
    guard::Handle parent;
    const auto current = GetCurrentProcess();
    if (!DuplicateHandle(current, GetStdHandle(STD_OUTPUT_HANDLE), current, &parent.value,
                         0, FALSE, DUPLICATE_SAME_ACCESS)) return false;
    // The upstream helper prints setup info through C stdout. Reserve the inherited pipe for the binary report.
    std::FILE* redirected{};
    if (freopen_s(&redirected, "NUL", "w", stdout)) return false;
    Report report{};
    Inputs data;
    if (inputs(data)) native(data, partial, report);
    report.validation = vktest::validation_error_count();
    DWORD written{};
    return WriteFile(parent.value, &report, sizeof(report), &written, nullptr) && written == sizeof(report);
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc != 2) return 2;
    const std::wstring_view mode(argv[1]);
    if (mode == L"--worker-full" || mode == L"--worker-partial")
        return worker(mode == L"--worker-partial") ? 0 : 2;
    if (mode == L"--cpu") {
        Inputs plan;
        if (!inputs(plan)) return 1;
        std::printf("full_bytes=%u partial_bytes=%u regions=%zu\n", full_bytes, partial_bytes, plan.boxes.size());
        return 0;
    }
    if (mode != L"--run-hardware") return 2;
    std::uint64_t baseline_hash{};
    for (bool partial : {false, true}) {
        const auto result = guard::run<Report>(limit, true, 3s, {partial ? L"--worker-partial" : L"--worker-full"});
        const auto& o = result.report;
        std::printf("%s status=%s reaped=%d exit=%lu result_stage=%d validation_errors=%u bytes=%u "
                    "regions=%u mismatch=%u readback_fnv1a64=%016llx driver=%u peak_job_commit=%zu\n",
                    partial ? "partial" : "full", result.status, int(result.reaped), result.exit_code, int(o.stage),
                    o.validation, o.bytes, o.regions, o.mismatch, static_cast<unsigned long long>(o.hash),
                    o.driver, result.job_peak);
        std::fflush(stdout);
        const auto expected_bytes = partial ? partial_bytes : full_bytes;
        if (std::strcmp(result.status, "returned") || !result.reaped || result.exit_code ||
            o.stage != Report::complete || o.validation || o.bytes != expected_bytes ||
            o.regions != (partial ? 2u : 1u) || (partial && baseline_hash != o.hash)) return 1;
        baseline_hash = o.hash;
    }
}
