// SPDX-License-Identifier: MIT
// Adapted from the PortBridge D3D12 pipeline probe's Windows worker guard.
#pragma once

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <psapi.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <initializer_list>
#include <iterator>
#include <string>
#include <string_view>
#include <vector>

namespace guard {
using namespace std::chrono_literals;
constexpr std::uint64_t mib = 1024 * 1024;
constexpr DWORD limit_flags = JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_MEMORY |
                              JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

struct Handle {
    HANDLE value{};
    Handle() = default;
    explicit Handle(HANDLE handle) : value(handle) {}
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    ~Handle() { close(); }
    explicit operator bool() const { return value && value != INVALID_HANDLE_VALUE; }
    void close() {
        if (*this) CloseHandle(value);
        value = nullptr;
    }
};

struct HandleList {
    std::vector<BYTE> buffer;
    LPPROC_THREAD_ATTRIBUTE_LIST list{};
    ~HandleList() { if (list) DeleteProcThreadAttributeList(list); }
    bool set(HANDLE (&handles)[2]) {
        SIZE_T size{};
        InitializeProcThreadAttributeList(nullptr, 1, 0, &size);
        if (!size) return false;
        buffer.resize(size);
        const auto data = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(buffer.data());
        if (!InitializeProcThreadAttributeList(data, 1, 0, &size)) return false;
        list = data;
        return UpdateProcThreadAttribute(list, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, handles,
                                         sizeof(handles), nullptr, nullptr) != FALSE;
    }
};

inline std::wstring quote(std::wstring_view arg) {
    std::wstring out = L"\"";
    std::size_t slashes{};
    for (const auto ch : arg) {
        if (ch == L'\\') {
            ++slashes;
            continue;
        }
        out.append(slashes * (ch == L'"' ? 2 : 1), L'\\');
        slashes = 0;
        if (ch == L'"') out.push_back(L'\\');
        out.push_back(ch);
    }
    out.append(slashes * 2, L'\\');
    return out + L'"';
}

inline bool headroom(std::uint64_t commit, std::uint64_t physical) {
    PERFORMANCE_INFORMATION memory{};
    memory.cb = sizeof(memory);
    if (!GetPerformanceInfo(&memory, sizeof(memory)) || memory.CommitTotal > memory.CommitLimit)
        return false;
    return (memory.CommitLimit - memory.CommitTotal) * memory.PageSize >= commit &&
           memory.PhysicalAvailable * memory.PageSize >= physical;
}

inline bool worker_limits(std::uint64_t limit) {
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION info{};
    return QueryInformationJobObject(nullptr, JobObjectExtendedLimitInformation, &info, sizeof(info), nullptr) &&
           (info.BasicLimitInformation.LimitFlags & limit_flags) == limit_flags &&
           info.ProcessMemoryLimit == limit && info.JobMemoryLimit == limit;
}

template<typename Report>
struct Outcome {
    const char* status = "guard_setup_failed";
    DWORD win_error{}, exit_code{};
    SIZE_T process_peak{}, job_peak{};
    bool reaped{};
    Report report{};
};

template<typename Report>
Outcome<Report> run(std::uint64_t limit, bool monitor, std::chrono::milliseconds timeout,
                    std::initializer_list<const wchar_t*> args) {
    static_assert(sizeof(Report) <= 4096);
    Outcome<Report> out;
    if (monitor && !headroom(4096 * mib, 6144 * mib)) {
        out.status = "admission_refused";
        return out;
    }
    Handle input, output;
    Handle null(CreateFileW(L"NUL", GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                            nullptr, OPEN_EXISTING, 0, nullptr));
    Handle job(CreateJobObjectW(nullptr, nullptr));
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = limit_flags;
    limits.ProcessMemoryLimit = limits.JobMemoryLimit = limit;
    SECURITY_ATTRIBUTES inherit{sizeof(inherit), nullptr, TRUE};
    if (!null || !job ||
        !SetInformationJobObject(job.value, JobObjectExtendedLimitInformation, &limits, sizeof(limits)) ||
        !CreatePipe(&input.value, &output.value, &inherit, 4096) ||
        !SetHandleInformation(null.value, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)) {
        out.win_error = GetLastError();
        return out;
    }
    HandleList handles;
    HANDLE allowed[] = {null.value, output.value};
    if (!handles.set(allowed)) {
        out.win_error = GetLastError();
        return out;
    }
    wchar_t executable[32768]{};
    const auto size = GetModuleFileNameW(nullptr, executable, static_cast<DWORD>(std::size(executable)));
    if (!size || size == std::size(executable)) {
        out.win_error = GetLastError();
        return out;
    }
    std::wstring command = quote(std::wstring_view(executable, size));
    for (const auto arg : args) command += L" " + quote(arg);
    STARTUPINFOEXW start{};
    start.StartupInfo.cb = sizeof(start);
    start.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    start.StartupInfo.hStdInput = start.StartupInfo.hStdError = null.value;
    start.StartupInfo.hStdOutput = output.value;
    start.lpAttributeList = handles.list;
    PROCESS_INFORMATION child{};
    if (!CreateProcessW(executable, command.data(), nullptr, nullptr, TRUE,
                        CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW,
                        nullptr, nullptr, &start.StartupInfo, &child)) {
        out.win_error = GetLastError();
        return out;
    }
    Handle process(child.hProcess), thread(child.hThread);
    output.close();
    if (!AssignProcessToJobObject(job.value, process.value) || ResumeThread(thread.value) == DWORD(-1)) {
        out.win_error = GetLastError();
        TerminateProcess(process.value, 2);
        out.reaped = WaitForSingleObject(process.value, 1000) == WAIT_OBJECT_0;
        return out;
    }
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    for (;;) {
        const auto now = std::chrono::steady_clock::now();
        if (now >= deadline) {
            out.status = "timeout";
            break;
        }
        if (monitor && !headroom(3072 * mib, 4096 * mib)) {
            out.status = "system_pressure";
            break;
        }
        const auto remaining = std::chrono::ceil<std::chrono::milliseconds>(deadline - now);
        const auto waited = WaitForSingleObject(process.value, static_cast<DWORD>(std::min(25ms, remaining).count()));
        if (waited == WAIT_OBJECT_0) {
            out.status = "incomplete_worker_report";
            DWORD available{}, read{};
            if (GetExitCodeProcess(process.value, &out.exit_code) &&
                PeekNamedPipe(input.value, nullptr, 0, nullptr, &available, nullptr) &&
                available == sizeof(Report) &&
                ReadFile(input.value, &out.report, sizeof(Report), &read, nullptr) && read == sizeof(Report))
                out.status = "returned";
            break;
        }
        if (waited != WAIT_TIMEOUT) {
            out.win_error = GetLastError();
            break;
        }
    }
    if (QueryInformationJobObject(job.value, JobObjectExtendedLimitInformation, &limits, sizeof(limits), nullptr)) {
        out.process_peak = limits.PeakProcessMemoryUsed;
        out.job_peak = limits.PeakJobMemoryUsed;
    }
    job.close();
    out.reaped = WaitForSingleObject(process.value, 1000) == WAIT_OBJECT_0;
    return out;
}
}  // namespace guard
