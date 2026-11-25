// SPDX-License-Identifier: MIT
#include "physical_trace.hpp"

#include <array>
#include <iostream>
#include <numeric>

std::uint64_t units(std::span<const transfer::Range> ranges) {
    return std::accumulate(ranges.begin(), ranges.end(), std::uint64_t{0},
                           [](auto sum, auto range) { return sum + range.end - range.begin; });
}

int main(int argc, char** argv) {
    try {
        if (argc != 2) {
            throw std::invalid_argument("usage: trace_census TRACE");
        }
        const auto trace = physical::read_trace(argv[1]);
        std::cout << "case,extent_atoms,cap_atoms,setup,frames,active_frames,strict_model_wins,"
                     "wins_over_one_percent,different_plans,greedy_score,optimal_score,"
                     "exact_bytes,greedy_bytes,optimal_bytes\n";
        for (const auto& item : trace.cases) {
            for (auto setup : std::array<std::uint64_t, 4>{2, 8, 14, 32}) {
                const transfer::Cost cost{setup, 1};
                std::size_t active = 0, wins = 0, strong = 0, changed = 0;
                std::uint64_t greedy_total = 0, optimal_total = 0;
                std::uint64_t exact_units = 0, greedy_units = 0, optimal_units = 0;
                for (const auto& epoch : item.epochs) {
                    const transfer::Problem p{item.extent, item.cap, cost, epoch.dirty, item.islands};
                    const auto exact = transfer::plan(p, transfer::Strategy::exact);
                    const auto greedy = transfer::plan(p, transfer::Strategy::greedy);
                    const auto optimal = transfer::plan(p);
                    const auto gs = transfer::score(greedy, cost);
                    const auto os = transfer::score(optimal, cost);
                    if (os > gs) {
                        throw std::logic_error("exact objective exceeded greedy");
                    }
                    active += !epoch.dirty.empty();
                    wins += os < gs;
                    strong += gs - os > gs / 100;
                    changed += greedy != optimal;
                    greedy_total += gs;
                    optimal_total += os;
                    exact_units += units(exact);
                    greedy_units += units(greedy);
                    optimal_units += units(optimal);
                }
                std::cout << item.name << ',' << item.extent << ',' << item.cap << ',' << setup << ','
                          << item.epochs.size() << ',' << active << ',' << wins << ',' << strong << ','
                          << changed << ',' << greedy_total << ',' << optimal_total << ','
                          << exact_units * trace.atom_bytes << ',' << greedy_units * trace.atom_bytes << ','
                          << optimal_units * trace.atom_bytes << '\n';
            }
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
