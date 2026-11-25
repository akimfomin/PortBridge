// SPDX-License-Identifier: GPL-3.0-only
#include "shader_library.h"

#include <bit>
#include <cerrno>
#include <cstdint>
#include <iostream>
#include <string>

int main() {
    std::ios::sync_with_stdio(false);
    std::string line;
    while (std::getline(std::cin, line)) {
        errno = 711;
        leonida::Json value;
        const bool parsed = leonida::JsonReader(line).parse(value);
        const int status = errno;
        std::cout << int(parsed) << ',' << int(value.kind) << ','
                  << std::bit_cast<std::uint64_t>(value.number) << ',' << status << '\n';
    }
}
