// SPDX-License-Identifier: MIT
#include "guard.h"

#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>

#include <array>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <string_view>

namespace {
using namespace std::chrono_literals;
constexpr std::uint64_t limit = 512 * guard::mib;
constexpr std::uint32_t sentinel = 0xeeeeeeeeu;
constexpr char adapter[] = "NVIDIA GeForce RTX 4070 Ti SUPER";
struct Fixture {
    const char* name;
    const std::uint32_t* code;
    std::size_t bytes;
    std::uint32_t lanes;
    std::uint32_t count;
    std::uint32_t marker;
};
#include "fixtures.inc"

struct Report {
    enum Stage {
        input, loader, instance_validation, adapter_selection, features, device, output_buffer,
        pipeline, record, submit_admission, submit, wait, readback, padding, complete
    };
    Stage stage = input;
    VkResult result = VK_ERROR_INITIALIZATION_FAILED;
    bool matched{};
    std::uint32_t driver{}, subgroup{}, validated{}, bad_lane{};
    std::uint32_t read_count{}, read_marker{};
    char diagnostic[320]{};
};

struct Validation {
    std::atomic<unsigned> seen{};
    char first[sizeof(Report::diagnostic)]{};
};

VKAPI_ATTR VkBool32 VKAPI_CALL diagnose(VkDebugUtilsMessageSeverityFlagBitsEXT,
                                      VkDebugUtilsMessageTypeFlagsEXT,
                                      const VkDebugUtilsMessengerCallbackDataEXT* data, void* context) {
    auto& errors = *static_cast<Validation*>(context);
    if (errors.seen.fetch_add(1) == 0) {
        std::snprintf(errors.first, sizeof(errors.first), "%s",
                      data->pMessageIdName ? data->pMessageIdName : "unnamed_validation_diagnostic");
    }
    return VK_FALSE;
}

struct Session {
    HMODULE library{};
    VkInstance instance{};
    VkDebugUtilsMessengerEXT debug{};
    VkDevice device{};
    VkBuffer buffer{};
    VkDeviceMemory memory{};
    void* mapping{};
    VkShaderModule shader{};
    VkPipelineLayout layout{};
    VkPipeline pipeline{};
    VkCommandPool pool{};
    VkFence fence{};
    bool pending{};
    PFN_vkGetInstanceProcAddr gipa{};
    PFN_vkGetDeviceProcAddr gdpa{};

    template<typename T> T load_i(const char* name) const {
        return reinterpret_cast<T>(gipa(instance, name));
    }
    template<typename T> T load_d(const char* name) const {
        return reinterpret_cast<T>(gdpa(device, name));
    }
    ~Session() {
        // A bounded wait failure is handled by exiting the guarded worker.
        if (pending) return;
#define CLEAN_D(handle, api) if (handle) load_d<PFN_##api>(#api)(device, handle, nullptr)
        CLEAN_D(fence, vkDestroyFence);
        CLEAN_D(pool, vkDestroyCommandPool);
        CLEAN_D(pipeline, vkDestroyPipeline);
        CLEAN_D(layout, vkDestroyPipelineLayout);
        CLEAN_D(shader, vkDestroyShaderModule);
        if (mapping) load_d<PFN_vkUnmapMemory>("vkUnmapMemory")(device, memory);
        CLEAN_D(buffer, vkDestroyBuffer);
        CLEAN_D(memory, vkFreeMemory);
#undef CLEAN_D
        if (device && gdpa) load_d<PFN_vkDestroyDevice>("vkDestroyDevice")(device, nullptr);
        if (debug) load_i<PFN_vkDestroyDebugUtilsMessengerEXT>("vkDestroyDebugUtilsMessengerEXT")(
            instance, debug, nullptr);
        if (instance) load_i<PFN_vkDestroyInstance>("vkDestroyInstance")(instance, nullptr);
        if (library) FreeLibrary(library);
    }
};

void measure(const Fixture& f, Report& out, Validation& diag) {
    Session v;
#define VK_CHECK(expression) do { \
        out.result = (expression); \
        if (out.result != VK_SUCCESS || diag.seen.load()) return; \
    } while (false)
#define INSTANCE(api) const auto api = v.load_i<PFN_##api>(#api); if (!api) return
#define DEVICE(api) const auto api = v.load_d<PFN_##api>(#api); if (!api) return
    out.stage = Report::loader;
    v.library = LoadLibraryExW(L"vulkan-1.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!v.library) return;
    const auto entry = GetProcAddress(v.library, "vkGetInstanceProcAddr");
    static_assert(sizeof(entry) == sizeof(v.gipa));
    std::memcpy(&v.gipa, &entry, sizeof(entry));
    if (!v.gipa) return;
    INSTANCE(vkEnumerateInstanceVersion);
    INSTANCE(vkCreateInstance);
    std::uint32_t version{};
    VK_CHECK(vkEnumerateInstanceVersion(&version));
    if (version < VK_API_VERSION_1_3) return;

    out.stage = Report::instance_validation;
    VkDebugUtilsMessengerCreateInfoEXT debug{VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT};
    debug.messageSeverity = VK_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT |
                            VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT;
    debug.messageType = VK_DEBUG_UTILS_MESSAGE_TYPE_GENERAL_BIT_EXT |
                        VK_DEBUG_UTILS_MESSAGE_TYPE_VALIDATION_BIT_EXT |
                        VK_DEBUG_UTILS_MESSAGE_TYPE_PERFORMANCE_BIT_EXT;
    debug.pfnUserCallback = diagnose;
    debug.pUserData = &diag;
    const VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO, nullptr,
                                "PortBridge finite shader readback", 0, nullptr, 0, VK_API_VERSION_1_3};
    const char* layer = "VK_LAYER_KHRONOS_validation";
    const char* extension = VK_EXT_DEBUG_UTILS_EXTENSION_NAME;
    VkInstanceCreateInfo inst{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    inst.pNext = &debug;
    inst.pApplicationInfo = &app;
    inst.enabledLayerCount = 1;
    inst.ppEnabledLayerNames = &layer;
    inst.enabledExtensionCount = 1;
    inst.ppEnabledExtensionNames = &extension;
    VK_CHECK(vkCreateInstance(&inst, nullptr, &v.instance));
    INSTANCE(vkCreateDebugUtilsMessengerEXT);
    VK_CHECK(vkCreateDebugUtilsMessengerEXT(v.instance, &debug, nullptr, &v.debug));

    out.stage = Report::adapter_selection;
    INSTANCE(vkEnumeratePhysicalDevices);
    INSTANCE(vkGetPhysicalDeviceProperties);
    INSTANCE(vkGetPhysicalDeviceProperties2);
    INSTANCE(vkGetPhysicalDeviceFeatures2);
    INSTANCE(vkGetPhysicalDeviceQueueFamilyProperties);
    INSTANCE(vkGetPhysicalDeviceMemoryProperties);
    INSTANCE(vkCreateDevice);
    v.gdpa = v.load_i<PFN_vkGetDeviceProcAddr>("vkGetDeviceProcAddr");
    if (!v.gdpa) return;
    std::array<VkPhysicalDevice, 16> devices{};
    std::uint32_t n{};
    VK_CHECK(vkEnumeratePhysicalDevices(v.instance, &n, nullptr));
    if (n == 0 || n > devices.size()) return;
    VK_CHECK(vkEnumeratePhysicalDevices(v.instance, &n, devices.data()));
    VkPhysicalDevice gpu{};
    for (std::uint32_t i = 0; i < n; ++i) {
        VkPhysicalDeviceProperties p{};
        vkGetPhysicalDeviceProperties(devices[i], &p);
        if (std::string_view(p.deviceName) != adapter) continue;
        if (gpu || p.vendorID != 0x10de || p.deviceType != VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU ||
            p.apiVersion < VK_API_VERSION_1_3) return;
        gpu = devices[i];
        out.driver = p.driverVersion;
    }
    if (!gpu) return;

    out.stage = Report::features;
    VkPhysicalDeviceFloatControlsProperties float_props{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FLOAT_CONTROLS_PROPERTIES};
    VkPhysicalDeviceSubgroupSizeControlProperties size_props{
        VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_SIZE_CONTROL_PROPERTIES, &float_props};
    VkPhysicalDeviceSubgroupProperties sg_props{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_PROPERTIES, &size_props};
    VkPhysicalDeviceProperties2 properties{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, &sg_props};
    vkGetPhysicalDeviceProperties2(gpu, &properties);
    std::array<std::uint32_t, 36> pc{};
    if (properties.properties.limits.maxPushConstantsSize < sizeof(pc) ||
        properties.properties.limits.maxComputeWorkGroupSize[0] < f.lanes ||
        properties.properties.limits.maxComputeWorkGroupInvocations < f.lanes ||
        !(sg_props.supportedStages & VK_SHADER_STAGE_COMPUTE_BIT) ||
        size_props.minSubgroupSize > 32 || size_props.maxSubgroupSize < 32 ||
        size_props.maxComputeWorkgroupSubgroups < f.lanes / 32 ||
        !(size_props.requiredSubgroupSizeStages & VK_SHADER_STAGE_COMPUTE_BIT) ||
        !float_props.shaderSignedZeroInfNanPreserveFloat32 || !float_props.shaderDenormPreserveFloat16)
        return;
    VkPhysicalDeviceVulkan13Features query13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES};
    VkPhysicalDeviceVulkan12Features query12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES, &query13};
    VkPhysicalDeviceFeatures2 query{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, &query12};
    vkGetPhysicalDeviceFeatures2(gpu, &query);
    if (!query.features.shaderInt64 || !query12.bufferDeviceAddress ||
        !query13.subgroupSizeControl || !query13.computeFullSubgroups || diag.seen.load()) return;
    out.subgroup = 32;

    out.stage = Report::device;
    std::array<VkQueueFamilyProperties, 32> families{};
    vkGetPhysicalDeviceQueueFamilyProperties(gpu, &n, nullptr);
    if (!n || n > families.size()) return;
    vkGetPhysicalDeviceQueueFamilyProperties(gpu, &n, families.data());
    std::uint32_t family{};
    while (family < n && (!families[family].queueCount || !(families[family].queueFlags & VK_QUEUE_COMPUTE_BIT)))
        ++family;
    if (family == n) return;
    const float priority = 1.0f;
    VkDeviceQueueCreateInfo q{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
    q.queueFamilyIndex = family;
    q.queueCount = 1;
    q.pQueuePriorities = &priority;
    VkPhysicalDeviceVulkan13Features enabled13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES};
    enabled13.subgroupSizeControl = VK_TRUE;
    enabled13.computeFullSubgroups = VK_TRUE;
    VkPhysicalDeviceVulkan12Features enabled12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES, &enabled13};
    enabled12.bufferDeviceAddress = VK_TRUE;
    VkPhysicalDeviceFeatures2 enabled{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, &enabled12};
    enabled.features.shaderInt64 = VK_TRUE;
    VkDeviceCreateInfo device{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
    device.pNext = &enabled;
    device.queueCreateInfoCount = 1;
    device.pQueueCreateInfos = &q;
    VK_CHECK(vkCreateDevice(gpu, &device, nullptr, &v.device));
    DEVICE(vkGetDeviceQueue);
    DEVICE(vkCreateBuffer);
    DEVICE(vkGetBufferMemoryRequirements);
    DEVICE(vkAllocateMemory);
    DEVICE(vkBindBufferMemory);
    DEVICE(vkMapMemory);
    DEVICE(vkGetBufferDeviceAddress);
    DEVICE(vkCreateShaderModule);
    DEVICE(vkCreatePipelineLayout);
    DEVICE(vkCreateComputePipelines);
    DEVICE(vkCreateCommandPool);
    DEVICE(vkAllocateCommandBuffers);
    DEVICE(vkBeginCommandBuffer);
    DEVICE(vkCmdBindPipeline);
    DEVICE(vkCmdPushConstants);
    DEVICE(vkCmdDispatch);
    DEVICE(vkCmdPipelineBarrier);
    DEVICE(vkEndCommandBuffer);
    DEVICE(vkCreateFence);
    DEVICE(vkQueueSubmit);
    DEVICE(vkWaitForFences);

    out.stage = Report::output_buffer;
    const VkDeviceSize data_size = 2 * f.lanes * sizeof(std::uint32_t);
    constexpr VkDeviceSize padding = 64;
    VkBufferCreateInfo buffer{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
    buffer.size = data_size + padding;
    buffer.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_SHADER_DEVICE_ADDRESS_BIT;
    VK_CHECK(vkCreateBuffer(v.device, &buffer, nullptr, &v.buffer));
    VkMemoryRequirements requirements{};
    vkGetBufferMemoryRequirements(v.device, v.buffer, &requirements);
    if (requirements.size > guard::mib || requirements.size < buffer.size) return;
    VkPhysicalDeviceMemoryProperties memory_props{};
    vkGetPhysicalDeviceMemoryProperties(gpu, &memory_props);
    constexpr auto visibility = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
    std::uint32_t mt{};
    for (; mt < memory_props.memoryTypeCount; ++mt)
        if ((requirements.memoryTypeBits & (1u << mt)) &&
            (memory_props.memoryTypes[mt].propertyFlags & visibility) == visibility)
            break;
    if (mt == memory_props.memoryTypeCount) return;
    const VkMemoryAllocateFlagsInfo flags{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_FLAGS_INFO, nullptr,
                                          VK_MEMORY_ALLOCATE_DEVICE_ADDRESS_BIT, 0};
    const VkMemoryAllocateInfo allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, &flags, requirements.size, mt};
    VK_CHECK(vkAllocateMemory(v.device, &allocation, nullptr, &v.memory));
    VK_CHECK(vkBindBufferMemory(v.device, v.buffer, v.memory, 0));
    VK_CHECK(vkMapMemory(v.device, v.memory, 0, buffer.size, 0, &v.mapping));
    std::memset(v.mapping, 0xee, static_cast<std::size_t>(buffer.size));
    const VkBufferDeviceAddressInfo address_info{VK_STRUCTURE_TYPE_BUFFER_DEVICE_ADDRESS_INFO, nullptr, v.buffer};
    const VkDeviceAddress address = vkGetBufferDeviceAddress(v.device, &address_info);
    if (!address || address % alignof(std::uint32_t) || diag.seen.load()) return;
    pc[2] = static_cast<std::uint32_t>(data_size);
    pc[3] = 0x31016facu;
    pc[32] = static_cast<std::uint32_t>(address);
    pc[33] = static_cast<std::uint32_t>(address >> 32);

    out.stage = Report::pipeline;
    VkShaderModuleCreateInfo shader{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
    shader.codeSize = f.bytes;
    shader.pCode = f.code;
    VK_CHECK(vkCreateShaderModule(v.device, &shader, nullptr, &v.shader));
    const VkPushConstantRange range{VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(pc)};
    VkPipelineLayoutCreateInfo layout{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    layout.pushConstantRangeCount = 1;
    layout.pPushConstantRanges = &range;
    VK_CHECK(vkCreatePipelineLayout(v.device, &layout, nullptr, &v.layout));
    const VkPipelineShaderStageRequiredSubgroupSizeCreateInfo required{
        VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_REQUIRED_SUBGROUP_SIZE_CREATE_INFO, nullptr, 32};
    VkComputePipelineCreateInfo pipe{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
    pipe.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    pipe.stage.pNext = &required;
    pipe.stage.flags = VK_PIPELINE_SHADER_STAGE_CREATE_REQUIRE_FULL_SUBGROUPS_BIT;
    pipe.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
    pipe.stage.module = v.shader;
    pipe.stage.pName = "main";
    pipe.layout = v.layout;
    VK_CHECK(vkCreateComputePipelines(v.device, VK_NULL_HANDLE, 1, &pipe, nullptr, &v.pipeline));

    out.stage = Report::record;
    VkCommandPoolCreateInfo pool{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
    pool.queueFamilyIndex = family;
    VK_CHECK(vkCreateCommandPool(v.device, &pool, nullptr, &v.pool));
    const VkCommandBufferAllocateInfo command_alloc{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, nullptr,
                                                     v.pool, VK_COMMAND_BUFFER_LEVEL_PRIMARY, 1};
    VkCommandBuffer cmd{};
    VK_CHECK(vkAllocateCommandBuffers(v.device, &command_alloc, &cmd));
    VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
    begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    VK_CHECK(vkBeginCommandBuffer(cmd, &begin));
    vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_COMPUTE, v.pipeline);
    vkCmdPushConstants(cmd, v.layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(pc), pc.data());
    vkCmdDispatch(cmd, 1, 1, 1);
    const VkMemoryBarrier readback{VK_STRUCTURE_TYPE_MEMORY_BARRIER, nullptr, VK_ACCESS_SHADER_WRITE_BIT,
                                   VK_ACCESS_HOST_READ_BIT};
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_HOST_BIT, 0, 1,
                         &readback, 0, nullptr, 0, nullptr);
    VK_CHECK(vkEndCommandBuffer(cmd));
    const VkFenceCreateInfo fence{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO, nullptr, 0};
    VK_CHECK(vkCreateFence(v.device, &fence, nullptr, &v.fence));
    VkQueue queue{};
    vkGetDeviceQueue(v.device, family, 0, &queue);
    if (!queue || diag.seen.load()) return;
    out.stage = Report::submit_admission;
    if (!guard::headroom(3072 * guard::mib, 4096 * guard::mib)) return;

    out.stage = Report::submit;
    VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};
    submit.commandBufferCount = 1;
    submit.pCommandBuffers = &cmd;
    out.result = vkQueueSubmit(queue, 1, &submit, v.fence);
    v.pending = out.result == VK_SUCCESS;
    if (!v.pending || diag.seen.load()) return;
    out.stage = Report::wait;
    out.result = vkWaitForFences(v.device, 1, &v.fence, VK_TRUE, 1'000'000'000u);
    if (out.result != VK_SUCCESS) return;
    v.pending = false;
    if (diag.seen.load()) return;

    out.stage = Report::readback;
    std::array<std::uint32_t, 144> words{};
    std::memcpy(words.data(), v.mapping, static_cast<std::size_t>(buffer.size));
    out.read_count = words[0];
    out.read_marker = words[1];
    for (std::uint32_t lane = 0; lane < f.lanes; ++lane) {
        if (words[2 * lane] != f.count || words[2 * lane + 1] != f.marker) {
            out.bad_lane = lane;
            out.read_count = words[2 * lane];
            out.read_marker = words[2 * lane + 1];
            return;
        }
    }
    if (std::any_of(words.begin() + 2 * f.lanes, words.begin() + buffer.size / sizeof(words[0]),
                    [](std::uint32_t value) { return value != sentinel; })) {
        out.stage = Report::padding;
        return;
    }
    out.stage = Report::complete;
    out.matched = true;
#undef DEVICE
#undef INSTANCE
#undef VK_CHECK
}

bool worker(const Fixture& fixture) {
    if (!guard::worker_limits(limit)) return false;
    Report report;
    Validation diagnostic;
    measure(fixture, report, diagnostic);
    report.validated = diagnostic.seen.load();
    std::memcpy(report.diagnostic, diagnostic.first, sizeof(report.diagnostic));
    DWORD written{};
    return WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), &report, sizeof(report), &written, nullptr) &&
           written == sizeof(report);
}

const char* stage_name(Report::Stage stage) {
    constexpr const char* stages[] = {
        "input", "loader", "instance_validation", "adapter", "features", "device", "output_buffer",
        "pipeline", "record", "submit_admission", "submit", "wait", "readback", "padding", "complete",
    };
    return static_cast<unsigned>(stage) < std::size(stages) ? stages[stage] : "invalid";
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc == 3 && std::wstring_view(argv[1]) == L"--worker" &&
        argv[2][0] >= L'0' && std::size_t(argv[2][0] - L'0') < std::size(fixtures) && argv[2][1] == L'\0')
        return worker(fixtures[argv[2][0] - L'0']) ? 0 : 2;
    if (argc != 2 || std::wstring_view(argv[1]) != L"--run-six") return 2;
    for (std::size_t i = 0; i < std::size(fixtures); ++i) {
        const auto& fixture = fixtures[i];
        const wchar_t index[] = {static_cast<wchar_t>(L'0' + i), L'\0'};
        const auto result = guard::run<Report>(limit, true, 3s, {L"--worker", index});
        const auto& report = result.report;
        std::printf(
            "%s guard=%s reaped=%d exit=%lu winerror=%lu peak=%zu job_peak=%zu stage=%s result=%d "
            "driver=%u subgroup=%u lanes=%u count=%u marker=%08x expected=%u/%08x diagnostics=%u first=%s bad_lane=%u\n",
            fixture.name, result.status, int(result.reaped), result.exit_code, result.win_error,
            result.process_peak, result.job_peak, stage_name(report.stage), int(report.result),
            report.driver, report.subgroup, fixture.lanes, report.read_count, report.read_marker,
            fixture.count, fixture.marker, report.validated, report.diagnostic, report.bad_lane);
        std::fflush(stdout);
        if (std::strcmp(result.status, "returned") || !result.reaped || result.exit_code ||
            !report.matched || report.validated)
            return 1;
    }
}
