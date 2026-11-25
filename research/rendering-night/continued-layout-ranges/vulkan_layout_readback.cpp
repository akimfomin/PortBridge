// SPDX-License-Identifier: GPL-3.0-or-later
// Device setup and image ownership follow Continued's vk_bc_zero_init_test.cpp.
#include "vulkan_loader.h"
// This fixture creates no shaders. The installed 1.3.285 validator predates
// the optional FMA feature enabled by the general GPU-test helper.
#undef VK_KHR_SHADER_FMA_EXTENSION_NAME
#include "vk_test_device.h"
#include "vulkan_replay.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <string_view>
#include <vector>

namespace {
using namespace leonida;
constexpr std::uint32_t width = 128, mip_count = 8, layer_count = 32;
constexpr auto color = VK_IMAGE_ASPECT_COLOR_BIT;
constexpr auto format = VK_FORMAT_R8G8B8A8_UINT;
constexpr auto shader = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
constexpr auto general = VK_IMAGE_LAYOUT_GENERAL;
constexpr auto copy_dst = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
constexpr auto copy_src = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
constexpr ResourceId image_id = 1;

using Pixel = std::array<std::uint8_t, 4>;
constexpr Pixel overwrite{0xA1, 0xB2, 0xC3, 0xD4};

bool selected(std::uint32_t mip, std::uint32_t layer) {
    return mip >= 1 && mip < 7 && layer >= 4 && layer < 20;
}

bool unused(std::uint32_t mip, std::uint32_t layer) {
    return mip >= 2 && mip < 4 && layer >= 7 && layer < 11;
}

Pixel sentinel(std::uint32_t mip, std::uint32_t layer) {
    return {std::uint8_t(0x11 + mip), std::uint8_t(0x30 + layer), 0x7F, std::uint8_t(0xF0 + ((mip + layer) % 16))};
}

struct Image {
    vktest::Device& device;
    VkImage image = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;

    ~Image() {
        if (image) device.fn<PFN_vkDestroyImage>("vkDestroyImage")(device.device, image, nullptr);
        if (memory) device.fn<PFN_vkFreeMemory>("vkFreeMemory")(device.device, memory, nullptr);
    }

    bool create() {
        VkImageCreateInfo info{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
        info.imageType = VK_IMAGE_TYPE_2D;
        info.format = format;
        info.extent = {width, width, 1};
        info.mipLevels = mip_count;
        info.arrayLayers = layer_count;
        info.samples = VK_SAMPLE_COUNT_1_BIT;
        info.tiling = VK_IMAGE_TILING_OPTIMAL;
        info.usage = VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT;
        if (device.fn<PFN_vkCreateImage>("vkCreateImage")(device.device, &info, nullptr, &image) != VK_SUCCESS)
            return false;
        VkMemoryRequirements req{};
        device.fn<PFN_vkGetImageMemoryRequirements>("vkGetImageMemoryRequirements")(device.device, image, &req);
        if (req.size > 16 * 1024 * 1024) return false;
        VkPhysicalDeviceMemoryProperties properties{};
        device.instance_fn<PFN_vkGetPhysicalDeviceMemoryProperties>("vkGetPhysicalDeviceMemoryProperties")(
            device.physical, &properties);
        for (std::uint32_t i = 0; i < properties.memoryTypeCount; ++i) {
            if (!(req.memoryTypeBits & (1u << i)) ||
                !(properties.memoryTypes[i].propertyFlags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)) continue;
            VkMemoryAllocateInfo allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
            allocation.allocationSize = req.size;
            allocation.memoryTypeIndex = i;
            if (device.fn<PFN_vkAllocateMemory>("vkAllocateMemory")(
                    device.device, &allocation, nullptr, &memory) != VK_SUCCESS) return false;
            return device.fn<PFN_vkBindImageMemory>("vkBindImageMemory")(device.device, image, memory, 0) == VK_SUCCESS;
        }
        return false;
    }
};

struct Native {
    PFN_vkCmdPipelineBarrier2 barrier2;
    PFN_vkCmdPipelineBarrier legacy;
    PFN_vkCmdClearColorImage clear;
    PFN_vkCmdCopyImageToBuffer read;
    VkImage image;
    unsigned calls = 0, image_records = 0, legacy_transitions = 0, first_use_clears = 0;

    VkImageMemoryBarrier2 transition(std::uint32_t mip, std::uint32_t layer, VkImageLayout before,
                                     VkImageLayout after, VkPipelineStageFlags2 src, VkAccessFlags2 src_access,
                                     VkPipelineStageFlags2 dst, VkAccessFlags2 dst_access) const {
        VkImageMemoryBarrier2 b{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2};
        b.srcStageMask = src;
        b.srcAccessMask = src_access;
        b.dstStageMask = dst;
        b.dstAccessMask = dst_access;
        b.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        b.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        b.oldLayout = before;
        b.newLayout = after;
        b.image = image;
        b.subresourceRange = {color, mip, 1, layer, 1};
        return b;
    }

    void transitions(VkCommandBuffer cb, const std::vector<VkImageMemoryBarrier2>& barriers) const {
        VkDependencyInfo dep{VK_STRUCTURE_TYPE_DEPENDENCY_INFO};
        dep.imageMemoryBarrierCount = std::uint32_t(barriers.size());
        dep.pImageMemoryBarriers = barriers.data();
        barrier2(cb, &dep);
    }

    void set_pixel(VkCommandBuffer cb, std::uint32_t mip, std::uint32_t layer, Pixel v) const {
        const VkImageSubresourceRange range{color, mip, 1, layer, 1};
        VkClearColorValue value{};
        for (unsigned i = 0; i < v.size(); ++i) value.uint32[i] = v[i];
        clear(cb, image, copy_dst, &value, 1, &range);
    }
};

Native* active = nullptr;

void VKAPI_CALL replay_enhanced(VkCommandBuffer cb, const VkDependencyInfo* dep) {
    ++active->calls;
    active->image_records += dep->imageMemoryBarrierCount;
    active->barrier2(cb, dep);
    // One update between the two transitions checks copy-write visibility through the second transition.
    if (active->calls == 1) active->set_pixel(cb, 6, 18, overwrite);
}

void VKAPI_CALL replay_legacy(VkCommandBuffer cb, VkPipelineStageFlags src, VkPipelineStageFlags dst,
                              VkDependencyFlags flags, uint32_t memories, const VkMemoryBarrier* memory,
                              uint32_t buffers, const VkBufferMemoryBarrier* buffer,
                              uint32_t images, const VkImageMemoryBarrier* image) {
    active->legacy_transitions += images;
    active->legacy(cb, src, dst, flags, memories, memory, buffers, buffer, images, image);
}

void VKAPI_CALL replay_clear(VkCommandBuffer cb, VkImage image, VkImageLayout layout, const VkClearColorValue* value,
                             uint32_t count, const VkImageSubresourceRange* ranges) {
    active->first_use_clears += count;
    active->clear(cb, image, layout, value, count, ranges);
}

int check(vktest::Device& d, unsigned expected) {
    Image image{d};
    if (!image.create()) return 1;
    // Require the native Vulkan 1.3 entry point. There is no downconversion to a legacy barrier here.
    Native native{reinterpret_cast<PFN_vkCmdPipelineBarrier2>(d.device_proc(d.device, "vkCmdPipelineBarrier2")),
                  d.fn<PFN_vkCmdPipelineBarrier>("vkCmdPipelineBarrier"),
                  d.fn<PFN_vkCmdClearColorImage>("vkCmdClearColorImage"),
                  d.fn<PFN_vkCmdCopyImageToBuffer>("vkCmdCopyImageToBuffer"), image.image};
    if (!native.barrier2 || !native.legacy || !native.clear || !native.read) return 1;

    ResourceBinding binding{};
    binding.image = image.image;
    binding.format = format;
    binding.width = binding.height = width;
    binding.mip_levels = mip_count;
    binding.array_layers = layer_count;
    LayoutTracker tracker;
    tracker.track(image_id, binding, shader);
    tracker.set(image_id, {color, 4, 4, 0, layer_count}, general);
    tracker.set(image_id, {color, 2, 2, 7, 4}, VK_IMAGE_LAYOUT_UNDEFINED);

    namespace s = d3d12_sync;
    namespace a = d3d12_access;
    namespace l = d3d12_layout;
    const BarrierSubresourceRange range{1, 6, 4, 16, 0, 1};
    const auto resolve = [&](ResourceId id) -> const ResourceBinding* { return id == image_id ? &binding : nullptr; };
    CommandList list;
    if (!list.barrier(TextureBarrier{s::pixel_shading, s::copy, a::shader_resource, a::copy_dest,
                                    l::shader_resource, l::copy_dest, image_id, range, 0}) ||
        !list.barrier(TextureBarrier{s::copy, s::copy, a::copy_dest, a::copy_source,
                                    l::copy_dest, l::copy_source, image_id, range, 0}) || !list.close()) return 1;
    ReplayFunctions vk{};
    vk.pipeline_barrier2 = replay_enhanced;
    vk.pipeline_barrier = replay_legacy;
    vk.clear_color_image = replay_clear;
    PreparedList prepared;
    if (prepare(list, resolve, vk, prepared) != ReplayResult::success) return 1;

    std::vector<VkImageMemoryBarrier2> to_initial_copy, to_old_layouts, to_copy_outside;
    std::vector<VkBufferImageCopy> selected_copy, outside_copy;
    VkDeviceSize size = 0;
    constexpr auto all = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT;
    constexpr auto clear_stage = VK_PIPELINE_STAGE_2_CLEAR_BIT;
    constexpr auto copy_stage = VK_PIPELINE_STAGE_2_COPY_BIT;
    constexpr auto write = VK_ACCESS_2_TRANSFER_WRITE_BIT;
    constexpr auto read = VK_ACCESS_2_TRANSFER_READ_BIT;
    constexpr auto memory = VK_ACCESS_2_MEMORY_READ_BIT | VK_ACCESS_2_MEMORY_WRITE_BIT;
    for (std::uint32_t layer = 0; layer < layer_count; ++layer) {
        for (std::uint32_t mip = 0; mip < mip_count; ++mip) {
            const auto old = mip < 4 ? shader : general;
            if (!unused(mip, layer)) {
                to_initial_copy.push_back(native.transition(mip, layer, VK_IMAGE_LAYOUT_UNDEFINED, copy_dst,
                                                             0, 0, clear_stage, write));
                to_old_layouts.push_back(native.transition(mip, layer, copy_dst, old, clear_stage, write, all, memory));
            }
            VkBufferImageCopy region{};
            region.bufferOffset = size;
            region.imageSubresource = {color, mip, layer, 1};
            const auto extent = width >> mip;
            region.imageExtent = {extent, extent, 1};
            size += VkDeviceSize(extent) * extent * sizeof(Pixel);
            if (selected(mip, layer)) selected_copy.push_back(region);
            else {
                outside_copy.push_back(region);
                to_copy_outside.push_back(native.transition(mip, layer, old, copy_src, all, memory, copy_stage, read));
            }
        }
    }
    void* map = nullptr;
    const auto dst = d.buffer(size, VK_BUFFER_USAGE_TRANSFER_DST_BIT, &map);
    if (!dst || !map || size != 2'796'160) return 1;

    const bool submitted = d.run([&](VkCommandBuffer cb) {
        native.transitions(cb, to_initial_copy);
        for (const auto& b : to_initial_copy) {
            const auto mip = b.subresourceRange.baseMipLevel, layer = b.subresourceRange.baseArrayLayer;
            native.set_pixel(cb, mip, layer, sentinel(mip, layer));
        }
        native.transitions(cb, to_old_layouts);
        active = &native;
        emit(prepared, cb, vk, &tracker);
        active = nullptr;
        // Read selected cells before adding any harness barriers for the unselected cells.
        native.read(cb, image.image, copy_src, dst, std::uint32_t(selected_copy.size()), selected_copy.data());
        native.transitions(cb, to_copy_outside);
        native.read(cb, image.image, copy_src, dst, std::uint32_t(outside_copy.size()), outside_copy.data());
        VkMemoryBarrier2 host{VK_STRUCTURE_TYPE_MEMORY_BARRIER_2};
        host.srcStageMask = copy_stage;
        host.srcAccessMask = write;
        host.dstStageMask = VK_PIPELINE_STAGE_2_HOST_BIT;
        host.dstAccessMask = VK_ACCESS_2_HOST_READ_BIT;
        VkDependencyInfo dep{VK_STRUCTURE_TYPE_DEPENDENCY_INFO};
        dep.memoryBarrierCount = 1;
        dep.pMemoryBarriers = &host;
        native.barrier2(cb, &dep);
        return true;
    });
    if (!submitted) return 1;

    unsigned texels = 0;
    std::uint64_t hash = 14695981039346656037ull;
    for (const auto* regions : {&selected_copy, &outside_copy}) {
        for (const auto& r : *regions) {
            const auto mip = r.imageSubresource.mipLevel, layer = r.imageSubresource.baseArrayLayer;
            auto want = unused(mip, layer) ? Pixel{} : sentinel(mip, layer);
            if (mip == 6 && layer == 18) want = overwrite;
            const auto* bytes = static_cast<const std::uint8_t*>(map) + r.bufferOffset;
            for (unsigned i = 0; i < r.imageExtent.width * r.imageExtent.height; ++i) {
                const auto* pixel = bytes + i * sizeof(Pixel);
                if (!std::equal(want.begin(), want.end(), pixel)) {
                    std::fprintf(stderr, "mismatch at mip=%u layer=%u texel=%u\n", mip, layer, i);
                    return 1;
                }
                for (unsigned component = 0; component < want.size(); ++component)
                    hash = (hash ^ pixel[component]) * 1099511628211ull;
                ++texels;
            }
        }
    }
    std::printf("texels=%u readback_fnv1a64=%016llx enhanced_calls=%u image_barriers=%u legacy=%u zero_clears=%u\n",
                texels, static_cast<unsigned long long>(hash), native.calls, native.image_records,
                native.legacy_transitions, native.first_use_clears);
    return texels == 699'040 && native.calls == 2 && native.image_records == expected &&
                   native.legacy_transitions == 16 && native.first_use_clears == 8 ? 0 : 1;
}
}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const std::string_view mode(argv[1]);
    if (mode != "baseline" && mode != "candidate") return 2;
    int result;
    {
        vktest::Device d;
        if (d.initialize() != vktest::DeviceStatus::ready || !d.validation) return 77;
        result = check(d, mode == "baseline" ? 97 : 13);
    }
    const auto errors = vktest::validation_error_count();
    std::printf("validation_errors=%u\n", errors);
    return errors ? 1 : result;
}
