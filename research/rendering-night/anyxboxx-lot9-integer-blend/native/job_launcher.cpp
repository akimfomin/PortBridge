// SPDX-License-Identifier: MIT
// Adapted from PortBridge's bounded synthetic `readback_guard.cpp` launcher.
#include "guard.h"

#include <cstdio>
#include <filesystem>

namespace {
using namespace std::chrono_literals;
constexpr auto limit = 512 * guard::mib;

struct Report {
    DWORD stage{}, child_exit{}, os_error{};
};

bool valid_arm(std::wstring_view name) {
    return name == L"baseline" || name == L"candidate";
}

Report work(const wchar_t* arm, const wchar_t* path) {
    Report report;
    if (!valid_arm(arm) || !guard::worker_limits(limit)) {
        report.os_error = ERROR_ACCESS_DENIED;
        return report;
    }
    wchar_t self[32768]{};
    const auto length = GetModuleFileNameW(nullptr, self, static_cast<DWORD>(std::size(self)));
    if (!length || length == std::size(self)) return report;
    const auto child_exe = std::filesystem::path(self).parent_path() / L"uint-blend-worker.exe";
    SECURITY_ATTRIBUTES inherit{sizeof(inherit), nullptr, TRUE};
    guard::Handle null(CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                  &inherit, OPEN_EXISTING, 0, nullptr));
    guard::Handle sink(CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, &inherit, CREATE_NEW, 0, nullptr));
    guard::HandleList handles;
    HANDLE allowed[] = {null.value, sink.value};
    if (!null || !sink || !handles.set(allowed) || !SetEnvironmentVariableW(L"PORTBRIDGE_UINT_BLEND_APPROVED", L"1")) {
        report.os_error = GetLastError();
        return report;
    }
    STARTUPINFOEXW start{};
    start.StartupInfo.cb = sizeof(start);
    start.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    start.StartupInfo.hStdInput = null.value;
    start.StartupInfo.hStdOutput = start.StartupInfo.hStdError = sink.value;
    start.lpAttributeList = handles.list;
    auto command = guard::quote(child_exe.native()) + L" " + guard::quote(arm);
    if (!guard::headroom(4096 * guard::mib, 6144 * guard::mib)) {
        report.os_error = ERROR_NOT_ENOUGH_MEMORY;
        return report;
    }
    PROCESS_INFORMATION child{};
    if (!CreateProcessW(child_exe.c_str(), command.data(), nullptr, nullptr, TRUE,
                        CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW,
                        nullptr, nullptr, &start.StartupInfo, &child)) {
        report.os_error = GetLastError();
        return report;
    }
    report.stage = 1;
    guard::Handle process(child.hProcess), thread(child.hThread);
    BOOL in_job{};
    if (!IsProcessInJob(process.value, nullptr, &in_job)) report.os_error = GetLastError();
    else if (!in_job) report.os_error = ERROR_ACCESS_DENIED;
    else if (!guard::headroom(4096 * guard::mib, 6144 * guard::mib)) report.os_error = ERROR_NOT_ENOUGH_MEMORY;
    else if (ResumeThread(thread.value) == DWORD(-1)) report.os_error = GetLastError();
    if (report.os_error) {
        TerminateProcess(process.value, 2);
        WaitForSingleObject(process.value, 250);
        return report;
    }
    report.stage = 2;
    if (WaitForSingleObject(process.value, INFINITE) == WAIT_OBJECT_0 &&
        GetExitCodeProcess(process.value, &report.child_exit)) {
        report.stage = 3;
    } else {
        report.os_error = GetLastError();
    }
    return report;
}
}

int wmain(int argc, wchar_t** argv) {
    if (argc != 4 || !valid_arm(argv[2])) return 2;
    const std::wstring_view action(argv[1]);
    if (action == L"__worker") {
        const auto report = work(argv[2], argv[3]);
        DWORD written{};
        if (!WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), &report, sizeof(report), &written, nullptr) ||
            written != sizeof(report)) return 2;
        return report.stage == 3 && !report.child_exit ? 0 : 1;
    }
    if (action != L"native") return 2;
    const auto result = guard::run<Report>(limit, true, 3s, {L"__worker", argv[2], argv[3]});
    std::printf("guard_status=%s worker_reaped=%d worker_exit=%lu stage=%lu child_exit=%lu os_error=%lu job_peak=%zu\n",
                result.status, result.reaped, result.exit_code, result.report.stage, result.report.child_exit,
                result.win_error ? result.win_error : result.report.os_error, result.job_peak);
    return std::string_view(result.status) == "returned" && result.reaped && !result.exit_code &&
           result.report.stage == 3 && !result.report.child_exit ? 0 : 1;
}
