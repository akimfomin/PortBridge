// SPDX-License-Identifier: MIT
#include "ordered_graphics.hpp"

#include <array>
#include <atomic>
#include <chrono>
#include <iostream>
#include <memory>
#include <string_view>

namespace {

using namespace std::chrono_literals;
using portbridge::OrderedDraws;
using portbridge::PipelineQueue;

void expect(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

void overlap_preserves_draw_order() {
    std::array<std::atomic<unsigned>, 2> builds{};
    std::promise<void> first_started;
    std::promise<void> second_started;
    auto after_first_started = first_started.get_future();
    auto after_second_started = second_started.get_future();
    std::vector<std::pair<std::size_t, int>> emitted;
    {
        PipelineQueue pipelines(builds.size(), 2, [&](std::size_t recipe) {
            ++builds.at(recipe);
            if (recipe == 0) {
                first_started.set_value();
                expect(after_second_started.wait_for(3s) == std::future_status::ready,
                       "later required pipeline did not start while first was in flight");
            } else {
                expect(after_first_started.wait_for(3s) == std::future_status::ready,
                       "first required pipeline did not start while second was in flight");
                second_started.set_value();
            }
        });
        OrderedDraws<std::unique_ptr<int>> window(pipelines, 4);
        const auto emit = [&](std::size_t recipe, const std::unique_ptr<int>& draw) {
            emitted.emplace_back(recipe, *draw);
        };

        window.append(0, std::make_unique<int>(11), emit);
        window.append(1, std::make_unique<int>(22), emit);
        window.append(0, std::make_unique<int>(33), emit);
        expect(emitted.empty(), "unexpected playback before flush");
        window.flush(emit);
        expect(emitted == std::vector<std::pair<std::size_t, int>>{{0, 11}, {1, 22}, {0, 33}},
               "playback changed order or lost a duplicate-key draw");
    }
    expect(builds[0] == 1 && builds[1] == 1, "each requested pipeline must build exactly once");
}

void full_window_flushes_before_the_next_draw() {
    PipelineQueue pipelines(4, 1, [](std::size_t) {});
    OrderedDraws<int> window(pipelines, 2);
    std::vector<int> emitted;
    const auto emit = [&](std::size_t, int draw) { emitted.push_back(draw); };

    window.append(0, 10, emit);
    window.append(1, 20, emit);
    expect(emitted.empty(), "a window may hold its exact capacity");
    window.append(2, 30, emit);
    expect(emitted == std::vector<int>{10, 20}, "appending beyond capacity must flush oldest draws");
    window.append(3, 40, emit);
    window.flush(emit);
    window.flush(emit);
    expect(emitted == std::vector<int>{10, 20, 30, 40}, "explicit flush must emit the tail only once");
}

void compile_failure_stops_playback_and_unwinds() {
    bool saw_failure = false;
    bool flush_refused = false;
    bool append_refused = false;
    std::vector<int> emitted;
    {
        PipelineQueue pipelines(3, 2, [](std::size_t recipe) {
            if (recipe == 1) throw std::runtime_error("intentional compile failure");
        });
        OrderedDraws<int> window(pipelines, 3);
        const auto emit = [&](std::size_t, int draw) { emitted.push_back(draw); };

        window.append(0, 10, emit);
        window.append(1, 20, emit);
        window.append(2, 30, emit);
        // A later ready pipeline must never be emitted past an earlier failure.
        pipelines.wait(2);
        try {
            window.flush(emit);
        } catch (const std::runtime_error& error) {
            saw_failure = std::string_view(error.what()) == "intentional compile failure";
        }
        try {
            window.flush(emit);
        } catch (const std::logic_error&) {
            flush_refused = true;
        }
        try {
            window.append(2, 40, emit);
        } catch (const std::logic_error&) {
            append_refused = true;
        }
    }
    expect(saw_failure, "flush did not propagate the compiler error");
    expect(flush_refused && append_refused, "failed playback must stay closed to retries");
    expect(emitted == std::vector<int>{10}, "playback emitted a draw at or after the failure");
}

} // namespace

int main() {
    try {
        overlap_preserves_draw_order();
        full_window_flushes_before_the_next_draw();
        compile_failure_stops_playback_and_unwinds();
        std::cout << "3 ordered graphics tests passed\n";
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
