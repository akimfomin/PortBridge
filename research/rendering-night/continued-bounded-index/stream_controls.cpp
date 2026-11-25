// SPDX-License-Identifier: GPL-3.0-only
#include "shader_library.h"

#include <iostream>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace fs = std::filesystem;
using leonida::ShaderLibrary;

namespace {
constexpr std::size_t chunk = 16 * 1024;
constexpr std::string_view bom = "\xef\xbb\xbf";
constexpr std::string_view row = R"json({"same":{"stage":"cs","fssm_sha256":"repeat","spv":"edge-\u00e9.spv","lds_bytes":16e+1,"wave64":false},"same":{"stage":"cs","fssm_sha256":"repeat","spv":"second.spv"}})json";

bool put(const fs::path& folder, std::string_view content) {
    fs::create_directories(folder);
    std::ofstream file(folder / "index.json", std::ios::binary);
    file.write(content.data(), static_cast<std::streamsize>(content.size()));
    file.close();
    return file.good();
}

bool order(const ShaderLibrary& library) {
    const auto rows = library.candidates("cs", "repeat");
    return library.size() == 2 && rows.size() == 2 && rows[0]->name == "same" && rows[1]->name == "same" &&
           rows[0]->spv_file == "edge-\xc3\xa9.spv" && rows[0]->lds_bytes == 160 && !rows[0]->wave64 &&
           rows[1]->spv_file == "second.spv";
}

bool check_refills(ShaderLibrary& library, const fs::path& folder) {
    constexpr std::pair<std::string_view, std::size_t> tokens[]{
        {"\\u00e9", 3}, {"16e+1", 2}, {"false", 2}, {"edge-", 3}, {"},\"same\"", 2},
    };
    std::string error;
    for (const auto& [token, split] : tokens) {
        const auto index = row.find(token);
        if (index == std::string_view::npos) return false;
        const std::string whitespace(chunk - bom.size() - index - split, ' ');
        const auto content = std::string(bom) + whitespace + std::string(row) + std::string(chunk * 3 + 1, '\n');
        if (!put(folder, content) || !library.load(folder, &error) || !order(library)) return false;
    }
    auto decimal = std::string(row);
    const auto digit = decimal.find("16e+1");
    decimal.replace(digit, 5, "00160");
    const std::string split_integer(chunk - digit - 2, ' ');
    if (!put(folder, split_integer + decimal) || !library.load(folder, &error) || !order(library)) return false;
    const auto giant = std::string(row.substr(0, row.size() - 1)) + ",\"padding\":\"" +
                       std::string(chunk * 3 + 7, 'x') + "\",\"number\":0.5" + std::string(chunk * 2 + 9, '0') + "}";
    return put(folder, giant) && library.load(folder, &error) && order(library);
}

bool check_tail(ShaderLibrary& library, const fs::path& folder) {
    const auto saved = library.directory();
    const auto text = std::string(row) + std::string(chunk * 4, ' ') + '!';
    std::string error;
    return put(folder, text) && !library.load(folder, &error) &&
           error == "index.json is not a JSON object" && library.directory() == saved && order(library);
}

bool check_depth(ShaderLibrary& library, const fs::path& folder) {
    std::string error;
    const auto nested = [&](std::size_t depth) {
        return std::string(row.substr(0, row.size() - 1)) + ",\"nested\":" +
               std::string(depth, '[') + '0' + std::string(depth, ']') + '}';
    };
    return put(folder, nested(63)) && library.load(folder, &error) && order(library) &&
           put(folder, nested(64)) && !library.load(folder, &error) &&
           error == "index.json is not a JSON object" && order(library);
}

#ifdef PB_STREAMED
bool check_read_error(ShaderLibrary& library, const fs::path& folder) {
    const auto saved = library.directory();
    const std::string text = std::string(row) + std::string(chunk * 4 - row.size(), ' ') + '!';
    if (!put(folder, text)) return false;
    std::string error;
#ifdef _WIN32
    const auto path = folder / "index.json";
    const HANDLE handle = CreateFileW(path.c_str(), GENERIC_READ | GENERIC_WRITE,
                                      FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING,
                                      FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle == INVALID_HANDLE_VALUE) return false;
    OVERLAPPED range{};
    range.Offset = static_cast<DWORD>(chunk * 4);
    const bool locked = LockFileEx(handle, LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &range);
    const bool loaded = locked && library.load(folder, &error);
    CloseHandle(handle);
    if (!locked || loaded) return false;
#else
    const auto path = folder / "index.json";
    if (!fs::remove(path) || !fs::create_directory(path) || library.load(folder, &error)) return false;
#endif
    return error == "index.json could not be read" && library.directory() == saved && order(library);
}
#endif
}

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const fs::path root(argv[1]);
    ShaderLibrary library;
    if (!check_refills(library, root / "refill")) return 3;
    std::cout << "BOM, duplicate order and split integer/escape/exponent/literal tokens: OK\n";
    if (!check_tail(library, root / "malformed-tail")) return 4;
    std::cout << "late malformed suffix retained previously loaded main index: OK\n";
    if (!check_depth(library, root / "depth")) return 5;
    std::cout << "nested arrays at and beyond the original hard depth limit: OK\n";
#ifdef PB_STREAMED
    if (!check_read_error(library, root / "read-failure")) return 6;
    std::cout << "late read failure retained previously loaded main index: OK\n";
#endif
}
