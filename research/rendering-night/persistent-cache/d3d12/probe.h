// SPDX-License-Identifier: MIT
#pragma once

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdint>

constexpr std::uint64_t mib = 1024 * 1024;
constexpr std::uint64_t process_limit = 2048 * mib;
constexpr std::uint64_t smoke_limit = 512 * mib;
constexpr std::uint64_t mock_limit = 64 * mib;
constexpr DWORD memory_flags = JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_MEMORY |
                               JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

enum class Stage : std::uint32_t { complete, guard, input, adapter, device, cache, root_signature, pipeline, mock };

struct Report {
    Stage stage = Stage::guard;
    HRESULT error = E_FAIL;
    LUID luid{};
    UINT vendor{}, device{};
    std::uint64_t dxgi_driver_version{};
    SIZE_T private_before{}, private_after{};
    SIZE_T lifetime_peak_before{}, lifetime_peak_after{};
    double pso_ms{};
    DWORD shader_bytes{};
    BYTE shader_sha[32]{}, root_sha[32]{};
    wchar_t adapter[128]{};
    std::uint64_t individual_cache_bytes{}, library_bytes{};
    double library_open_ms{}, library_replay_ms{}, individual_replay_ms{}, warm_create_ms{};
    DWORD library_pipelines{};
};

bool has_worker_limits(std::uint64_t limit);
Report measure(const wchar_t* selector, const wchar_t* root_path, const wchar_t* shader_path, bool smoke);
enum class CacheAction { library_first, blob_first, seed, replay_plain, replay_blobs, replay_library };
Report measure_library(const wchar_t* selector, const wchar_t* root_path, wchar_t* const* shader_paths,
                       CacheAction action, const wchar_t* archive_path = nullptr);
