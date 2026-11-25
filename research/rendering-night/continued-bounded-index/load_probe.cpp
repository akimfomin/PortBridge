// SPDX-License-Identifier: GPL-3.0-only
#include "shader_library.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <psapi.h>

#include <chrono>
#include <cstdio>
#include <iostream>
#include <string_view>

using leonida::ShaderLibrary;
namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;

namespace {
constexpr std::array<std::string_view, 4> stages{"cs", "vs", "ps", "ms"};

std::string format(std::string_view prefix, std::size_t number, bool is_key) {
    char tail[72]{};
    if (is_key) {
        std::snprintf(tail, sizeof(tail), "%064zx", number);
        return tail;
    }
    std::snprintf(tail, sizeof(tail), "%06zu", number);
    return "Synthetic_" + std::string(prefix) + "_" + tail;
}

bool fixture(const fs::path& directory) {
    ShaderLibrary library;
    std::string error;
    if (!library.load(directory / "control", &error)) return false;
    const auto rows = library.candidates("cs", "repeat");
    if (library.size() != 3 || library.fspx_size() != 1 || library.bvh_size() != 0 ||
        rows.size() != 3 || rows[0]->name != "a" || rows[1]->name != "a" ||
        rows[2]->name != "fspx/b" || library.fspx_candidates("cs", "same-code").size() != 3)
        return false;
    if (library.load(directory / "bad-main", &error) || library.load(directory / "non-object", &error))
        return false;
    const auto* retained = library.find("cs", "repeat");
    if (library.size() != 3 || !retained || retained->name != "a") return false;
    if (!library.load(directory / "replacement", &error) || library.size() != 1 ||
        !library.find("vs", "new-key") || library.find("cs", "repeat"))
        return false;
    if (!library.load(directory / "reversed", &error)) return false;
    const auto ordered = library.candidates("cs", "repeat");
    if (ordered.size() != 3 || ordered[0]->name != "first" || ordered[1]->name != "second" ||
        ordered[2]->name != "library/third") return false;
    return library.load(directory / "empty", &error) && library.loaded() && !library.size();
}

bool verify_rows(const ShaderLibrary& library, std::size_t count, int richness) {
    if (library.size() != count || !library.loaded()) return false;
    for (std::size_t i = 0; i < count; ++i) {
        const auto stage = stages[i % stages.size()];
        const auto digest = format(stage, i + 1, true);
        const auto label = format(stage, i, false);
        const auto* entry = library.find(stage, digest);
        if (!entry || entry->name != label || entry->stage != stage || entry->fssm_sha256 != digest ||
            entry->spv_file != label + ".spv" || entry->binding_count != std::size_t(richness) + i % 4 ||
            entry->push_constant_bytes != 16 * (i % 10) || entry->lds_bytes != 32 * (i % 17) ||
            entry->local_size != std::array<std::uint32_t, 3>{i % 2 ? 32u : 64u, 1u, 1u} ||
            entry->uses_code_base != (i % 11 == 0) || entry->wave64 != (i % 2 == 0) ||
            entry->subgroup_size != (i % 2 ? 32u : 64u) ||
            entry->wave64_exchange != (i % 7 == 0 ? "workgroup" : "") ||
            entry->literal_samplers.size() != (i % 3 == 0 && richness > 1 ? 1u : 0u))
            return false;
        if (i % 3 == 0 && richness > 1 &&
            entry->literal_samplers[0] != std::array<std::uint32_t, 4>{
                std::uint32_t(i), std::uint32_t(i + 1), std::uint32_t(i + 2), std::uint32_t(i + 3)})
            return false;
        if (stage != "cs") {
            if (entry->input_signature.size() != std::size_t((richness + 1) / 2) ||
                entry->inputs.size() != std::size_t(richness) ||
                entry->outputs != std::vector<std::uint32_t>{0, 2, 5} ||
                entry->f16_halves != decltype(entry->f16_halves){{1, {1, 3}}, {2, {2, 4}}})
                return false;
            for (std::size_t j = 0; j < entry->input_signature.size(); ++j) {
                const auto& s = entry->input_signature[j];
                if (s.semantic != "TEXCOORD" || s.semantic_index != j || s.register_index != j + 1 ||
                    s.system_value != 0 || s.component_type != "float") return false;
            }
        }
        if (stage == "ms" && (entry->max_vertices != 128 || entry->max_primitives != 64)) return false;
    }
    return true;
}
}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc == 3 && std::wstring_view(argv[1]) == L"checks") {
        if (!fixture(argv[2])) return 1;
        std::cout << "duplicate rows, optional index precedence, malformed rollback and replacement passed\n";
        return 0;
    }
    if (argc != 4) return 2;
    const fs::path directory(argv[1]);
    const auto count = std::stoull(argv[2]);
    const auto richness = std::stoi(argv[3]);
    ShaderLibrary library;
    std::string error;
    const auto start = Clock::now();
    const bool loaded = library.load(directory, &error);
    const auto took = std::chrono::duration<double, std::milli>(Clock::now() - start).count();
    PROCESS_MEMORY_COUNTERS_EX memory{};
    if (!GetProcessMemoryInfo(GetCurrentProcess(), reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&memory),
                              sizeof(memory))) return 3;
    if (!loaded || !verify_rows(library, count, richness)) {
        std::cerr << "validation failed: " << error << "\n";
        return 1;
    }
    std::cout << "{\"verified\":" << count << ",\"load_ms\":" << took
              << ",\"peak_working_set\":" << memory.PeakWorkingSetSize
              << ",\"peak_commit\":" << memory.PeakPagefileUsage << "}\n";
    return 0;
}
