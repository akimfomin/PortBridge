// SPDX-License-Identifier: GPL-3.0-or-later
#define VK_NO_PROTOTYPES
#include "vulkan_replay.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <map>
#include <random>
#include <string_view>
#include <tuple>
#include <vector>

namespace {
using namespace leonida;
constexpr auto color = VK_IMAGE_ASPECT_COLOR_BIT;
constexpr auto depth = VK_IMAGE_ASPECT_DEPTH_BIT;
constexpr auto stencil = VK_IMAGE_ASPECT_STENCIL_BIT;
constexpr auto both = depth | stencil;
constexpr auto general = VK_IMAGE_LAYOUT_GENERAL;
constexpr auto shader = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
constexpr auto target = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
constexpr auto uninit = VK_IMAGE_LAYOUT_UNDEFINED;
constexpr auto copy_dst = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
constexpr auto copy_src = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
constexpr ResourceId id = 1;
std::uint32_t mips = 8, layers = 32;

void require(bool condition, const char* label) {
    if (!condition) {
        std::fprintf(stderr, "FAIL %s\n", label);
        std::exit(1);
    }
}

using Cell = std::tuple<VkImageAspectFlagBits, uint32_t, uint32_t>;

template <typename Apply>
void expand(const VkImageSubresourceRange& r, Apply apply) {
    const auto mip_end = r.levelCount == VK_REMAINING_MIP_LEVELS ? mips : r.baseMipLevel + r.levelCount;
    const auto layer_end = r.layerCount == VK_REMAINING_ARRAY_LAYERS ? layers : r.baseArrayLayer + r.layerCount;
    require(mip_end <= mips && layer_end <= layers, "range stays inside image");
    for (const auto a : {color, depth, stencil}) {
        if (!(r.aspectMask & a)) continue;
        for (auto layer = r.baseArrayLayer; layer < layer_end; ++layer)
            for (auto mip = r.baseMipLevel; mip < mip_end; ++mip)
                apply(Cell(a, mip, layer));
    }
}

std::size_t equivalent_partition(const LayoutTracker& tracker, const VkImageSubresourceRange& query) {
    std::map<Cell, VkImageLayout> actual;
    LayoutPieces out;
    require(tracker.pieces(id, query, out), "tracked image returned a partition");
    for (const auto& piece : out)
        expand(piece.range, [&](const Cell& c) {
            require(actual.emplace(c, piece.layout).second, "pieces do not overlap");
        });
    std::map<Cell, VkImageLayout> expected;
    expand(query, [&](const Cell& c) {
        const auto [aspect, mip, layer] = c;
        const auto plane_offset = aspect == stencil ? mips * layers : 0;
        expected.emplace(c, tracker.layout(id, plane_offset + layer * mips + mip));
    });
    require(expected == actual, "exact queried aspect, layer, mip and actual backend layout");
    return out.size();
}

ResourceBinding texture(VkImageAspectFlags aspects = color) {
    ResourceBinding image{};
    image.image = reinterpret_cast<VkImage>(std::uintptr_t(0x10));
    image.format = aspects == color ? VK_FORMAT_R8G8B8A8_UNORM : VK_FORMAT_D24_UNORM_S8_UINT;
    image.width = image.height = 128;
    image.mip_levels = mips;
    image.array_layers = layers;
    image.aspects = aspects;
    return image;
}

void report_count(const char* label, std::size_t actual, std::size_t expected) {
    std::printf("%s=%zu\n", label, actual);
    require(actual == expected, label);
}

void partition_cases(bool patched) {
    LayoutTracker rgba;
    rgba.track(id, texture(), shader);
    const VkImageSubresourceRange all{color, 0, mips, 0, layers};
    rgba.set(id, {color, 4, 4, 0, layers}, general);
    report_count("striped_pieces", equivalent_partition(rgba, all), patched ? 2 : mips * layers);
    const VkImageSubresourceRange tail{color, 2, VK_REMAINING_MIP_LEVELS, 3, VK_REMAINING_ARRAY_LAYERS};
    report_count("partial_tail_pieces", equivalent_partition(rgba, tail), patched ? 2 : 6 * 29);
    for (uint32_t layer = 0; layer < layers; ++layer)
        for (uint32_t mip = 0; mip < mips; ++mip)
            rgba.set(id, {color, mip, 1, layer, 1}, (mip + layer) % 2 ? shader : general);
    report_count("checkerboard_pieces", equivalent_partition(rgba, all), mips * layers);

    std::mt19937 rng(0x1026);
    constexpr auto states = std::array{shader, general, target, uninit, copy_src};
    for (unsigned sample = 0; sample < 96; ++sample) {
        for (uint32_t layer = 0; layer < layers; ++layer)
            for (uint32_t mip = 0; mip < mips; ++mip)
                rgba.set(id, {color, mip, 1, layer, 1}, states[rng() % states.size()]);
        const std::uint32_t from_mip = rng() % mips, from_layer = rng() % layers;
        const std::uint32_t size_mip = 1 + rng() % (mips - from_mip);
        const std::uint32_t size_layer = 1 + rng() % (layers - from_layer);
        equivalent_partition(rgba, {color, from_mip, size_mip, from_layer, size_layer});
    }
    std::printf("deterministic_partial_queries=96\n");

    mips = 4;
    layers = 8;
    LayoutTracker separate(true);
    const auto ds = texture(both);
    separate.track(id, ds, VK_IMAGE_LAYOUT_DEPTH_READ_ONLY_OPTIMAL);
    separate.set(id, {stencil, 0, mips, 0, layers}, VK_IMAGE_LAYOUT_STENCIL_ATTACHMENT_OPTIMAL);
    report_count("separate_ds_pieces", equivalent_partition(separate, {both, 0, mips, 0, layers}),
                 patched ? 2 : 2 * mips * layers);
    report_count("stencil_only_pieces", equivalent_partition(separate, {stencil, 0, mips, 0, layers}), 1);
    LayoutPieces out;
    VkImageSubresourceRange rejected{};
    require(!barrier_range(ds, {0, 1, 0, 1, 2, 1}, rejected),
            "irrelevant aspect plane is rejected before replay");
    require(separate.pieces(id, {color, 0, 1, 0, 1}, out) && out.size() == 1 && out[0].layout == uninit,
            "unvisited aspect keeps existing internal fallback");

    LayoutTracker coupled(false);
    coupled.track(id, ds, VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL);
    const auto stencil_only = VkImageSubresourceRange{stencil, 2, 2, 0, layers};
    const auto effective = detail::planes_for_layout(ds, stencil_only, false);
    require(effective.aspectMask == both, "nonseparate backend transitions the coupled planes together");
    coupled.set(id, effective, VK_IMAGE_LAYOUT_DEPTH_STENCIL_READ_ONLY_OPTIMAL);
    report_count("coupled_ds_pieces", equivalent_partition(coupled, {both, 0, mips, 0, layers}),
                 patched ? 2 : mips * layers);
}

using Event = std::tuple<char, VkImageLayout, VkImageLayout>;
std::map<Cell, std::vector<Event>> timeline;
std::size_t legacy_count = 0, enhanced_count = 0, enhanced_calls = 0;

void add(const VkImageSubresourceRange& r, Event event) {
    expand(r, [&](Cell key) { timeline[key].push_back(event); });
}

void VKAPI_CALL legacy(VkCommandBuffer, VkPipelineStageFlags, VkPipelineStageFlags, VkDependencyFlags,
                       uint32_t, const VkMemoryBarrier*, uint32_t, const VkBufferMemoryBarrier*,
                       uint32_t count, const VkImageMemoryBarrier* barriers) {
    legacy_count += count;
    for (uint32_t i = 0; i < count; ++i)
        add(barriers[i].subresourceRange, {'b', barriers[i].oldLayout, barriers[i].newLayout});
}

void VKAPI_CALL enhanced(VkCommandBuffer, const VkDependencyInfo* info) {
    ++enhanced_calls;
    enhanced_count += info->imageMemoryBarrierCount;
    for (uint32_t i = 0; i < info->imageMemoryBarrierCount; ++i) {
        const auto& b = info->pImageMemoryBarriers[i];
        require(b.srcQueueFamilyIndex == VK_QUEUE_FAMILY_IGNORED && b.dstQueueFamilyIndex == VK_QUEUE_FAMILY_IGNORED,
                "unchanged queue family scope");
        require(b.srcStageMask && b.dstStageMask && b.srcAccessMask && b.dstAccessMask, "preserved scopes");
        add(b.subresourceRange, {'e', b.oldLayout, b.newLayout});
    }
}

void VKAPI_CALL clear_color(VkCommandBuffer, VkImage, VkImageLayout layout, const VkClearColorValue*,
                            uint32_t count, const VkImageSubresourceRange* ranges) {
    for (uint32_t i = 0; i < count; ++i) add(ranges[i], {'c', layout, layout});
}

void replay_case(bool patched) {
    mips = 8;
    layers = 32;
    LayoutTracker tracker;
    const auto image = texture();
    tracker.track(id, image, shader);
    tracker.set(id, {color, 4, 4, 0, layers}, general);
    tracker.set(id, {color, 2, 2, 7, 4}, uninit);
    ReplayFunctions vk{};
    vk.pipeline_barrier = legacy;
    vk.pipeline_barrier2 = enhanced;
    vk.clear_color_image = clear_color;
    const auto resolve = [&](ResourceId r) -> const ResourceBinding* { return r == id ? &image : nullptr; };
    namespace s = d3d12_sync;
    namespace a = d3d12_access;
    namespace l = d3d12_layout;
    const BarrierSubresourceRange subrange{1, 6, 4, 16, 0, 1};
    CommandList list;
    require(list.barrier(TextureBarrier{s::pixel_shading, s::copy, a::shader_resource, a::copy_dest,
                                        l::shader_resource, l::copy_dest, id, subrange, 0}),
            "record first enhanced transition");
    require(list.barrier(TextureBarrier{s::copy, s::copy, a::copy_dest, a::copy_source,
                                        l::copy_dest, l::copy_source, id, subrange, 0}),
            "record second enhanced transition");
    require(list.close(), "close replay list");
    PreparedList prepared;
    require(prepare(list, resolve, vk, prepared) == ReplayResult::success, "prepare real replay path");
    const auto cb = reinterpret_cast<VkCommandBuffer>(std::uintptr_t(0x20));
    emit(prepared, cb, vk, &tracker);
    require(enhanced_calls == 2, "the two enhanced commands remain independent and ordered");
    require(legacy_count == 16, "first-use initialization kept its two transitions for each of eight cells");
    const auto area = VkImageSubresourceRange{color, 1, 6, 4, 16};
    expand(area, [&](const Cell& c) {
        const auto [aspect, mip, layer] = c;
        const bool new_cell = mip >= 2 && mip < 4 && layer >= 7 && layer < 11;
        const auto original = mip >= 4 ? general : shader;
        std::vector<Event> expected;
        if (new_cell)
            expected = {{'b', uninit, copy_dst}, {'c', copy_dst, copy_dst}, {'b', copy_dst, shader}};
        expected.push_back({'e', original, copy_dst});
        expected.push_back({'e', copy_dst, copy_src});
        require(timeline.at(c) == expected, "preserved clear-before-use and per-subresource barrier order");
        require(tracker.layout(id, layer * mips + mip) == copy_src, "final backend layout");
    });
    require(timeline.size() == 96, "no barriers on cells outside the requested range");
    require(tracker.layout(id, 4 * mips) == shader && tracker.layout(id, 4 * mips + 7) == general,
            "outside tracked cells retain their layouts");
    report_count("ordered_replay_image_barriers", enhanced_count, patched ? 13 : 97);
    std::printf("ordered_replay_cells=96\n");
}
}  // namespace

int main(int argc, char** argv) {
    const bool patched = argc == 2 && std::string_view(argv[1]) == "candidate";
    require(patched || (argc == 2 && std::string_view(argv[1]) == "baseline"), "select baseline or candidate");
    partition_cases(patched);
    replay_case(patched);
}
