// SPDX-License-Identifier: MIT
#include "planner.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <random>
#include <stdexcept>
#include <vector>

namespace {
using transfer::Cost;
using transfer::Problem;
using transfer::Range;
using transfer::Strategy;

constexpr std::uint32_t extent = 8192;
constexpr std::uint32_t atom_bytes = 64;
constexpr std::uint32_t epochs = 1024;
constexpr std::uint32_t seed = 27731071;
constexpr std::array caps{64u, extent};
constexpr std::array models{Cost{8, 1}, Cost{16, 1}, Cost{2, 1}};
constexpr std::array model_names{"warp-synthetic", "warp-sensitivity", "cpu-like"};
constexpr std::array family_names{"dense", "strided", "uniform-scatter", "local-burst"};

struct Trace {
    std::vector<std::uint32_t> dirty;
    std::vector<Range> islands;
};

Trace epoch(std::size_t family, bool guarded, std::mt19937& rng) {
    const auto draw = [&](std::uint32_t limit) { return std::uint32_t(rng() % limit); };
    std::vector<bool> marks(extent);
    if (family == 0 || family == 2) {
        const auto density_per_thousand = family == 0 ? 550 + draw(400) : 6 + draw(90);
        for (std::uint32_t index = 0; index < extent; ++index) {
            marks[index] = draw(1000) < density_per_thousand;
        }
    } else if (family == 1) {
        const auto stride = 3 + draw(55);
        const auto width = 1 + draw(std::min(stride, 5u));
        for (auto begin = draw(stride); begin < extent; begin += stride) {
            for (auto index = begin; index < std::min(extent, begin + width); ++index) {
                marks[index] = true;
            }
        }
    } else {
        for (std::uint32_t begin = 0; begin < extent; begin += 128 + draw(320)) {
            const auto end = std::min(extent, begin + 64 + draw(128));
            const auto density_per_thousand = 350 + draw(500);
            for (auto index = begin; index < end; ++index) {
                if (draw(1000) < density_per_thousand) {
                    marks[index] = true;
                }
            }
        }
    }
    Trace result;
    for (std::uint32_t begin = 0; begin < extent;) {
        const auto end = guarded ? std::min(extent, begin + 192 + draw(448)) : extent;
        result.islands.push_back({begin, end});
        for (auto index = begin; index < end; ++index) {
            if (marks[index]) {
                result.dirty.push_back(index);
            }
        }
        begin = end + 1 + draw(32);
    }
    return result;
}

std::uint64_t bytes(const std::vector<Range>& ranges) {
    std::uint64_t total = 0;
    for (const auto range : ranges) {
        total += std::uint64_t(range.end - range.begin) * atom_bytes;
    }
    return total;
}

struct Stats {
    std::uint32_t gains = 0;
    std::uint32_t gains_over_1_percent = 0;
    std::uint64_t greedy_cost = 0;
    std::uint64_t optimal_cost = 0;
    std::uint64_t greedy_bytes = 0;
    std::uint64_t optimal_bytes = 0;
    std::uint64_t greedy_regions = 0;
    std::uint64_t optimal_regions = 0;
    std::vector<std::uint32_t> savings_bps;

    void compare(const Problem& problem) {
        const auto greedy = transfer::plan(problem, Strategy::greedy);
        const auto optimal = transfer::plan(problem, Strategy::optimal);
        const auto g_cost = transfer::score(greedy, problem.cost);
        const auto o_cost = transfer::score(optimal, problem.cost);
        const auto g_bytes = bytes(greedy);
        const auto o_bytes = bytes(optimal);
        if (o_cost > g_cost || (o_cost == g_cost && o_bytes > g_bytes)
            || (o_cost == g_cost && o_bytes == g_bytes && optimal.size() > greedy.size())) {
            throw std::runtime_error("optimal objective lost to same-cap greedy");
        }
        const auto gain = g_cost - o_cost;
        gains += gain != 0;
        gains_over_1_percent += gain * 100 > g_cost;
        savings_bps.push_back(g_cost == 0 ? 0u : std::uint32_t(gain * 10000 / g_cost));
        greedy_cost += g_cost;
        optimal_cost += o_cost;
        greedy_bytes += g_bytes;
        optimal_bytes += o_bytes;
        greedy_regions += greedy.size();
        optimal_regions += optimal.size();
    }
};
} // namespace

int main() {
    std::cout << "family,model,setup_weight,unit_weight,max_units,seed,epochs,strict_cost_gains,"
        "cost_gains_over_1_percent,sum_greedy_cost,sum_optimal_cost,sum_greedy_bytes,sum_optimal_bytes,"
        "sum_greedy_regions,sum_optimal_regions,p50_cost_savings_bps,p95_cost_savings_bps\n";
    std::mt19937 random(seed);
    for (std::size_t family = 0; family < family_names.size(); ++family) {
        std::array<std::array<Stats, caps.size()>, models.size()> results;
        for (std::uint32_t n = 0; n < epochs; ++n) {
            const auto trace = epoch(family, n % 2 != 0, random);
            for (std::size_t model = 0; model < models.size(); ++model) {
                for (std::size_t cap = 0; cap < caps.size(); ++cap) {
                    results[model][cap].compare({extent, caps[cap], models[model], trace.dirty, trace.islands});
                }
            }
        }
        for (std::size_t model = 0; model < models.size(); ++model) {
            for (std::size_t cap = 0; cap < caps.size(); ++cap) {
                auto& r = results[model][cap];
                std::sort(r.savings_bps.begin(), r.savings_bps.end());
                std::cout << family_names[family] << ',' << model_names[model] << ',' << models[model].setup
                    << ',' << models[model].unit << ',' << caps[cap] << ',' << seed << ',' << epochs
                    << ',' << r.gains << ',' << r.gains_over_1_percent << ',' << r.greedy_cost
                    << ',' << r.optimal_cost << ',' << r.greedy_bytes << ',' << r.optimal_bytes
                    << ',' << r.greedy_regions << ',' << r.optimal_regions
                    << ',' << r.savings_bps[(epochs - 1) * 50 / 100]
                    << ',' << r.savings_bps[(epochs - 1) * 95 / 100] << '\n';
            }
        }
    }
}
