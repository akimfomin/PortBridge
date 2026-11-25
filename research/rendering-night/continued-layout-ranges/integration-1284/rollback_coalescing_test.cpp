// SPDX-License-Identifier: GPL-3.0-or-later
#define VK_NO_PROTOTYPES
#include "vulkan_replay.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <string_view>

static bool count_allocations = false;
static std::size_t allocations = 0;
void* operator new(std::size_t size) {
    if (count_allocations) ++allocations;
    if (auto* p = std::malloc(size ? size : 1)) return p;
    throw std::bad_alloc();
}
void* operator new[](std::size_t size) { return operator new(size); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

namespace {
using namespace leonida;
namespace y = d3d12_sync;
namespace a = d3d12_access;
namespace l = d3d12_layout;
constexpr ResourceId tested = 41, untouched = 42;
constexpr std::uint32_t mips = 6, layers = 8;
constexpr auto color = VK_IMAGE_ASPECT_COLOR_BIT;
constexpr auto shader = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
constexpr auto general = VK_IMAGE_LAYOUT_GENERAL;
constexpr auto unknown = VK_IMAGE_LAYOUT_UNDEFINED;
constexpr auto transfer_dst = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
constexpr auto transfer_src = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
constexpr BarrierSubresourceRange release_area{1, 4, 2, 4, 0, 1};
constexpr BarrierSubresourceRange inner_area{2, 2, 3, 2, 0, 1};
constexpr BarrierSubresourceRange same_area{1, 2, 2, 1, 0, 1};

void require(bool ok, const char* what) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", what);
        std::exit(1);
    }
}

bool contains(const BarrierSubresourceRange& r, std::uint32_t mip, std::uint32_t layer) {
    return mip >= r.index_or_first_mip && mip < r.index_or_first_mip + r.mip_count &&
           layer >= r.first_layer && layer < r.first_layer + r.layer_count;
}

VkImageLayout initial(std::uint32_t mip, std::uint32_t layer) {
    if (mip >= 1 && mip < 3 && layer >= 3 && layer < 5) return unknown;
    return mip < 3 ? shader : general;
}

std::array<VkImageMemoryBarrier2, mips * layers + 4> barriers{};
std::array<std::size_t, 4> call_ends{};
std::size_t records, calls;
VkImage replay_image;

void VKAPI_CALL observe(VkCommandBuffer, const VkDependencyInfo* info) {
    require(!info->memoryBarrierCount && !info->bufferMemoryBarrierCount && info->imageMemoryBarrierCount,
            "one enhanced image dependency per command");
    require(calls < call_ends.size() && records + info->imageMemoryBarrierCount <= barriers.size(),
            "bounded callback trace");
    for (std::uint32_t i = 0; i < info->imageMemoryBarrierCount; ++i)
        barriers[records++] = info->pImageMemoryBarriers[i];
    call_ends[calls++] = records;
}

struct Expected {
    bool present;
    VkImageLayout before, after;
};

template<class ExpectedAt>
void check_call(std::size_t call, std::size_t expected_count, const TextureBarrier& command, ExpectedAt at) {
    const auto first = call ? call_ends[call - 1] : 0;
    const auto last = call_ends[call];
    require(call < calls && last - first == expected_count, "expected barrier records for the call");
    const auto src = vulkan_barrier_scope(command.sync_before, command.access_before);
    const auto dst = vulkan_barrier_scope(command.sync_after, command.access_after);
    std::array<bool, mips * layers> seen{};
    for (std::size_t i = first; i < last; ++i) {
        const auto& b = barriers[i];
        const auto& r = b.subresourceRange;
        require(b.image == replay_image && r.aspectMask == color && b.newLayout != unknown &&
                    b.srcQueueFamilyIndex == VK_QUEUE_FAMILY_IGNORED && b.dstQueueFamilyIndex == VK_QUEUE_FAMILY_IGNORED,
                "correct image, aspect, queue family and valid new layout");
        require(b.srcStageMask == src.stages && b.srcAccessMask == src.access &&
                    b.dstStageMask == dst.stages && b.dstAccessMask == dst.access, "original synchronization scopes");
        require(r.levelCount && r.layerCount && r.baseMipLevel + r.levelCount <= mips &&
                    r.baseArrayLayer + r.layerCount <= layers, "bounded emitted range");
        for (auto layer = r.baseArrayLayer; layer < r.baseArrayLayer + r.layerCount; ++layer) {
            for (auto mip = r.baseMipLevel; mip < r.baseMipLevel + r.levelCount; ++mip) {
                const auto wanted = at(mip, layer);
                const auto index = layer * mips + mip;
                require(wanted.present && !seen[index] && wanted.before == b.oldLayout && wanted.after == b.newLayout,
                        "exact per-cell layout and disjoint coverage");
                seen[index] = true;
            }
        }
    }
    for (std::uint32_t layer = 0; layer < layers; ++layer)
        for (std::uint32_t mip = 0; mip < mips; ++mip)
            require(seen[layer * mips + mip] == at(mip, layer).present, "no missed or surplus cell");
}

const auto released = [](std::uint32_t mip, std::uint32_t layer) {
    const auto was = initial(mip, layer);
    return Expected{contains(release_area, mip, layer) && was != unknown, was, was};
};

void check_state(const LayoutTracker& tracker, bool transitioned) {
    for (std::uint32_t layer = 0; layer < layers; ++layer) {
        for (std::uint32_t mip = 0; mip < mips; ++mip) {
            const auto wanted = !transitioned || !contains(release_area, mip, layer) ? initial(mip, layer) :
                                contains(inner_area, mip, layer) ? transfer_src : transfer_dst;
            const auto index = layer * mips + mip;
            require(tracker.layout(tested, index) == wanted, "tracked layout after transaction");
            require(tracker.layout(untouched, index) == general, "other tracked image left alone");
        }
    }
}

std::size_t replay(const PreparedList& prepared, const ReplayFunctions& vk, LayoutTracker& tracker) {
    calls = records = allocations = 0;
    count_allocations = true;
    emit(prepared, reinterpret_cast<VkCommandBuffer>(std::uintptr_t(0x20)), vk, &tracker);
    count_allocations = false;
    return allocations;
}

int check(bool patched) {
    ResourceBinding image{};
    image.image = replay_image = reinterpret_cast<VkImage>(std::uintptr_t(0x10));
    image.format = VK_FORMAT_R8G8B8A8_UNORM;
    image.width = image.height = 32;
    image.mip_levels = mips;
    image.array_layers = layers;
    const auto resolve = [&](ResourceId id) -> const ResourceBinding* { return id == tested ? &image : nullptr; };
    LayoutTracker tracker;
    tracker.track(tested, image, shader);
    auto other_image = image;
    other_image.image = reinterpret_cast<VkImage>(std::uintptr_t(0x11));
    tracker.track(untouched, other_image, general);
    for (std::uint32_t layer = 0; layer < layers; ++layer)
        for (std::uint32_t mip = 0; mip < mips; ++mip)
            tracker.set(tested, {color, mip, 1, layer, 1}, initial(mip, layer));

    ReplayFunctions vk{};
    vk.pipeline_barrier2 = observe;
    const TextureBarrier release{y::pixel_shading, y::none, a::shader_resource, a::no_access,
                                l::shader_resource, l::undefined, tested, release_area, 0};
    const TextureBarrier discard{y::none, y::copy, a::no_access, a::copy_dest,
                                l::undefined, l::copy_dest, tested, release_area, 0};
    const TextureBarrier transition{y::copy, y::copy, a::copy_dest, a::copy_source,
                                   l::copy_dest, l::copy_source, tested, inner_area, 0};
    const TextureBarrier same{y::pixel_shading, y::pixel_shading, a::shader_resource, a::shader_resource,
                             l::shader_resource, l::shader_resource, tested, same_area, 0};
    CommandList release_list, work_list, same_list;
    require(release_list.barrier(release) && release_list.close(), "record isolated release");
    require(work_list.barrier(release) && work_list.barrier(discard) && work_list.barrier(transition) && work_list.close(),
            "record release, discard and subrange transition in order");
    require(same_list.barrier(same) && same_list.close(), "record same-layout ordering");
    PreparedList r, w, s;
    require(prepare(release_list, resolve, vk, r) == ReplayResult::success &&
                prepare(work_list, resolve, vk, w) == ReplayResult::success &&
                prepare(same_list, resolve, vk, s) == ReplayResult::success, "prepare all command lists");

    const auto release_count = patched ? 3u : 12u;
    const auto direct_allocs = replay(r, vk, tracker);
    check_state(tracker, false);
    tracker.begin();
    require(replay(r, vk, tracker) == direct_allocs, "release adds no allocations for the undo journal");
    require(calls == 1, "release is one synchronization call");
    check_call(0, release_count, release, released);
    check_state(tracker, false);
    require(replay(s, vk, tracker) == 0 && calls == 1, "same-layout barrier orders access without a journal entry");
    check_call(0, 1, same, [](std::uint32_t mip, std::uint32_t layer) {
        return Expected{contains(same_area, mip, layer), shader, shader};
    });
    tracker.rollback();
    check_state(tracker, false);

    for (const bool submitted : {false, true}) {
        tracker.begin();
        replay(w, vk, tracker);
        require(calls == 3, "release, discard and transition remain three ordered calls");
        check_call(0, release_count, release, released);
        check_call(1, 1, discard, [](std::uint32_t mip, std::uint32_t layer) {
            return Expected{contains(release_area, mip, layer), unknown, transfer_dst};
        });
        check_call(2, 1, transition, [](std::uint32_t mip, std::uint32_t layer) {
            return Expected{contains(inner_area, mip, layer), transfer_dst, transfer_src};
        });
        check_state(tracker, true);
        if (submitted) tracker.commit();
        else tracker.rollback();
        check_state(tracker, submitted);
    }

    tracker.begin();
    tracker.set(tested, {color, 2, 2, 3, 2}, general);
    tracker.rollback();
    check_state(tracker, true);
    std::printf("release_records=%u ordered_records=%u release_allocations=%zu same_layout_allocations=0\n",
                release_count, release_count + 2, direct_allocs);
    std::printf("partial coverage, rollback, commit and follow-up rollback: OK\n");
    return 0;
}
}  // namespace

int main(int argc, char** argv) {
    require(argc == 2, "select baseline or candidate");
    const std::string_view mode(argv[1]);
    require(mode == "baseline" || mode == "candidate", "select baseline or candidate");
    return check(mode == "candidate");
}
