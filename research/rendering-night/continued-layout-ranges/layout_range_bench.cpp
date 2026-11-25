// SPDX-License-Identifier: GPL-3.0-or-later
#define VK_NO_PROTOTYPES
#include "vulkan_replay.h"

#include <windows.h>

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <string_view>
#include <vector>

namespace {
using namespace leonida;
constexpr auto color = VK_IMAGE_ASPECT_COLOR_BIT;
constexpr auto normal = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
constexpr auto alternate = VK_IMAGE_LAYOUT_GENERAL;
constexpr auto undefined = VK_IMAGE_LAYOUT_UNDEFINED;
constexpr ResourceId id = 1;

enum class Pattern { uniform, mip_stripe, layer_stripe, sparse, checkerboard, mostly_unused };

struct Case {
    const char* name;
    std::uint32_t mips, layers;
    Pattern pattern;
    bool one_cell = false;
};

constexpr std::array cases = {
    Case{"single_image", 1, 1, Pattern::uniform},
    Case{"single_view", 8, 32, Pattern::checkerboard, true},
    Case{"mixed_inline", 2, 1, Pattern::checkerboard},
    Case{"uniform_4x8", 4, 8, Pattern::uniform},
    Case{"uniform_8x32", 8, 32, Pattern::uniform},
    Case{"uniform_10x64", 10, 64, Pattern::uniform},
    Case{"mip_stripe_4x8", 4, 8, Pattern::mip_stripe},
    Case{"mip_stripe_8x32", 8, 32, Pattern::mip_stripe},
    Case{"mip_stripe_10x64", 10, 64, Pattern::mip_stripe},
    Case{"layer_stripe_4x8", 4, 8, Pattern::layer_stripe},
    Case{"layer_stripe_8x32", 8, 32, Pattern::layer_stripe},
    Case{"layer_stripe_10x64", 10, 64, Pattern::layer_stripe},
    Case{"sparse_8x32", 8, 32, Pattern::sparse},
    Case{"sparse_10x64", 10, 64, Pattern::sparse},
    Case{"checkerboard_4x8", 4, 8, Pattern::checkerboard},
    Case{"checkerboard_8x32", 8, 32, Pattern::checkerboard},
    Case{"checkerboard_10x64", 10, 64, Pattern::checkerboard},
    Case{"mostly_unused_8x32", 8, 32, Pattern::mostly_unused},
};

[[noreturn]] void fail(const char* what, const char* name = "") {
    std::fprintf(stderr, "%s %s\n", what, name);
    std::exit(1);
}

unsigned number(std::string_view text) {
    unsigned value;
    const auto end = text.data() + text.size();
    const auto parsed = std::from_chars(text.data(), end, value);
    if (parsed.ec != std::errc{} || parsed.ptr != end) fail("invalid number");
    return value;
}

VkImageLayout layout(const Case& s, std::uint32_t mip, std::uint32_t layer) {
    const bool center = mip == s.mips / 2 && layer == s.layers / 2;
    switch (s.pattern) {
    case Pattern::uniform: return normal;
    case Pattern::mip_stripe: return mip < s.mips / 2 ? normal : alternate;
    case Pattern::layer_stripe: return layer < s.layers / 2 ? normal : alternate;
    case Pattern::sparse: return center ? alternate : normal;
    case Pattern::checkerboard: return (mip + layer) % 2 ? normal : alternate;
    case Pattern::mostly_unused: return center ? normal : undefined;
    }
    fail("unknown layout pattern", s.name);
}

std::uint32_t expected_records(const Case& s, bool patched) {
    if (s.one_cell || s.pattern == Pattern::uniform) return 1;
    if (patched && (s.pattern == Pattern::mip_stripe || s.pattern == Pattern::layer_stripe)) return 2;
    if (patched && s.pattern == Pattern::sparse) return 5;
    return s.mips * s.layers;
}

std::size_t verify(const Case& s, bool patched, const LayoutTracker& tracker, const VkImageSubresourceRange& range) {
    LayoutPieces out;
    if (!tracker.pieces(id, range, out) || out.size() != expected_records(s, patched)) fail("wrong record count", s.name);
    std::vector<bool> visited(s.mips * s.layers);
    for (const auto& piece : out) {
        const auto& r = piece.range;
        if (r.aspectMask != color || !r.levelCount || !r.layerCount ||
            r.baseMipLevel + r.levelCount > s.mips || r.baseArrayLayer + r.layerCount > s.layers)
            fail("invalid record range", s.name);
        for (std::uint32_t layer = r.baseArrayLayer; layer < r.baseArrayLayer + r.layerCount; ++layer) {
            for (std::uint32_t mip = r.baseMipLevel; mip < r.baseMipLevel + r.levelCount; ++mip) {
                const auto index = layer * s.mips + mip;
                if (visited[index] || piece.layout != layout(s, mip, layer)) fail("overlap or wrong old layout", s.name);
                visited[index] = true;
            }
        }
    }
    for (std::uint32_t layer = 0; layer < s.layers; ++layer) {
        for (std::uint32_t mip = 0; mip < s.mips; ++mip) {
            const bool requested = mip >= range.baseMipLevel && mip < range.baseMipLevel + range.levelCount &&
                                   layer >= range.baseArrayLayer && layer < range.baseArrayLayer + range.layerCount;
            if (visited[layer * s.mips + mip] != requested) fail("missing or surplus coverage", s.name);
        }
    }
    return out.size();
}

[[gnu::noinline]] std::uint64_t one_query(const LayoutTracker& tracker, const VkImageSubresourceRange& range) {
    LayoutPieces out;
    if (!tracker.pieces(id, range, out) || out.empty()) fail("query returned no records");
    // Make the whole output observable to the optimizer. The empty assembly adds no CPU instructions.
    asm volatile("" : : "r"(out.begin()), "r"(out.size()) : "memory");
    const auto& last = out[out.size() - 1];
    return out.size() + last.range.levelCount + last.range.layerCount + std::uint32_t(last.layout);
}

void run(const Case& s, bool patched) {
    LayoutTracker tracker;
    ResourceBinding image{};
    image.mip_levels = s.mips;
    image.array_layers = s.layers;
    image.width = image.height = 1u << (s.mips - 1);
    tracker.track(id, image, normal);
    for (std::uint32_t layer = 0; layer < s.layers; ++layer)
        for (std::uint32_t mip = 0; mip < s.mips; ++mip)
            tracker.set(id, {color, mip, 1, layer, 1}, layout(s, mip, layer));
    const VkImageSubresourceRange range = s.one_cell ? VkImageSubresourceRange{color, 3, 1, 7, 1}
                                                    : VkImageSubresourceRange{color, 0, s.mips, 0, s.layers};
    const auto count = verify(s, patched, tracker, range);
    const auto cells = range.layerCount * range.levelCount;
    const auto iterations = std::clamp(2'000'000u / cells, 4096u, 400'000u);
    const std::uint64_t one = one_query(tracker, range);
    std::uint64_t warmup = 0;
    for (unsigned i = 0; i < iterations / 16; ++i) warmup += one_query(tracker, range);
    if (warmup != one * (iterations / 16)) fail("warmup output changed", s.name);
    std::uint64_t sum = 0;
    const auto start = std::chrono::steady_clock::now();
    for (unsigned i = 0; i < iterations; ++i) sum += one_query(tracker, range);
    const auto duration = std::chrono::steady_clock::now() - start;
    if (sum != one * iterations) fail("measured output changed", s.name);
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(duration).count();
    if (ns <= 0) fail("non-positive duration", s.name);
    std::printf("%s,%u,%zu,%u,%lld\n", s.name, cells, count, iterations, static_cast<long long>(ns));
}
}  // namespace

int main(int argc, char** argv) {
    if (argc != 4) fail("usage: layout_range_bench.exe baseline|candidate logical_cpu round");
    const std::string_view arm(argv[1]);
    if (arm != "baseline" && arm != "candidate") fail("unknown arm");
    const auto cpu = number(argv[2]);
    const auto round = number(argv[3]);
    if (cpu >= std::numeric_limits<DWORD_PTR>::digits ||
        !SetThreadAffinityMask(GetCurrentThread(), DWORD_PTR{1} << cpu) || GetCurrentProcessorNumber() != cpu)
        fail("could not pin the benchmark thread to the requested logical CPU");
    std::printf("case,cells,records,iterations,total_ns\n");
    for (unsigned i = 0; i < cases.size(); ++i)
        run(cases[(i + round * 7) % cases.size()], arm == "candidate");
}
