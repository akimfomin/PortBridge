// SPDX-License-Identifier: MIT
#pragma once

#include <cstdint>
#include <span>
#include <vector>

namespace transfer {

struct Range {
    std::uint32_t begin;
    std::uint32_t end;
    bool operator==(const Range&) const = default;
};

struct Cost {
    std::uint64_t setup;
    std::uint64_t unit;
};

struct Problem {
    std::uint32_t extent;
    std::uint32_t max_units;
    Cost cost;
    std::span<const std::uint32_t> dirty;
    std::span<const Range> islands;
};

enum class Strategy { exact, greedy, optimal };

// Units are caller-chosen aligned atoms. Dirty indices are sorted and unique.
// Each half-open island authorizes one stable source/destination mapping.
// Adjacent islands remain separate. Every dirty atom must be inside an island.
// The caller owns synchronization, alias checks, and the snapshot lifetime.
// Optimal minimizes (modeled cost, copied units, region count) in that order.
std::vector<Range> plan(const Problem& problem, Strategy strategy = Strategy::optimal);
std::uint64_t score(std::span<const Range> ranges, Cost cost);

}  // namespace transfer
