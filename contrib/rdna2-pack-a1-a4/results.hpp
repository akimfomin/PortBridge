// SPDX-License-Identifier: MIT
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

struct Row {
    std::uint32_t value;
    std::uint32_t tag;
};
static_assert(sizeof(Row) == 8);
using Rows = std::array<Row, 6>;

// Independent fills make a persistent missing value byte observable even when
// the kernel wrote its tag. Ordinary arithmetic results can legally be zero.
inline const char* validate(const Rows& zero_fill, const Rows& ones_fill) {
    for (std::size_t i = 0; i < zero_fill.size(); ++i) {
        const auto expected_tag = 0x50420000u + i;
        if (zero_fill[i].tag != expected_tag || ones_fill[i].tag != expected_tag)
            return "Missing or misplaced result tag";
        if (zero_fill[i].value != ones_fill[i].value)
            return "Value differs between complementary fills";
    }
    if (zero_fill[0].value != UINT32_MAX)
        return "Wave32 entry EXEC control failed";
    if (zero_fill[1].value != 0x01230abcu)
        return "In-range integer pack control failed";
    return nullptr;
}
