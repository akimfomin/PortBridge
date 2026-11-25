// SPDX-License-Identifier: MIT
#include "planner.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <optional>
#include <random>
#include <span>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace {

using transfer::Cost;
using transfer::Problem;
using transfer::Range;
using transfer::Strategy;

using Objective = std::tuple<std::uint64_t, std::uint64_t, std::size_t>;

struct Totals {
    std::size_t cases = 0;
    std::size_t wins_over_greedy = 0;
    std::uint64_t greatest_greedy_score_excess = 0;
    std::string witness;
};

std::string describe(const Problem& problem) {
    std::ostringstream out;
    out << "extent=" << problem.extent << " cap=" << problem.max_units
        << " setup=" << problem.cost.setup << " unit=" << problem.cost.unit << " dirty=";
    for (const auto unit : problem.dirty) {
        out << unit << ',';
    }
    out << " islands=";
    for (const auto island : problem.islands) {
        out << '[' << island.begin << ',' << island.end << ')';
    }
    return out.str();
}

void require(bool condition, const char* message, const Problem& problem) {
    if (!condition) {
        throw std::runtime_error(std::string(message) + " " + describe(problem));
    }
}

bool lies_in_one_island(std::span<const Range> islands, Range copy) {
    return std::any_of(islands.begin(), islands.end(), [copy](Range island) {
        return island.begin <= copy.begin && copy.end <= island.end;
    });
}

Objective check_plan(const Problem& problem, const std::vector<Range>& ranges) {
    std::uint64_t bytes = 0;
    std::uint32_t previous_end = 0;
    std::size_t next_dirty = 0;
    for (const auto range : ranges) {
        require(range.begin < range.end, "empty or reversed copy", problem);
        require(previous_end <= range.begin, "copies overlap or are unordered", problem);
        require(range.end - range.begin <= problem.max_units, "copy exceeds size cap", problem);
        require(lies_in_one_island(problem.islands, range), "copy crosses an authorization boundary", problem);
        require(next_dirty < problem.dirty.size() && problem.dirty[next_dirty] >= range.begin
                    && problem.dirty[next_dirty] < range.end,
                "copy missed the next dirty unit or covered no dirty units", problem);
        while (next_dirty < problem.dirty.size() && problem.dirty[next_dirty] < range.end) {
            ++next_dirty;
        }
        bytes += range.end - range.begin;
        previous_end = range.end;
    }
    require(next_dirty == problem.dirty.size(), "dirty units not covered", problem);
    const auto model = problem.cost.setup * ranges.size() + problem.cost.unit * bytes;
    require(transfer::score(ranges, problem.cost) == model, "public score disagrees with independent arithmetic", problem);
    return {model, bytes, ranges.size()};
}

// For nonnegative setup and unit costs, the tight interval enclosing a group
// of dirty units weakly improves score, and minimizes bytes on a score tie.
// Every ordered non-overlapping solution therefore has a representative among
// the partitions of the sorted dirty units. This oracle walks every split mask.
Objective exhaustive_score(const Problem& problem) {
    if (problem.dirty.empty()) {
        return {0, 0, 0};
    }
    std::optional<Objective> best;
    const auto split_limit = std::uint64_t{1} << (problem.dirty.size() - 1);
    for (std::uint64_t splits = 0; splits < split_limit; ++splits) {
        std::uint64_t bytes = 0;
        std::size_t count = 0;
        auto begin = problem.dirty.front();
        bool legal = true;
        for (std::size_t i = 0; i < problem.dirty.size(); ++i) {
            const auto last = i + 1 == problem.dirty.size();
            if (!last && (splits & (std::uint64_t{1} << i)) == 0) {
                continue;
            }
            const Range copy{begin, problem.dirty[i] + 1};
            const auto size = copy.end - copy.begin;
            if (size > problem.max_units || !lies_in_one_island(problem.islands, copy)) {
                legal = false;
                break;
            }
            bytes += size;
            ++count;
            if (!last) {
                begin = problem.dirty[i + 1];
            }
        }
        if (legal) {
            const Objective candidate{problem.cost.setup * count + problem.cost.unit * bytes, bytes, count};
            if (!best || candidate < *best) {
                best = candidate;
            }
        }
    }
    require(best.has_value(), "test oracle found no legal partition", problem);
    return *best;
}

void check_all_strategies(const Problem& problem, Totals& totals) {
    const auto target = exhaustive_score(problem);
    const auto optimal = check_plan(problem, transfer::plan(problem, Strategy::optimal));
    const auto greedy = check_plan(problem, transfer::plan(problem, Strategy::greedy));
    const auto exact = check_plan(problem, transfer::plan(problem, Strategy::exact));
    require(optimal == target, "optimal disagrees with exhaustive score/bytes/count", problem);
    require(std::get<1>(exact) == problem.dirty.size(), "exact copied clean units", problem);
    require(target <= greedy && target <= exact, "a legal baseline beat the exhaustive oracle", problem);
    ++totals.cases;
    if (optimal < greedy) {
        ++totals.wins_over_greedy;
        const auto score_excess = std::get<0>(greedy) - std::get<0>(optimal);
        if (score_excess > totals.greatest_greedy_score_excess) {
            totals.greatest_greedy_score_excess = score_excess;
            totals.witness = describe(problem);
        }
    }
}

std::vector<std::uint32_t> dirty_units(std::uint32_t extent, std::uint32_t mask) {
    std::vector<std::uint32_t> units;
    for (std::uint32_t i = 0; i < extent; ++i) {
        if (mask & (std::uint32_t{1} << i)) {
            units.push_back(i);
        }
    }
    return units;
}

std::vector<Range> permission_islands(std::uint32_t extent, std::uint32_t permitted) {
    std::vector<Range> islands;
    for (const auto unit : dirty_units(extent, permitted)) {
        if (!islands.empty() && islands.back().end == unit) {
            islands.back().end = unit + 1;
        } else {
            islands.push_back({unit, unit + 1});
        }
    }
    return islands;
}

void exhaustive_cases(Totals& totals) {
    constexpr Cost costs[]{{0, 0}, {0, 1}, {1, 0}, {1, 1}, {2, 1}, {8, 3}};
    for (std::uint32_t extent = 1; extent <= 6; ++extent) {
        for (std::uint32_t cuts = 0; cuts < (std::uint32_t{1} << (extent - 1)); ++cuts) {
            std::vector<Range> islands;
            auto begin = std::uint32_t{0};
            for (std::uint32_t unit = 1; unit < extent; ++unit) {
                if (cuts & (std::uint32_t{1} << (unit - 1))) {
                    islands.push_back({begin, unit});
                    begin = unit;
                }
            }
            islands.push_back({begin, extent});
            for (std::uint32_t mask = 0; mask < (std::uint32_t{1} << extent); ++mask) {
                const auto dirty = dirty_units(extent, mask);
                for (std::uint32_t cap = 1; cap <= extent + 1; ++cap) {
                    for (const auto cost : costs) {
                        check_all_strategies({extent, cap, cost, dirty, islands}, totals);
                    }
                }
            }
        }
    }
}

void permission_gap_cases(Totals& totals) {
    constexpr std::uint32_t extent = 7;
    constexpr Cost costs[]{{0, 0}, {3, 1}, {63, 1}};
    for (std::uint32_t permitted = 0; permitted < (std::uint32_t{1} << extent); ++permitted) {
        const auto islands = permission_islands(extent, permitted);
        for (auto mask = permitted;; mask = (mask - 1) & permitted) {
            const auto dirty = dirty_units(extent, mask);
            for (const auto cap : {1u, 3u, extent}) {
                for (const auto cost : costs) {
                    check_all_strategies({extent, cap, cost, dirty, islands}, totals);
                }
            }
            if (mask == 0) {
                break;
            }
        }
    }
}

void boundary_cases(Totals& totals) {
    std::mt19937_64 rng{0x7472616e73666572ULL};
    constexpr auto max = std::numeric_limits<std::uint32_t>::max();
    for (std::uint32_t i = 0; i < 4000; ++i) {
        const auto extent = static_cast<std::uint32_t>(1 + rng() % 17);
        const auto shift = (i % 2 == 0) ? 0u : max - extent;
        std::vector<Range> islands;
        std::vector<std::uint32_t> dirty;
        for (std::uint32_t position = 0; position < extent;) {
            const auto remaining = extent - position;
            const auto size = static_cast<std::uint32_t>(1 + rng() % remaining);
            const auto end = position + size;
            if (rng() % 3 != 0) {
                islands.push_back({shift + position, shift + end});
                for (auto unit = position; unit < end && dirty.size() < 11; ++unit) {
                    if (rng() % 4 == 0 || i % 5 == 0) {
                        dirty.push_back(shift + unit);
                    }
                }
            }
            position = end;
        }
        const auto cap = static_cast<std::uint32_t>(1 + rng() % (extent + 4));
        const auto cost = Cost{rng() % 4096, rng() % 253};
        check_all_strategies({shift + extent, cap, cost, dirty, islands}, totals);
    }
    const std::vector<Range> wide_island{{0, max}};
    const std::vector<std::uint32_t> extremes{0, 1, max - 3, max - 1};
    check_all_strategies({max, max, {8192, 1}, extremes, wide_island}, totals);
    check_all_strategies({max, 2, {17, 0}, extremes, wide_island}, totals);

    const std::vector<std::uint32_t> near_limit{max - 6, max - 4, max - 2};
    constexpr auto signed_cap = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    constexpr auto weight = signed_cap / (static_cast<std::uint64_t>(max) + 6);
    check_all_strategies({max, 3, {2 * weight, weight}, near_limit, wide_island}, totals);
}

void named_controls(Totals& totals) {
    check_all_strategies({0, 1, {0, 0}, {}, {}}, totals);

    const std::vector<Range> island{{0, 3}};
    const std::vector<std::uint32_t> separated{0, 2};
    const Problem equal_score{3, 3, {1, 1}, separated, island};
    check_all_strategies(equal_score, totals);
    require(transfer::plan(equal_score) == std::vector<Range>{{0, 1}, {2, 3}},
            "equal-cost overfetch must lose to the shorter transfer", equal_score);

    const std::vector<std::uint32_t> adjacent{0, 1};
    const Problem equal_bytes{3, 3, {0, 1}, adjacent, island};
    check_all_strategies(equal_bytes, totals);
    require(transfer::plan(equal_bytes) == std::vector<Range>{{0, 2}},
            "equal-cost equal-byte tie must prefer fewer regions", equal_bytes);

    const std::vector<Range> adjacent_islands{{0, 1}, {1, 3}};
    const Problem fenced{3, 3, {90, 1}, adjacent, adjacent_islands};
    check_all_strategies(fenced, totals);
    require(transfer::plan(fenced) == std::vector<Range>{{0, 1}, {1, 2}},
            "adjacent authorization islands must remain distinct", fenced);

    const std::vector<Range> wider_island{{0, 5}};
    const std::vector<std::uint32_t> clustered{0, 2, 3, 4};
    const Problem lookahead{5, 3, {3, 1}, clustered, wider_island};
    check_all_strategies(lookahead, totals);
    require(transfer::plan(lookahead) == std::vector<Range>{{0, 1}, {2, 5}},
            "expected the exact plan to reserve capacity for the dense cluster", lookahead);
    const auto greedy = transfer::plan(lookahead, Strategy::greedy);
    require(transfer::score(greedy, lookahead.cost) == 11
                && transfer::score(transfer::plan(lookahead), lookahead.cost) == 10,
            "expected the simple greedy counterexample to cost 11 vs 10", lookahead);
}

template <typename Function>
void require_rejection(Function operation, const char* explanation) {
    try {
        operation();
    } catch (const std::invalid_argument&) {
        return;
    } catch (const std::overflow_error&) {
        return;
    }
    throw std::runtime_error(std::string("accepted invalid input: ") + explanation);
}

void invalid_cases() {
    const std::vector<Range> allowed{{0, 4}};
    const std::vector<Range> gap{{0, 2}, {3, 4}};
    const std::vector<Range> overlapping{{0, 3}, {2, 4}};
    const std::vector<Range> unordered{{2, 4}, {0, 2}};
    const std::vector<Range> empty{{2, 2}, {3, 4}};
    const std::vector<Range> reversed{{2, 1}, {3, 4}};
    const std::vector<Range> beyond_extent{{0, 5}};
    const std::vector<std::uint32_t> valid{0, 3};
    const std::vector<std::uint32_t> duplicate{0, 0};
    const std::vector<std::uint32_t> descending{3, 0};
    const std::vector<std::uint32_t> forbidden{2};
    const std::vector<std::uint32_t> out_of_bounds{4};
    const auto check = [](const Problem& problem, const char* description) {
        for (const auto strategy : {Strategy::exact, Strategy::greedy, Strategy::optimal}) {
            require_rejection([&] { static_cast<void>(transfer::plan(problem, strategy)); }, description);
        }
    };

    check({4, 0, {2, 1}, valid, allowed}, "zero maximum copy size");
    check({4, 4, {2, 1}, duplicate, allowed}, "duplicate dirty units");
    check({4, 4, {2, 1}, descending, allowed}, "descending dirty units");
    check({4, 4, {2, 1}, forbidden, gap}, "dirty unit outside allowed islands");
    check({4, 4, {2, 1}, out_of_bounds, allowed}, "dirty unit equal to extent");
    check({4, 4, {2, 1}, valid, overlapping}, "overlapping permission islands");
    check({4, 4, {2, 1}, valid, unordered}, "unordered permission islands");
    check({4, 4, {2, 1}, valid, empty}, "empty permission island");
    check({4, 4, {2, 1}, valid, reversed}, "reversed permission island");
    check({4, 4, {2, 1}, valid, beyond_extent}, "permission island exceeds extent");
    check({4, 4, {2, 1}, valid, {}}, "dirty units with no permission islands");

    constexpr auto high = std::numeric_limits<std::uint64_t>::max();
    check({4, 4, {high, 1}, valid, allowed}, "score exceeds signed range");
    constexpr auto signed_cap = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    check({4, 4, {signed_cap / 2 + 1, 0}, valid, allowed}, "aggregate setup exceeds signed range");
    require_rejection([&] { static_cast<void>(transfer::score(allowed, {0, high})); }, "score multiplication overflow");
    require_rejection([&] { static_cast<void>(transfer::score(allowed, {high, 1})); }, "score addition overflow");
    require_rejection([&] { static_cast<void>(transfer::score(reversed, {0, 0})); }, "score of a reversed range");
    require_rejection([&] { static_cast<void>(transfer::score(empty, {0, 0})); }, "score of an empty range");
    if (transfer::score(allowed, {high, 0}) != high) {
        throw std::runtime_error("public score lost a representable unsigned result");
    }
}

}  // namespace

int main() {
    try {
        Totals totals;
        exhaustive_cases(totals);
        permission_gap_cases(totals);
        boundary_cases(totals);
        named_controls(totals);
        invalid_cases();
        std::cout << "verified_cases=" << totals.cases
                  << " strict_wins_over_greedy=" << totals.wins_over_greedy
                  << " greatest_greedy_score_excess=" << totals.greatest_greedy_score_excess << '\n';
        if (!totals.witness.empty()) {
            std::cout << "witness " << totals.witness << '\n';
        }
    } catch (const std::exception& error) {
        std::cerr << "verification failed: " << error.what() << '\n';
        return 1;
    }
}
