// SPDX-License-Identifier: MIT
#include "probe.h"

#include <psapi.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace {
using namespace std::chrono_literals;

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

struct InheritedHandles {
    std::vector<BYTE> bytes;
    LPPROC_THREAD_ATTRIBUTE_LIST attributes{};
    ~InheritedHandles() { if (attributes) DeleteProcThreadAttributeList(attributes); }

    bool set(HANDLE (&handles)[2]) {
        SIZE_T size = 0;
        InitializeProcThreadAttributeList(nullptr, 1, 0, &size);
        if (!size) return false;
        bytes.resize(size);
        auto* list = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(bytes.data());
        if (!InitializeProcThreadAttributeList(list, 1, 0, &size)) return false;
        attributes = list;
        return UpdateProcThreadAttribute(attributes, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, handles,
                                         sizeof(handles), nullptr, nullptr) != FALSE;
    }
};

struct Outcome {
    enum class Status { setup, refused, pressure, timeout, incomplete, returned } status = Status::setup;
    DWORD os_error{}, exit_code{};
    SIZE_T process_peak{}, job_peak{};
    bool worker_reaped{};
    Report report;
};

std::wstring quote_arg(std::wstring_view arg) {
    std::wstring out = L"\"";
    std::size_t slashes = 0;
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
    out.push_back(L'"');
    return out;
}

bool has_system_headroom(std::uint64_t commit, std::uint64_t physical) {
    PERFORMANCE_INFORMATION memory{};
    memory.cb = sizeof(memory);
    if (!GetPerformanceInfo(&memory, sizeof(memory)) || memory.CommitTotal > memory.CommitLimit)
        return false;
    const auto available_commit = (memory.CommitLimit - memory.CommitTotal) * memory.PageSize;
    return available_commit >= commit && memory.PhysicalAvailable * memory.PageSize >= physical;
}

struct ChildBudget {
    std::uint64_t process;
    std::uint64_t start_commit;
    std::uint64_t stop_commit;
};

constexpr ChildBudget mock_budget{mock_limit, 0, 0};
constexpr ChildBudget smoke_budget{smoke_limit, 4 * 1024 * mib, 3 * 1024 * mib};
constexpr ChildBudget pair_budget{process_limit, 8 * 1024 * mib, 6 * 1024 * mib};

Outcome run_child(ChildBudget budget, std::chrono::milliseconds deadline_after,
                  std::initializer_list<const wchar_t*> args) {
    Outcome out;
    if (budget.start_commit && !has_system_headroom(budget.start_commit, 6 * 1024 * mib)) {
        out.status = Outcome::Status::refused;
        return out;
    }

    Handle input, pipe;
    Handle null(CreateFileW(L"NUL", GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                            nullptr, OPEN_EXISTING, 0, nullptr));
    Handle job(CreateJobObjectW(nullptr, nullptr));
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = memory_flags;
    limits.ProcessMemoryLimit = limits.JobMemoryLimit = budget.process;
    SECURITY_ATTRIBUTES inherit{sizeof(inherit), nullptr, TRUE};
    if (!null || !job ||
        !SetInformationJobObject(job.value, JobObjectExtendedLimitInformation, &limits, sizeof(limits)) ||
        !CreatePipe(&input.value, &pipe.value, &inherit, 4096) ||
        !SetHandleInformation(null.value, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)) {
        out.os_error = GetLastError();
        return out;
    }
    InheritedHandles inherited;
    HANDLE allowed[] = {null.value, pipe.value};
    if (!inherited.set(allowed)) {
        out.os_error = GetLastError();
        return out;
    }

    wchar_t exe[32768];
    const auto size = GetModuleFileNameW(nullptr, exe, static_cast<DWORD>(std::size(exe)));
    if (!size || size == std::size(exe)) {
        out.os_error = GetLastError();
        return out;
    }
    std::wstring command = quote_arg(std::wstring_view(exe, size));
    for (const auto arg : args) command += L" " + quote_arg(arg);
    STARTUPINFOEXW startup{};
    startup.StartupInfo.cb = sizeof(startup);
    startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    startup.StartupInfo.hStdInput = startup.StartupInfo.hStdError = null.value;
    startup.StartupInfo.hStdOutput = pipe.value;
    startup.lpAttributeList = inherited.attributes;
    PROCESS_INFORMATION child{};
    if (!CreateProcessW(exe, command.data(), nullptr, nullptr, TRUE,
                        CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW,
                        nullptr, nullptr, &startup.StartupInfo, &child)) {
        out.os_error = GetLastError();
        return out;
    }
    Handle process(child.hProcess), thread(child.hThread);
    pipe.close();
    if (!AssignProcessToJobObject(job.value, process.value) || ResumeThread(thread.value) == DWORD(-1)) {
        out.os_error = GetLastError();
        // Assignment can fail on a host that prohibits nested jobs. The child is still suspended.
        TerminateProcess(process.value, 2);
        out.worker_reaped = WaitForSingleObject(process.value, 1000) == WAIT_OBJECT_0;
        return out;
    }
    const auto deadline = std::chrono::steady_clock::now() + deadline_after;
    for (;;) {
        const auto now = std::chrono::steady_clock::now();
        if (now >= deadline) {
            out.status = Outcome::Status::timeout;
            break;
        }
        if (budget.stop_commit && !has_system_headroom(budget.stop_commit, 4 * 1024 * mib)) {
            out.status = Outcome::Status::pressure;
            break;
        }
        const auto remaining_ms = std::chrono::ceil<std::chrono::milliseconds>(deadline - now);
        const DWORD waited = WaitForSingleObject(process.value, static_cast<DWORD>(std::min(remaining_ms, 25ms).count()));
        if (waited == WAIT_OBJECT_0) {
            out.status = Outcome::Status::incomplete;
            DWORD available = 0, read = 0;
            if (GetExitCodeProcess(process.value, &out.exit_code) &&
                PeekNamedPipe(input.value, nullptr, 0, nullptr, &available, nullptr) && available == sizeof(Report) &&
                ReadFile(input.value, &out.report, sizeof(Report), &read, nullptr) && read == sizeof(Report))
                out.status = Outcome::Status::returned;
            break;
        }
        if (waited != WAIT_TIMEOUT) {
            out.os_error = GetLastError();
            break;
        }
    }
    if (QueryInformationJobObject(job.value, JobObjectExtendedLimitInformation, &limits, sizeof(limits), nullptr)) {
        out.process_peak = limits.PeakProcessMemoryUsed;
        out.job_peak = limits.PeakJobMemoryUsed;
    }
    job.close();  // kill-on-close also covers hardware pressure, deadline, and unexpected wait failures
    out.worker_reaped = WaitForSingleObject(process.value, 1000) == WAIT_OBJECT_0;
    return out;
}

std::string json_string(const wchar_t* wide) {
    std::string out = "\"";
    const int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide, -1, nullptr, 0, nullptr, nullptr);
    if (size > 0) {
        std::string text(static_cast<std::size_t>(size), '\0');
        WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide, -1, text.data(), size, nullptr, nullptr);
        text.pop_back();
        for (unsigned char ch : text) {
            if (ch == '"' || ch == '\\') {
                out.push_back('\\');
                out.push_back(static_cast<char>(ch));
            } else if (ch < 32) {
                char escaped[7];
                std::snprintf(escaped, sizeof(escaped), "\\u%04x", static_cast<unsigned>(ch));
                out += escaped;
            } else {
                out.push_back(static_cast<char>(ch));
            }
        }
    }
    return out + '"';
}

const char* status_name(Outcome::Status status) {
    switch (status) {
    case Outcome::Status::setup: return "guard_setup_failed";
    case Outcome::Status::refused: return "admission_refused";
    case Outcome::Status::pressure: return "system_pressure";
    case Outcome::Status::timeout: return "timeout";
    case Outcome::Status::incomplete: return "incomplete_worker_report";
    case Outcome::Status::returned: return "returned";
    }
    return "unknown";
}

const char* stage_name(Stage stage) {
    switch (stage) {
    case Stage::complete: return "complete";
    case Stage::guard: return "guard";
    case Stage::input: return "input";
    case Stage::adapter: return "adapter";
    case Stage::device: return "device";
    case Stage::cache: return "cache";
    case Stage::root_signature: return "root_signature";
    case Stage::pipeline: return "pipeline";
    case Stage::mock: return "mock";
    }
    return "unknown";
}

std::string hex(const BYTE (&bytes)[32]) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string text;
    text.reserve(sizeof(bytes) * 2);
    for (BYTE byte : bytes) {
        text.push_back(digits[byte >> 4]);
        text.push_back(digits[byte & 15]);
    }
    return text;
}

void print(const char* label, const Outcome& out) {
    std::printf("{\"case\":\"%s\",\"status\":\"%s\",\"win32_error\":%lu,\"exit_code\":%lu,"
                "\"process_peak_bytes\":%zu,\"job_peak_bytes\":%zu,\"worker_reaped\":%s",
                label, status_name(out.status), out.os_error, out.exit_code, out.process_peak, out.job_peak,
                out.worker_reaped ? "true" : "false");
    if (out.status == Outcome::Status::returned) {
        const Report& r = out.report;
        std::printf(",\"stage\":\"%s\",\"hresult\":\"0x%08lx\",\"adapter\":%s,"
                    "\"adapter_luid\":\"%08lx:%08lx\",\"vendor_id\":%u,\"device_id\":%u,"
                    "\"dxgi_driver_version\":\"%016llx\",\"shader_bytes\":%lu,"
                    "\"shader_sha256\":\"%s\",\"root_sha256\":\"%s\",\"pso_ms\":%.6f,"
                    "\"private_before_bytes\":%zu,\"private_after_bytes\":%zu,"
                    "\"lifetime_private_peak_before_bytes\":%zu,\"lifetime_private_peak_after_bytes\":%zu",
                    stage_name(r.stage), static_cast<unsigned long>(r.error), json_string(r.adapter).c_str(),
                    static_cast<unsigned long>(r.luid.HighPart), r.luid.LowPart, r.vendor, r.device,
                    static_cast<unsigned long long>(r.dxgi_driver_version), r.shader_bytes,
                    hex(r.shader_sha).c_str(), hex(r.root_sha).c_str(), r.pso_ms,
                    r.private_before, r.private_after, r.lifetime_peak_before, r.lifetime_peak_after);
        if (r.library_pipelines) {
            std::printf(",\"pipelines\":%lu,\"individual_cache_bytes\":%llu,\"library_bytes\":%llu,"
                        "\"library_open_ms\":%.6f,\"library_replay_ms\":%.6f,"
                        "\"individual_replay_ms\":%.6f,\"warm_create_ms\":%.6f",
                        r.library_pipelines, static_cast<unsigned long long>(r.individual_cache_bytes),
                        static_cast<unsigned long long>(r.library_bytes), r.library_open_ms,
                        r.library_replay_ms, r.individual_replay_ms, r.warm_create_ms);
        }
    }
    std::printf("}\n");
}

int emit(const Report& report) {
    DWORD written = 0;
    if (!WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), &report, sizeof(report), &written, nullptr) ||
        written != sizeof(report)) return 2;
    return FAILED(report.error) ? 2 : 0;
}

int mock(bool block) {
    Report report;
    if (!has_worker_limits(mock_limit)) return emit(report);
    report.stage = Stage::mock;
    if (block) {
        Sleep(2000);
        return emit(report);
    }
    void* small = VirtualAlloc(nullptr, mib, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    void* over_limit = VirtualAlloc(nullptr, mock_limit + mib, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (small) VirtualFree(small, 0, MEM_RELEASE);
    if (over_limit) VirtualFree(over_limit, 0, MEM_RELEASE);
    report.error = small && !over_limit ? S_OK : E_FAIL;
    return emit(report);
}

bool successful(const Outcome& out) {
    return out.status == Outcome::Status::returned && out.exit_code == 0 &&
           out.report.stage == Stage::complete && SUCCEEDED(out.report.error);
}

int test() {
    const auto memory = run_child(mock_budget, 2s, {L"__mock-memory"});
    print("mock-memory", memory);
    const auto timeout = run_child(mock_budget, 500ms, {L"__mock-timeout"});
    print("mock-timeout", timeout);
    return memory.status == Outcome::Status::returned && memory.exit_code == 0 &&
           memory.report.stage == Stage::mock && memory.worker_reaped &&
           timeout.status == Outcome::Status::timeout && timeout.worker_reaped ? 0 : 2;
}

std::optional<CacheAction> archive_action(std::wstring_view name) {
    if (name == L"seed") return CacheAction::seed;
    if (name == L"plain") return CacheAction::replay_plain;
    if (name == L"blobs") return CacheAction::replay_blobs;
    if (name == L"library") return CacheAction::replay_library;
    return std::nullopt;
}
} // namespace

bool has_worker_limits(std::uint64_t limit) {
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION info{};
    return QueryInformationJobObject(nullptr, JobObjectExtendedLimitInformation, &info, sizeof(info), nullptr) &&
           (info.BasicLimitInformation.LimitFlags & memory_flags) == memory_flags &&
           info.ProcessMemoryLimit == limit && info.JobMemoryLimit == limit;
}

int wmain(int count, wchar_t** args) {
    const std::wstring_view action = count > 1 ? args[1] : L"";
    if (count == 2 && action == L"self-test") return test();
    if (count == 2 && action == L"__mock-memory") return mock(false);
    if (count == 2 && action == L"__mock-timeout") return mock(true);
    if (count == 11 && action == L"__library-worker") {
        const auto order = std::wstring_view(args[4]);
        if (order != L"library-first" && order != L"blob-first") return 2;
        const auto mode = order == L"library-first" ? CacheAction::library_first : CacheAction::blob_first;
        return emit(measure_library(args[2], args[3], args + 5, mode));
    }
    if (count == 12 && action == L"__archive-worker") {
        const auto mode = archive_action(args[4]);
        if (!mode || !args[5][0]) return 2;
        return emit(measure_library(args[2], args[3], args + 6, *mode, args[5]));
    }
    if (count == 12 && action == L"library-archive" && args[2][0] && args[5][0]) {
        if (!archive_action(args[4])) return 2;
        const auto r = run_child(smoke_budget, 3s,
            {L"__archive-worker", args[2], args[3], args[4], args[5],
             args[6], args[7], args[8], args[9], args[10], args[11]});
        print("library-archive", r);
        return successful(r) && r.report.library_pipelines == 6 ? 0 : 2;
    }
    if (count == 11 && action == L"library-smoke" && args[2][0]) {
        const auto order = std::wstring_view(args[4]);
        if (order != L"library-first" && order != L"blob-first") return 2;
        const auto r = run_child(smoke_budget, 3s,
            {L"__library-worker", args[2], args[3], args[4], args[5], args[6], args[7], args[8], args[9], args[10]});
        print(order == L"library-first" ? "library-first" : "blob-first", r);
        return successful(r) && r.report.library_pipelines == 6 ? 0 : 2;
    }
    const bool smoke = action == L"smoke" || action == L"__smoke-worker";
    if (count == 5 && (action == L"__worker" || action == L"__smoke-worker")) {
        return emit(measure(args[2], args[3], args[4], smoke));
    }
    if (count != 6 || (action != L"pair" && action != L"smoke") ||
        !args[2][0] || std::wstring_view(args[4]) == args[5]) {
        std::fputs("usage: portbridge-pso (pair|smoke) <adapter-name fragment> <root signature> <A.dxil> <B.dxil>\n"
                   "       portbridge-pso library-smoke <adapter> <root signature> (library-first|blob-first) <six DXIL paths>\n"
                   "       portbridge-pso library-archive <adapter> <root signature> (seed|plain|blobs|library) <scratch directory> <six DXIL paths>\n"
                   "       portbridge-pso self-test\n", stderr);
        return 2;
    }
    const auto budget = smoke ? smoke_budget : pair_budget;
    const auto deadline = smoke ? 3s : 10s;
    const auto worker = smoke ? L"__smoke-worker" : L"__worker";
    std::printf("{\"cache_mode\":\"%s\","
                "\"process_and_job_limit_bytes\":%llu,\"deadline_ms_per_worker\":%llu}\n",
                smoke ? "default_smoke_only" : "d3d_cache_disable_requested_driver_advisory",
                static_cast<unsigned long long>(budget.process),
                static_cast<unsigned long long>(std::chrono::milliseconds(deadline).count()));
    const auto first = run_child(budget, deadline, {worker, args[2], args[3], args[4]});
    print("A", first);
    if (!successful(first)) return 2;
    const auto second = run_child(budget, deadline, {worker, args[2], args[3], args[5]});
    print("B", second);
    if (!successful(second)) return 2;
    const Report& a = first.report;
    const Report& b = second.report;
    const bool matched = a.luid.LowPart == b.luid.LowPart && a.luid.HighPart == b.luid.HighPart &&
                         a.dxgi_driver_version == b.dxgi_driver_version &&
                         std::memcmp(a.root_sha, b.root_sha, sizeof(a.root_sha)) == 0 &&
                         std::memcmp(a.shader_sha, b.shader_sha, sizeof(a.shader_sha)) != 0;
    std::printf("{\"pair_matches\":%s}\n", matched ? "true" : "false");
    return matched ? 0 : 2;
}
