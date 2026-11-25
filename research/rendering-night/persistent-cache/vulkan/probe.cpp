// SPDX-License-Identifier: MIT
#include "guard.h"
#include <bcrypt.h>

#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>

#include <array>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace {
using namespace std::chrono_literals;
using Clock = std::chrono::steady_clock;
using Hash = std::array<BYTE, 32>;
constexpr std::size_t recipes = 6;
constexpr std::size_t slots = recipes + 1;
constexpr std::size_t max_shader_bytes = 4 * 1024;
constexpr std::size_t max_cache_bytes = 1024 * 1024;
constexpr std::size_t cache_header_bytes = 32;
constexpr std::uint64_t smoke_limit = 512 * guard::mib;
constexpr std::uint64_t mock_limit = 64 * guard::mib;
constexpr char layout_identity[] = "cs-main/v1 set=0 binding=0 storage-buffer compute";

enum class Mode { seed, absent, combined, separate, invalid };
enum class Stage { guard, input, loader, instance, adapter, device, layout, cache, shader, pipeline,
                   snapshot, complete, mock };
enum class FeedbackPath { unsupported, core13, extension };

struct Report {
    Stage stage = Stage::guard;
    VkResult result = VK_ERROR_INITIALIZATION_FAILED;
    FeedbackPath feedback_path{};
    std::uint32_t vendor{}, device{}, driver{}, api{}, instance_api{};
    bool luid_valid{};
    std::array<BYTE, VK_UUID_SIZE> cache_uuid{}, device_uuid{}, driver_uuid{};
    std::array<BYTE, VK_LUID_SIZE> luid{};
    Hash bundle_sha256{};
    std::array<Hash, slots> cache_sha256{};
    std::array<std::uint32_t, slots> cache_bytes{};
    std::array<double, slots> cache_open_ms{};
    std::array<double, recipes> create_ms{};
    std::array<VkPipelineCreationFeedback, recipes> feedback{};
    double setup_ms{}, shader_ms{};
};

template<typename T, std::size_t N>
void copy_array(std::array<T, N>& out, const T (&in)[N]) {
    std::copy_n(in, N, out.begin());
}

double elapsed(Clock::time_point start) {
    return std::chrono::duration<double, std::milli>(Clock::now() - start).count();
}

bool sha256(std::vector<BYTE>& data, Hash& hash) {
    return BCryptHash(BCRYPT_SHA256_ALG_HANDLE, nullptr, 0, data.data(), static_cast<ULONG>(data.size()),
                      hash.data(), static_cast<ULONG>(hash.size())) >= 0;
}

std::vector<BYTE> read_bytes(const std::filesystem::path& path, std::size_t max) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    const auto length = file.tellg();
    if (length <= 0 || static_cast<std::uint64_t>(length) > max) return {};
    std::vector<BYTE> data(static_cast<std::size_t>(length));
    file.seekg(0);
    if (!file.read(reinterpret_cast<char*>(data.data()), length)) return {};
    return data;
}

bool write_new(const std::filesystem::path& path, const std::vector<BYTE>& data) {
    guard::Handle file(CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW,
                                  FILE_ATTRIBUTE_NORMAL, nullptr));
    DWORD count{};
    return file && WriteFile(file.value, data.data(), static_cast<DWORD>(data.size()), &count, nullptr) &&
           count == data.size();
}

std::uint32_t word(const std::vector<BYTE>& data, std::size_t offset) {
    // Windows x64 and the Vulkan pipeline cache header both use little-endian values.
    std::uint32_t value;
    std::memcpy(&value, data.data() + offset, sizeof(value));
    return value;
}

bool matches_header(const std::vector<BYTE>& data, const Report& report) {
    // https://docs.vulkan.org/refpages/latest/refpages/source/VkPipelineCacheHeaderVersionOne.html
    return data.size() >= cache_header_bytes && word(data, 0) == cache_header_bytes &&
           word(data, 4) == VK_PIPELINE_CACHE_HEADER_VERSION_ONE &&
           word(data, 8) == report.vendor && word(data, 12) == report.device &&
           std::equal(report.cache_uuid.begin(), report.cache_uuid.end(), data.begin() + 16);
}

std::filesystem::path cache_path(const std::filesystem::path& directory, std::size_t slot) {
    if (slot == 0) return directory / L"combined.vkc";
    return directory / (std::to_wstring(slot - 1) + L".vkc");
}

std::string utf8(const wchar_t* value) {
    const auto n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value, -1, nullptr, 0, nullptr, nullptr);
    if (n <= 1) return {};
    std::string out(static_cast<std::size_t>(n), '\0');
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value, -1, out.data(), n, nullptr, nullptr))
        return {};
    out.pop_back();
    return out;
}

struct Vulkan {
    HMODULE library{};
    VkInstance instance{};
    VkDevice device{};
    VkDescriptorSetLayout descriptors{};
    VkPipelineLayout layout{};
    std::array<VkPipelineCache, slots> caches{};
    std::array<VkShaderModule, recipes> modules{};
    std::array<VkPipeline, recipes> pipelines{};

    PFN_vkGetInstanceProcAddr instance_proc{};
    PFN_vkGetDeviceProcAddr device_proc{};
    PFN_vkDestroyInstance destroy_instance{};
    PFN_vkDestroyDevice destroy_device{};
    PFN_vkDestroyDescriptorSetLayout destroy_descriptors{};
    PFN_vkDestroyPipelineLayout destroy_layout{};
    PFN_vkDestroyPipelineCache destroy_cache{};
    PFN_vkDestroyShaderModule destroy_shader{};
    PFN_vkDestroyPipeline destroy_pipeline{};
    PFN_vkGetPipelineCacheData get_cache_data{};
    PFN_vkCreatePipelineCache create_cache{};
    PFN_vkCreateComputePipelines create_pipeline{};

    template<typename T> T from_instance(const char* name) {
        return reinterpret_cast<T>(instance_proc(instance, name));
    }
    template<typename T> T from_device(const char* name) {
        return reinterpret_cast<T>(device_proc(device, name));
    }

    ~Vulkan() {
        for (auto pipeline : pipelines) if (pipeline) destroy_pipeline(device, pipeline, nullptr);
        for (auto module : modules) if (module) destroy_shader(device, module, nullptr);
        for (auto cache : caches) if (cache) destroy_cache(device, cache, nullptr);
        if (layout) destroy_layout(device, layout, nullptr);
        if (descriptors) destroy_descriptors(device, descriptors, nullptr);
        if (device && destroy_device) destroy_device(device, nullptr);
        if (instance && destroy_instance) destroy_instance(instance, nullptr);
        if (library) FreeLibrary(library);
    }
};

bool start_vulkan(Vulkan& vk, Report& report, const std::string& selector) {
    report.stage = Stage::loader;
    vk.library = LoadLibraryExW(L"vulkan-1.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!vk.library) return false;
    const auto entry = GetProcAddress(vk.library, "vkGetInstanceProcAddr");
    static_assert(sizeof(entry) == sizeof(vk.instance_proc));
    std::memcpy(&vk.instance_proc, &entry, sizeof(entry));
    if (!vk.instance_proc) return false;
    const auto enumerate_versions = vk.from_instance<PFN_vkEnumerateInstanceVersion>("vkEnumerateInstanceVersion");
    const auto create_instance = vk.from_instance<PFN_vkCreateInstance>("vkCreateInstance");
    std::uint32_t loader_version{};
    if (!enumerate_versions || !create_instance || enumerate_versions(&loader_version) != VK_SUCCESS ||
        loader_version < VK_API_VERSION_1_1) return false;
    report.instance_api = std::min(loader_version, VK_API_VERSION_1_3);

    report.stage = Stage::instance;
    VkApplicationInfo app{};
    app.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    app.pApplicationName = "PortBridge synthetic cache replay";
    app.apiVersion = report.instance_api;
    VkInstanceCreateInfo instance_info{};
    instance_info.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    instance_info.pApplicationInfo = &app;
    report.result = create_instance(&instance_info, nullptr, &vk.instance);
    if (report.result != VK_SUCCESS) return false;
    vk.destroy_instance = vk.from_instance<PFN_vkDestroyInstance>("vkDestroyInstance");
    vk.device_proc = vk.from_instance<PFN_vkGetDeviceProcAddr>("vkGetDeviceProcAddr");
    const auto enumerate_devices = vk.from_instance<PFN_vkEnumeratePhysicalDevices>("vkEnumeratePhysicalDevices");
    const auto get_properties = vk.from_instance<PFN_vkGetPhysicalDeviceProperties>("vkGetPhysicalDeviceProperties");
    const auto get_properties2 = vk.from_instance<PFN_vkGetPhysicalDeviceProperties2>("vkGetPhysicalDeviceProperties2");
    const auto get_queues = vk.from_instance<PFN_vkGetPhysicalDeviceQueueFamilyProperties>(
        "vkGetPhysicalDeviceQueueFamilyProperties");
    const auto get_extensions = vk.from_instance<PFN_vkEnumerateDeviceExtensionProperties>(
        "vkEnumerateDeviceExtensionProperties");
    const auto create_device = vk.from_instance<PFN_vkCreateDevice>("vkCreateDevice");
    if (!vk.destroy_instance || !vk.device_proc || !enumerate_devices || !get_properties ||
        !get_properties2 || !get_queues || !get_extensions || !create_device) return false;

    report.stage = Stage::adapter;
    std::uint32_t count{};
    if (enumerate_devices(vk.instance, &count, nullptr) != VK_SUCCESS || count == 0 || count > 64) return false;
    std::vector<VkPhysicalDevice> physical_devices(count);
    if (enumerate_devices(vk.instance, &count, physical_devices.data()) != VK_SUCCESS) return false;
    VkPhysicalDevice selected{};
    for (std::uint32_t i = 0; i != count; ++i) {
        VkPhysicalDeviceProperties p{};
        get_properties(physical_devices[i], &p);
        if (selector != p.deviceName ||
            (p.deviceType != VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU &&
             p.deviceType != VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU)) continue;
        if (selected || p.apiVersion < VK_API_VERSION_1_1) return false;
        VkPhysicalDeviceIDProperties identification{};
        identification.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_ID_PROPERTIES;
        VkPhysicalDeviceProperties2 properties{};
        properties.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2;
        properties.pNext = &identification;
        get_properties2(physical_devices[i], &properties);
        selected = physical_devices[i];
        report.vendor = p.vendorID;
        report.device = p.deviceID;
        report.driver = p.driverVersion;
        report.api = p.apiVersion;
        copy_array(report.cache_uuid, p.pipelineCacheUUID);
        copy_array(report.device_uuid, identification.deviceUUID);
        copy_array(report.driver_uuid, identification.driverUUID);
        report.luid_valid = identification.deviceLUIDValid == VK_TRUE;
        if (report.luid_valid) copy_array(report.luid, identification.deviceLUID);
    }
    if (!selected) return false;
    get_queues(selected, &count, nullptr);
    if (!count || count > 64) return false;
    std::vector<VkQueueFamilyProperties> queues(count);
    get_queues(selected, &count, queues.data());
    std::uint32_t queue = 0;
    while (queue < count && (!(queues[queue].queueFlags & VK_QUEUE_COMPUTE_BIT) || !queues[queue].queueCount))
        ++queue;
    if (queue == count) return false;

    const char* feedback_extension = VK_EXT_PIPELINE_CREATION_FEEDBACK_EXTENSION_NAME;
    // https://docs.vulkan.org/refpages/latest/refpages/source/VK_EXT_pipeline_creation_feedback.html
    if (report.instance_api >= VK_API_VERSION_1_3 && report.api >= VK_API_VERSION_1_3) {
        report.feedback_path = FeedbackPath::core13;
    } else {
        if (get_extensions(selected, nullptr, &count, nullptr) != VK_SUCCESS || count > 1024) return false;
        std::vector<VkExtensionProperties> extensions(count);
        if (get_extensions(selected, nullptr, &count, extensions.data()) != VK_SUCCESS) return false;
        for (std::uint32_t i = 0; i != count; ++i) {
            if (std::strcmp(extensions[i].extensionName, feedback_extension) == 0)
                report.feedback_path = FeedbackPath::extension;
        }
    }

    report.stage = Stage::device;
    const float priority = 1.f;
    VkDeviceQueueCreateInfo queue_info{};
    queue_info.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
    queue_info.queueFamilyIndex = queue;
    queue_info.queueCount = 1;
    queue_info.pQueuePriorities = &priority;
    VkDeviceCreateInfo device_info{};
    device_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
    device_info.queueCreateInfoCount = 1;
    device_info.pQueueCreateInfos = &queue_info;
    if (report.feedback_path == FeedbackPath::extension) {
        device_info.enabledExtensionCount = 1;
        device_info.ppEnabledExtensionNames = &feedback_extension;
    }
    report.result = create_device(selected, &device_info, nullptr, &vk.device);
    if (report.result != VK_SUCCESS) return false;

    vk.destroy_device = vk.from_device<PFN_vkDestroyDevice>("vkDestroyDevice");
    vk.destroy_descriptors = vk.from_device<PFN_vkDestroyDescriptorSetLayout>("vkDestroyDescriptorSetLayout");
    vk.destroy_layout = vk.from_device<PFN_vkDestroyPipelineLayout>("vkDestroyPipelineLayout");
    vk.destroy_shader = vk.from_device<PFN_vkDestroyShaderModule>("vkDestroyShaderModule");
    vk.destroy_pipeline = vk.from_device<PFN_vkDestroyPipeline>("vkDestroyPipeline");
    vk.destroy_cache = vk.from_device<PFN_vkDestroyPipelineCache>("vkDestroyPipelineCache");
    vk.get_cache_data = vk.from_device<PFN_vkGetPipelineCacheData>("vkGetPipelineCacheData");
    vk.create_cache = vk.from_device<PFN_vkCreatePipelineCache>("vkCreatePipelineCache");
    vk.create_pipeline = vk.from_device<PFN_vkCreateComputePipelines>("vkCreateComputePipelines");
    return vk.destroy_device && vk.destroy_descriptors && vk.destroy_layout && vk.destroy_shader &&
           vk.destroy_pipeline && vk.destroy_cache && vk.get_cache_data && vk.create_cache && vk.create_pipeline;
}

bool create_layout(Vulkan& vk, Report& report) {
    report.stage = Stage::layout;
    const auto create_descriptors = vk.from_device<PFN_vkCreateDescriptorSetLayout>("vkCreateDescriptorSetLayout");
    const auto create_pipeline_layout = vk.from_device<PFN_vkCreatePipelineLayout>("vkCreatePipelineLayout");
    if (!create_descriptors || !create_pipeline_layout) return false;
    VkDescriptorSetLayoutBinding binding{};
    binding.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    binding.descriptorCount = 1;
    binding.stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
    VkDescriptorSetLayoutCreateInfo descriptors{};
    descriptors.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
    descriptors.bindingCount = 1;
    descriptors.pBindings = &binding;
    report.result = create_descriptors(vk.device, &descriptors, nullptr, &vk.descriptors);
    if (report.result != VK_SUCCESS) return false;
    VkPipelineLayoutCreateInfo layout{};
    layout.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO;
    layout.setLayoutCount = 1;
    layout.pSetLayouts = &vk.descriptors;
    report.result = create_pipeline_layout(vk.device, &layout, nullptr, &vk.layout);
    return report.result == VK_SUCCESS;
}

using ShaderWords = std::array<std::vector<std::uint32_t>, recipes>;

bool load_shaders(ShaderWords& words, Report& report, const std::filesystem::path& directory) {
    // Identity is the ASCII layout string with NUL, then each little-endian byte length and module.
    std::vector<BYTE> bundle(std::begin(layout_identity), std::end(layout_identity));
    for (std::size_t i = 0; i != recipes; ++i) {
        const auto shader = read_bytes(directory / (std::to_wstring(i) + L".spv"), max_shader_bytes);
        if (shader.size() < 20 || shader.size() % 4 || word(shader, 0) != 0x07230203) return false;
        const auto size = static_cast<std::uint32_t>(shader.size());
        for (int shift = 0; shift != 32; shift += 8) bundle.push_back(static_cast<BYTE>(size >> shift));
        bundle.insert(bundle.end(), shader.begin(), shader.end());
        words[i].resize(shader.size() / 4);
        std::memcpy(words[i].data(), shader.data(), shader.size());
    }
    return sha256(bundle, report.bundle_sha256);
}

bool create_modules(const ShaderWords& words, Vulkan& vk, Report& report) {
    report.stage = Stage::shader;
    const auto create_shader = vk.from_device<PFN_vkCreateShaderModule>("vkCreateShaderModule");
    if (!create_shader) return false;
    const auto start = Clock::now();
    for (std::size_t i = 0; i != recipes; ++i) {
        VkShaderModuleCreateInfo module{};
        module.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO;
        module.codeSize = words[i].size() * sizeof(std::uint32_t);
        module.pCode = words[i].data();
        report.result = create_shader(vk.device, &module, nullptr, &vk.modules[i]);
        if (report.result != VK_SUCCESS) return false;
    }
    report.shader_ms = elapsed(start);
    return true;
}

bool cache_data(std::vector<BYTE>& bytes, Report& report, std::size_t slot) {
    if (!matches_header(bytes, report) || !sha256(bytes, report.cache_sha256[slot])) return false;
    report.cache_bytes[slot] = static_cast<std::uint32_t>(bytes.size());
    return true;
}

bool create_cache(Vulkan& vk, Report& report, std::size_t slot, const std::filesystem::path& directory,
                  bool seed) {
    std::vector<BYTE> bytes;
    if (!seed) {
        bytes = read_bytes(cache_path(directory, slot), max_cache_bytes);
        if (!cache_data(bytes, report, slot)) return false;
    }
    VkPipelineCacheCreateInfo info{};
    info.sType = VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO;
    info.initialDataSize = bytes.size();
    info.pInitialData = seed ? nullptr : bytes.data();
    const auto start = Clock::now();
    report.result = vk.create_cache(vk.device, &info, nullptr, &vk.caches[slot]);
    report.cache_open_ms[slot] = elapsed(start);
    return report.result == VK_SUCCESS;
}

bool snapshots(Vulkan& vk, Report& report, const std::filesystem::path& directory) {
    report.stage = Stage::snapshot;
    const auto merge = vk.from_device<PFN_vkMergePipelineCaches>("vkMergePipelineCaches");
    if (!merge) return false;
    // Merge six caches populated by the same six measured PSO calls.
    report.result = merge(vk.device, vk.caches[0], recipes, vk.caches.data() + 1);
    if (report.result != VK_SUCCESS) return false;
    for (std::size_t i = 0; i != slots; ++i) {
        std::size_t size{};
        report.result = vk.get_cache_data(vk.device, vk.caches[i], &size, nullptr);
        if (report.result != VK_SUCCESS || size < cache_header_bytes || size > max_cache_bytes) return false;
        std::vector<BYTE> bytes(size);
        report.result = vk.get_cache_data(vk.device, vk.caches[i], &size, bytes.data());
        if (report.result != VK_SUCCESS || size > bytes.size()) return false;
        bytes.resize(size);
        if (!cache_data(bytes, report, i) || !write_new(cache_path(directory, i), bytes)) return false;
    }
    return true;
}

Report measure(Mode mode, const wchar_t* adapter, const wchar_t* directory) {
    Report report{};
    if (!guard::worker_limits(smoke_limit)) return report;
    report.stage = Stage::input;
    const std::filesystem::path dir(directory);
    ShaderWords words;
    const auto selector = utf8(adapter);
    if (mode == Mode::invalid || selector.empty() || !load_shaders(words, report, dir)) return report;
    const auto start = Clock::now();
    Vulkan vk;
    if (!start_vulkan(vk, report, selector) || !create_layout(vk, report)) return report;
    report.setup_ms = elapsed(start);
    if (!create_modules(words, vk, report)) return report;

    report.stage = Stage::cache;
    const bool seed = mode == Mode::seed;
    if ((seed || mode == Mode::combined) && !create_cache(vk, report, 0, dir, seed)) return report;
    if (seed || mode == Mode::separate) {
        for (std::size_t i = 1; i != slots; ++i)
            if (!create_cache(vk, report, i, dir, seed)) return report;
    }

    report.stage = Stage::pipeline;
    for (std::size_t i = 0; i != recipes; ++i) {
        VkPipelineCreationFeedbackCreateInfo feedback{};
        feedback.sType = VK_STRUCTURE_TYPE_PIPELINE_CREATION_FEEDBACK_CREATE_INFO;
        feedback.pPipelineCreationFeedback = &report.feedback[i];
        VkComputePipelineCreateInfo pipeline{};
        pipeline.sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO;
        if (report.feedback_path != FeedbackPath::unsupported) pipeline.pNext = &feedback;
        pipeline.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        pipeline.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
        pipeline.stage.module = vk.modules[i];
        pipeline.stage.pName = "main";
        pipeline.layout = vk.layout;
        pipeline.basePipelineIndex = -1;
        const auto cache = mode == Mode::absent ? VK_NULL_HANDLE : vk.caches[mode == Mode::combined ? 0 : i + 1];
        const auto begin = Clock::now();
        report.result = vk.create_pipeline(vk.device, cache, 1, &pipeline, nullptr, &vk.pipelines[i]);
        report.create_ms[i] = elapsed(begin);
        if (report.result != VK_SUCCESS || !vk.pipelines[i]) return report;
    }
    if (seed && !snapshots(vk, report, dir)) return report;
    report.stage = Stage::complete;
    return report;
}

template<std::size_t N>
void print_hex(const std::array<BYTE, N>& bytes) {
    std::putchar('"');
    for (auto byte : bytes) std::printf("%02x", static_cast<unsigned>(byte));
    std::putchar('"');
}

const char* boolean(bool value) { return value ? "true" : "false"; }

void print(const guard::Outcome<Report>& out) {
    const auto& report = out.report;
    std::printf("{\"status\":\"%s\",\"exit_code\":%lu,\"win_error\":%lu,\"reaped\":%s,"
                "\"process_peak\":%zu,\"job_peak\":%zu,\"stage\":%d,\"vk_result\":%d,"
                "\"vendor\":%u,\"device\":%u,\"driver\":%u,\"api\":%u,\"instance_api\":%u,"
                "\"luid_valid\":%s,\"feedback_path\":%d,\"cache_uuid\":",
                out.status, out.exit_code, out.win_error, boolean(out.reaped),
                out.process_peak, out.job_peak, static_cast<int>(report.stage), static_cast<int>(report.result),
                report.vendor, report.device, report.driver, report.api, report.instance_api,
                boolean(report.luid_valid), static_cast<int>(report.feedback_path));
    print_hex(report.cache_uuid);
    std::printf(",\"driver_uuid\":");
    print_hex(report.driver_uuid);
    std::printf(",\"device_uuid\":");
    print_hex(report.device_uuid);
    std::printf(",\"luid\":");
    print_hex(report.luid);
    std::printf(",\"bundle_sha256\":");
    print_hex(report.bundle_sha256);
    std::printf(",\"setup_ms\":%.6f,\"shader_ms\":%.6f,\"cache\":[", report.setup_ms, report.shader_ms);
    for (std::size_t i = 0; i != slots; ++i) {
        std::printf("%s{\"bytes\":%u,\"open_ms\":%.6f,\"sha256\":",
                    i ? "," : "", report.cache_bytes[i], report.cache_open_ms[i]);
        print_hex(report.cache_sha256[i]);
        std::putchar('}');
    }
    std::printf("],\"pipeline\":[");
    for (std::size_t i = 0; i != recipes; ++i) {
        const auto& feedback = report.feedback[i];
        const bool valid = (feedback.flags & VK_PIPELINE_CREATION_FEEDBACK_VALID_BIT) != 0;
        const auto hit = valid ? boolean((feedback.flags & VK_PIPELINE_CREATION_FEEDBACK_APPLICATION_PIPELINE_CACHE_HIT_BIT) != 0)
                               : "null";
        std::printf("%s{\"ms\":%.6f,\"feedback_valid\":%s,\"app_hit\":%s,\"driver_ns\":",
                    i ? "," : "", report.create_ms[i], boolean(valid), hit);
        if (valid) std::printf("%llu", static_cast<unsigned long long>(feedback.duration));
        else std::printf("null");
        std::putchar('}');
    }
    std::printf("]}\n");
}

Mode parse(std::wstring_view arg) {
    if (arg == L"seed") return Mode::seed;
    if (arg == L"absent") return Mode::absent;
    if (arg == L"combined") return Mode::combined;
    if (arg == L"separate") return Mode::separate;
    return Mode::invalid;
}

int emit(const Report& report, Stage expected) {
    DWORD written{};
    const auto output = GetStdHandle(STD_OUTPUT_HANDLE);
    if (!WriteFile(output, &report, sizeof(report), &written, nullptr) || written != sizeof(report)) return 3;
    return report.stage == expected ? 0 : 1;
}

int mock(std::wstring_view action) {
    Report report{};
    if (!guard::worker_limits(mock_limit)) return emit(report, Stage::mock);
    if (action == L"__mock_timeout") Sleep(INFINITE);
    void* allowed = VirtualAlloc(nullptr, guard::mib, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    void* denied = VirtualAlloc(nullptr, mock_limit + guard::mib, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (allowed) VirtualFree(allowed, 0, MEM_RELEASE);
    if (denied) VirtualFree(denied, 0, MEM_RELEASE);
    if (allowed && !denied) {
        report.stage = Stage::mock;
        report.result = VK_SUCCESS;
    }
    return emit(report, Stage::mock);
}
}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc == 2) {
        const std::wstring_view action(argv[1]);
        if (action == L"__mock_memory" || action == L"__mock_timeout") return mock(action);
        if (action == L"self-test") {
            const auto memory = guard::run<Report>(mock_limit, false, 2s, {L"__mock_memory"});
            const auto timeout = guard::run<Report>(mock_limit, false, 500ms, {L"__mock_timeout"});
            print(memory);
            print(timeout);
            return memory.report.stage == Stage::mock && memory.exit_code == 0 && memory.reaped &&
                   std::string_view(timeout.status) == "timeout" && timeout.reaped ? 0 : 1;
        }
    }
    if (argc == 5 && std::wstring_view(argv[1]) == L"__worker")
        return emit(measure(parse(argv[2]), argv[3], argv[4]), Stage::complete);
    if (argc == 4 && parse(argv[1]) != Mode::invalid) {
        const auto result = guard::run<Report>(smoke_limit, true, 3s, {L"__worker", argv[1], argv[2], argv[3]});
        print(result);
        return result.report.stage == Stage::complete && result.exit_code == 0 && result.reaped ? 0 : 1;
    }
    std::fprintf(stderr, "Usage: probe.exe seed|absent|combined|separate ADAPTER CASE_DIRECTORY\n");
    return 2;
}
