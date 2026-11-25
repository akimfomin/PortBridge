// SPDX-License-Identifier: MIT
#include "planner.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <limits>
#include <stdexcept>

namespace transfer {
namespace {

using Points = std::span<const std::uint32_t>;
using Key = std::array<std::int64_t, 3>;

struct Choice {
    Key prefix;
    std::size_t start;
};

struct Scratch {
    std::vector<Choice> choices;
    std::vector<std::size_t> parents;
};

std::uint64_t product(std::uint64_t a, std::uint64_t b, std::uint64_t limit) {
    if (a && b > limit / a) {
        throw std::overflow_error("transfer cost exceeds the supported range");
    }
    return a * b;
}

void validate(const Problem& problem) {
    if (problem.max_units == 0) {
        throw std::invalid_argument("the transfer limit must be positive");
    }
    std::uint32_t end = 0;
    for (Range island : problem.islands) {
        if (island.begin < end || island.begin >= island.end || island.end > problem.extent) {
            throw std::invalid_argument("invalid or unordered authority island");
        }
        end = island.end;
    }
    std::size_t island = 0;
    for (std::size_t i = 0; i < problem.dirty.size(); ++i) {
        const auto unit = problem.dirty[i];
        if (unit >= problem.extent || (i && unit <= problem.dirty[i - 1])) {
            throw std::invalid_argument("dirty units must be unique, sorted and in bounds");
        }
        while (island < problem.islands.size() && problem.islands[island].end <= unit) {
            ++island;
        }
        if (island == problem.islands.size() || problem.islands[island].begin > unit) {
            throw std::invalid_argument("a dirty unit has no authoritative source");
        }
    }
    if (problem.dirty.empty()) {
        return;
    }
    // This also bounds the signed coordinate transformations in the deque.
    constexpr std::uint64_t limit = std::numeric_limits<std::int64_t>::max();
    const auto extent_cost = product(problem.extent, problem.cost.unit, limit);
    product(problem.dirty.size(), problem.cost.setup, limit - extent_cost);
}

bool beneficial(std::uint32_t gap, Cost cost) {
    return gap == 0 || gap * cost.unit < cost.setup;
}

void simple(Points points, const Problem& problem, bool merge_holes, std::vector<Range>& result) {
    Range current{points.front(), points.front() + 1};
    for (auto unit : points.subspan(1)) {
        const auto gap = unit - current.end;
        if (unit + 1 - current.begin <= problem.max_units
            && (gap == 0 || (merge_holes && beneficial(gap, problem.cost)))) {
            current.end = unit + 1;
        } else {
            result.push_back(current);
            current = {unit, unit + 1};
        }
    }
    result.push_back(current);
}

void solve_bounded(Points points, const Problem& problem, Scratch& scratch,
                   std::vector<Range>& result) {
    const auto setup = static_cast<std::int64_t>(problem.cost.setup);
    const auto weight = static_cast<std::int64_t>(problem.cost.unit);
    auto& choices = scratch.choices;
    auto& parents = scratch.parents;
    choices.clear();
    choices.reserve(points.size());
    parents.resize(points.size());
    std::size_t front = 0;
    Key prefix{};

    for (std::size_t i = 0; i < points.size(); ++i) {
        const auto end = points[i] + 1;
        while (front < choices.size()
               && end - points[choices[front].start] > problem.max_units) {
            ++front;
        }
        // Every predecessor adds the same end-dependent terms. A later
        // predecessor with a better key survives every older one's window.
        const Key key{prefix[0] - weight * points[i], prefix[1] - points[i], prefix[2]};
        while (choices.size() > front && key <= choices.back().prefix) {
            choices.pop_back();
        }
        choices.push_back({key, i});
        const auto& best = choices[front];
        prefix = {best.prefix[0] + weight * end + setup,
                  best.prefix[1] + end, best.prefix[2] + 1};
        parents[i] = best.start;
    }

    const auto offset = result.size();
    for (std::size_t end = points.size(); end > 0;) {
        const auto start = parents[end - 1];
        result.push_back({points[start], points[end - 1] + 1});
        end = start;
    }
    std::reverse(result.begin() + static_cast<std::ptrdiff_t>(offset), result.end());
}

void optimal(Points points, const Problem& problem, Scratch& scratch, std::vector<Range>& result) {
    while (!points.empty()) {
        std::size_t split = 1;
        while (split < points.size()
               && beneficial(points[split] - points[split - 1] - 1, problem.cost)) {
            ++split;
        }
        // Crossing an unprofitable gap can only lose cost or the copied-byte
        // tie break. An unconstrained profitable block needs a single range.
        const auto block = points.first(split);
        const auto width = block.back() + 1 - block.front();
        if (width <= problem.max_units) {
            result.push_back({block.front(), block.back() + 1});
        } else if (block.size() == width) {
            simple(block, problem, false, result);
        } else {
            solve_bounded(block, problem, scratch, result);
        }
        points = points.subspan(split);
    }
}

}  // namespace

std::vector<Range> plan(const Problem& problem, Strategy strategy) {
    validate(problem);
    std::vector<Range> result;
    Scratch scratch;
    Points points = problem.dirty;
    for (Range island : problem.islands) {
        if (points.empty()) {
            break;
        }
        std::size_t count = 0;
        while (count < points.size() && points[count] < island.end) {
            ++count;
        }
        if (count == 0) {
            continue;
        }
        const auto authorized = points.first(count);
        if (strategy == Strategy::optimal) {
            optimal(authorized, problem, scratch, result);
        } else {
            simple(authorized, problem, strategy == Strategy::greedy, result);
        }
        points = points.subspan(count);
    }
    return result;
}

std::uint64_t score(std::span<const Range> ranges, Cost cost) {
    constexpr auto limit = std::numeric_limits<std::uint64_t>::max();
    std::uint64_t total = product(ranges.size(), cost.setup, limit);
    for (Range range : ranges) {
        if (range.begin >= range.end) {
            throw std::invalid_argument("empty or inverted transfer range");
        }
        total += product(range.end - range.begin, cost.unit, limit - total);
    }
    return total;
}

}  // namespace transfer
