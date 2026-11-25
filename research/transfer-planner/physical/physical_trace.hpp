// SPDX-License-Identifier: MIT
#pragma once

#include "planner.hpp"

#include <charconv>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace physical {

struct Epoch {
    std::uint32_t id;
    std::vector<std::uint32_t> dirty;
};

struct Case {
    std::string name;
    std::uint32_t extent;
    std::uint32_t cap;
    std::vector<transfer::Range> islands;
    std::vector<Epoch> epochs;
};

struct Trace {
    std::uint32_t atom_bytes = 0;
    std::vector<Case> cases;
};

inline std::uint32_t number(std::istringstream& line) {
    std::string token;
    line >> token;
    std::uint32_t value = 0;
    const auto [end, result] = std::from_chars(token.data(), token.data() + token.size(), value);
    if (result != std::errc{} || end != token.data() + token.size()) {
        throw std::invalid_argument("expected an unsigned trace field");
    }
    return value;
}

inline Trace read_trace(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::invalid_argument("could not open the trace");
    }
    Trace result;
    Case* current = nullptr;
    Epoch* epoch = nullptr;
    std::string text;
    while (std::getline(input, text)) {
        std::istringstream line(text);
        std::string tag;
        line >> tag;
        if (tag.empty() || tag.front() == '#') {
            continue;
        }
        if (tag == "PBTRACE1" && result.atom_bytes == 0) {
            result.atom_bytes = number(line);
            if (result.atom_bytes != 64) {
                throw std::invalid_argument("PBTRACE1 requires 64-byte atoms");
            }
        } else if (tag == "case" && result.atom_bytes && !current && !epoch) {
            std::string name;
            line >> name;
            const auto extent = number(line);
            const auto cap = number(line);
            if (name.empty() || name.find_first_not_of(
                    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-") != std::string::npos
                || !extent || !cap) {
                throw std::invalid_argument("invalid trace case");
            }
            result.cases.push_back({name, extent, cap, {}, {}});
            current = &result.cases.back();
        } else if (tag == "allow" && current && !epoch && current->epochs.empty()) {
            const auto begin = number(line);
            const auto end = number(line);
            if (begin >= end || end > current->extent
                || (!current->islands.empty() && begin < current->islands.back().end)) {
                throw std::invalid_argument("invalid trace range");
            }
            current->islands.push_back({begin, end});
        } else if (tag == "frame" && current && !epoch && !current->islands.empty()) {
            const auto id = number(line);
            if (!current->epochs.empty() && id <= current->epochs.back().id) {
                throw std::invalid_argument("trace frames must be ordered");
            }
            current->epochs.push_back({id, {}});
            epoch = &current->epochs.back();
        } else if (tag == "dirty" && current && epoch) {
            const auto begin = number(line);
            const auto end = number(line);
            if (begin >= end || end > current->extent
                || (!epoch->dirty.empty() && begin <= epoch->dirty.back())) {
                throw std::invalid_argument("invalid dirty interval");
            }
            for (auto at = begin; at < end; ++at) {
                epoch->dirty.push_back(at);
            }
        } else if (tag == "endframe" && epoch) {
            epoch = nullptr;
        } else if (tag == "endcase" && current && !epoch && !current->epochs.empty()) {
            current = nullptr;
        } else {
            throw std::invalid_argument("unexpected record in trace");
        }
        std::string extra;
        if (line >> extra) {
            throw std::invalid_argument("unexpected trailing field in trace");
        }
    }
    if (current || epoch || result.cases.empty() || input.bad()) {
        throw std::invalid_argument("incomplete trace");
    }
    return result;
}

}  // namespace physical
