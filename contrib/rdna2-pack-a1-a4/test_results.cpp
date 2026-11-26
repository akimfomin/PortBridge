// SPDX-License-Identifier: MIT
#include "results.hpp"

#include <cstdio>
#include <utility>

int main() {
    Rows good{};
    for (std::size_t i = 0; i < good.size(); ++i)
        good[i].tag = static_cast<std::uint32_t>(0x50420000u + i);
    good[0].value = UINT32_MAX;
    good[1].value = 0x01230abcu;
    // Both extremes are admissible observations for the four unknowns.
    good[2].value = UINT32_MAX;
    if (validate(good, good)) return 1;

    for (std::size_t i = 0; i < good.size(); ++i) {
        auto corrupt = good;
        corrupt[i].tag = 0;
        if (!validate(corrupt, good) || !validate(good, corrupt)) return 1;
        corrupt = good;
        std::swap(corrupt[i], corrupt[(i + 1) % good.size()]);
        if (!validate(corrupt, corrupt)) return 1;
        for (unsigned bit = 0; bit < 32; ++bit) {
            auto zero = good, ones = good;
            zero[i].value &= ~(std::uint32_t{1} << bit);
            ones[i].value |= std::uint32_t{1} << bit;
            if (!validate(zero, ones)) return 1;
        }
    }
    for (std::size_t i = 0; i < 2; ++i) {
        auto bad_control = good;
        bad_control[i].value ^= 1;
        if (!validate(bad_control, bad_control)) return 1;
    }
    std::puts("CPU result validation passed");
}
