// SPDX-License-Identifier: MIT
// Fixed-job launcher adapted from PortBridge's guarded shader readback probe.
#include "guard.h"

#include <cstdio>

namespace {
using namespace std::chrono_literals;
constexpr auto memory_limit = 512 * guard::mib;

struct Report {
    DWORD stage{};
    DWORD exit_code{};
    DWORD win_error{};
};

bool valid_container(const wchar_t* path) {
    WIN32_FILE_ATTRIBUTE_DATA data{};
    return GetFileAttributesExW(path, GetFileExInfoStandard, &data) &&
           !(data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && !data.nFileSizeHigh &&
           data.nFileSizeLow >= 32 && data.nFileSizeLow <= 4096;
}

Report invoke(const wchar_t* runner, const wchar_t* adapter, const wchar_t* image,
              const wchar_t* root, const wchar_t* log) {
    Report report{};
    if (!guard::worker_limits(memory_limit) || !valid_container(image) || !valid_container(root))
        return report;
    report.stage = 1;
    SECURITY_ATTRIBUTES inherit{sizeof(inherit), nullptr, TRUE};
    guard::Handle null(CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                  &inherit, OPEN_EXISTING, 0, nullptr));
    guard::Handle sink(CreateFileW(log, GENERIC_WRITE, FILE_SHARE_READ,
                                  &inherit, CREATE_NEW, 0, nullptr));
    guard::HandleList handles;
    HANDLE allowed[] = {null.value, sink.value};
    if (!null || !sink || !handles.set(allowed)) {
        report.win_error = GetLastError();
        return report;
    }
    auto command = guard::quote(runner) + L" native " + guard::quote(adapter) + L" " +
                   guard::quote(image) + L" " + guard::quote(root);
    STARTUPINFOEXW start{};
    start.StartupInfo.cb = sizeof(start);
    start.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    start.StartupInfo.hStdInput = null.value;
    start.StartupInfo.hStdOutput = start.StartupInfo.hStdError = sink.value;
    start.lpAttributeList = handles.list;
    PROCESS_INFORMATION child{};
    if (!CreateProcessW(runner, command.data(), nullptr, nullptr, TRUE,
                        CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW,
                        nullptr, nullptr, &start.StartupInfo, &child)) {
        report.win_error = GetLastError();
        return report;
    }
    guard::Handle process(child.hProcess), thread(child.hThread);
    BOOL in_job{};
    if (!IsProcessInJob(process.value, nullptr, &in_job) || !in_job ||
        ResumeThread(thread.value) == DWORD(-1)) {
        report.win_error = GetLastError();
        TerminateProcess(process.value, 2);
        WaitForSingleObject(process.value, 1000);
        return report;
    }
    report.stage = 2;
    if (WaitForSingleObject(process.value, INFINITE) == WAIT_OBJECT_0 &&
        GetExitCodeProcess(process.value, &report.exit_code))
        report.stage = 3;
    else
        report.win_error = GetLastError();
    return report;
}
}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc != 7) return 2;
    const std::wstring_view action(argv[1]);
    if (action == L"__worker") {
        const auto result = invoke(argv[2], argv[3], argv[4], argv[5], argv[6]);
        DWORD written{};
        if (!WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), &result, sizeof(result), &written, nullptr) ||
            written != sizeof(result)) return 1;
        return result.stage == 3 && !result.exit_code ? 0 : 1;
    }
    if (action != L"run") return 2;
    const auto result = guard::run<Report>(memory_limit, true, 3s,
        {L"__worker", argv[2], argv[3], argv[4], argv[5], argv[6]});
    std::printf("{\"guard\":\"%s\",\"reaped\":%s,\"process_exit\":%lu,"
                "\"stage\":%lu,\"runner_exit\":%lu,\"win_error\":%lu,\"peak_bytes\":%zu}\n",
                result.status, result.reaped ? "true" : "false", result.exit_code,
                result.report.stage, result.report.exit_code,
                result.win_error ? result.win_error : result.report.win_error, result.job_peak);
    return result.reaped && !result.exit_code && result.report.stage == 3 && !result.report.exit_code ? 0 : 1;
}
