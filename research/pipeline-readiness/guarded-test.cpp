// SPDX-License-Identifier: MIT
// Bound one Windows D3D12 test process before it can start loading shaders.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <psapi.h>

#include <chrono>
#include <cstdio>
#include <string>
#include <string_view>
#include <vector>

namespace {
constexpr SIZE_T gib = SIZE_T{1} << 30;

struct Handle {
    HANDLE value;
    explicit Handle(HANDLE h) : value(h) {}
    Handle(const Handle&) = delete;
    ~Handle() { if (*this) CloseHandle(value); }
    explicit operator bool() const { return value && value != INVALID_HANDLE_VALUE; }
};

struct Inheritance {
    std::vector<unsigned char> storage;
    LPPROC_THREAD_ATTRIBUTE_LIST list = nullptr;
    ~Inheritance() { if (list) DeleteProcThreadAttributeList(list); }

    bool restrict_to(HANDLE (&handles)[2]) {
        SIZE_T size = 0;
        InitializeProcThreadAttributeList(nullptr, 1, 0, &size);
        if (!size) return false;
        storage.resize(size);
        auto* data = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(storage.data());
        if (!InitializeProcThreadAttributeList(data, 1, 0, &size)) return false;
        list = data;
        return UpdateProcThreadAttribute(list, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                                         handles, sizeof(handles), nullptr, nullptr) != FALSE;
    }
};

bool headroom(SIZE_T commit, SIZE_T physical) {
    PERFORMANCE_INFORMATION memory{};
    memory.cb = sizeof(memory);
    if (!GetPerformanceInfo(&memory, sizeof(memory)) || memory.CommitLimit < memory.CommitTotal)
        return false;
    return (memory.CommitLimit - memory.CommitTotal) * memory.PageSize >= commit
        && memory.PhysicalAvailable * memory.PageSize >= physical;
}

int win_error(const char* step) {
    std::fprintf(stderr, "%s failed: %lu\n", step, GetLastError());
    return 2;
}
}

int wmain(int argc, wchar_t** argv) {
    if (argc != 4 || std::wstring_view(argv[1]).find(L'"') != std::wstring_view::npos ||
        std::wstring_view(argv[3]).find_first_not_of(L"abcdefghijklmnopqrstuvwxyz_0123456789:") != std::wstring_view::npos) {
        std::fprintf(stderr, "guarded-test EXE NEW_LOG TEST_NAME\n");
        return 2;
    }
    if (!headroom(8 * gib, 6 * gib)) {
        std::fprintf(stderr, "Insufficient system commit or RAM headroom\n");
        return 2;
    }
    SECURITY_ATTRIBUTES inherit{sizeof(inherit), nullptr, TRUE};
    Handle output(CreateFileW(argv[2], GENERIC_WRITE, FILE_SHARE_READ, &inherit, CREATE_NEW,
                              FILE_ATTRIBUTE_NORMAL, nullptr));
    Handle input(CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                             &inherit, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
    if (!output || !input) return win_error("CreateFileW");
    Handle job(CreateJobObjectW(nullptr, nullptr));
    if (!job) return win_error("CreateJobObjectW");
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE |
        JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_MEMORY;
    limits.ProcessMemoryLimit = limits.JobMemoryLimit = 2 * gib;
    if (!SetInformationJobObject(job.value, JobObjectExtendedLimitInformation, &limits, sizeof(limits)))
        return win_error("SetInformationJobObject");

    auto command = L"\"" + std::wstring(argv[1]) + L"\" --exact " + argv[3] + L" --nocapture --test-threads=1";
    Inheritance inherit_list;
    HANDLE handles[] = {input.value, output.value};
    if (!inherit_list.restrict_to(handles)) return win_error("Initialize handle list");
    STARTUPINFOEXW startup{};
    startup.StartupInfo.cb = sizeof(startup);
    startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    startup.StartupInfo.hStdInput = input.value;
    startup.StartupInfo.hStdOutput = startup.StartupInfo.hStdError = output.value;
    startup.lpAttributeList = inherit_list.list;
    PROCESS_INFORMATION child{};
    if (!CreateProcessW(argv[1], command.data(), nullptr, nullptr, TRUE,
                        CREATE_SUSPENDED | CREATE_NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT,
                        nullptr, nullptr, &startup.StartupInfo, &child))
        return win_error("CreateProcessW");
    Handle process(child.hProcess), thread(child.hThread);
    if (!AssignProcessToJobObject(job.value, process.value) || ResumeThread(thread.value) == DWORD(-1)) {
        const int error = win_error("AssignProcessToJobObject or ResumeThread");
        TerminateProcess(process.value, 2);
        WaitForSingleObject(process.value, 1000);
        return error;
    }
    using namespace std::chrono;
    const auto deadline = steady_clock::now() + seconds(20);
    DWORD wait;
    while ((wait = WaitForSingleObject(process.value, 25)) == WAIT_TIMEOUT) {
        if (steady_clock::now() >= deadline || !headroom(6 * gib, 4 * gib)) {
            TerminateJobObject(job.value, 3);
            WaitForSingleObject(process.value, 1000);
            std::fprintf(stderr, "Stopped after the time or system-memory limit\n");
            return 3;
        }
    }
    DWORD exit_code = 0;
    if (wait != WAIT_OBJECT_0 || !GetExitCodeProcess(process.value, &exit_code))
        return win_error("Test process status");
    if (!QueryInformationJobObject(job.value, JobObjectExtendedLimitInformation, &limits, sizeof(limits), nullptr))
        return win_error("QueryInformationJobObject");
    std::printf("exit=%lu peak_process_bytes=%zu peak_job_bytes=%zu\n", exit_code,
                limits.PeakProcessMemoryUsed, limits.PeakJobMemoryUsed);
    return exit_code == 0 ? 0 : 4;
}
