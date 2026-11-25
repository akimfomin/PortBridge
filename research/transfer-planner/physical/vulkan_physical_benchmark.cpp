// SPDX-License-Identifier: MIT
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#define VK_NO_PROTOTYPES
#include <windows.h>
#include <vulkan/vulkan.h>

#include "planner.hpp"
#include "physical_trace.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

constexpr std::uint32_t extent = 2048;
constexpr std::size_t unit_bytes = 256;
constexpr std::size_t words_per_unit = unit_bytes / sizeof(std::uint32_t);
constexpr VkDeviceSize size_bytes = extent * unit_bytes;
constexpr transfer::Range protected_gap{960, 1088};
constexpr int warms = 4;
constexpr int trials = 24;
constexpr std::uint32_t compute_group_size = 64;
constexpr std::uint32_t arm_count = 3;

struct Options {
    bool physical = false;
    std::filesystem::path shader;
    std::filesystem::path trace;
    std::uint32_t frame_limit = 16;
    std::uint32_t samples = 3;
    std::uint32_t cap_bytes = 0;
    transfer::Cost cost{14, 1};
};

std::uint32_t parse_unsigned(std::string_view argument) {
    std::uint32_t value = 0;
    const auto [end, error] = std::from_chars(argument.data(), argument.data() + argument.size(), value);
    if (error != std::errc{} || end != argument.data() + argument.size()) {
        throw std::invalid_argument("expected an unsigned numeric option");
    }
    return value;
}

Options options(int argc, char** argv) {
    Options result;
    bool adapter_selected = false;
    for (int i = 1; i < argc; ++i) {
        const std::string_view argument = argv[i];
        if (argument == "--software" || argument == "--rtx4070tisuper" || argument == "--adapter") {
            if (adapter_selected) {
                throw std::invalid_argument("select exactly one Vulkan adapter mode");
            }
            adapter_selected = true;
            if (argument == "--adapter") {
                if (++i == argc || std::string_view(argv[i]) != "rtx4070tisuper") {
                    throw std::invalid_argument("the only Vulkan hardware selector is rtx4070tisuper");
                }
                result.physical = true;
            } else {
                result.physical = argument == "--rtx4070tisuper";
            }
        } else if (argument == "--shader" && result.shader.empty() && i + 1 < argc) {
            result.shader = argv[++i];
        } else if (argument == "--trace" && result.trace.empty() && i + 1 < argc) {
            result.trace = argv[++i];
        } else if (argument == "--frame-limit" && i + 1 < argc) {
            result.frame_limit = parse_unsigned(argv[++i]);
        } else if (argument == "--samples" && i + 1 < argc) {
            result.samples = parse_unsigned(argv[++i]);
        } else if (argument == "--cap-bytes" && i + 1 < argc) {
            result.cap_bytes = parse_unsigned(argv[++i]);
        } else if (argument == "--setup" && i + 1 < argc) {
            result.cost.setup = parse_unsigned(argv[++i]);
        } else if (argument == "--unit-cost" && i + 1 < argc) {
            result.cost.unit = parse_unsigned(argv[++i]);
        } else {
            throw std::invalid_argument(
                "usage: vulkan_benchmark [--software | --adapter rtx4070tisuper]"
                " [--trace PATH --shader PATH --frame-limit N --samples N --cap-bytes N"
                " --setup N --unit-cost N]");
        }
    }
    if (result.samples == 0 || result.frame_limit == 0) {
        throw std::invalid_argument("trace sample and frame limits must be positive");
    }
    if (result.physical && (result.trace.empty() || result.shader.empty())) {
        throw std::invalid_argument("physical benchmark requires --trace and --shader");
    }
    if (!result.trace.empty() && result.shader.empty()) {
        throw std::invalid_argument("full-chain trace benchmarking requires --shader");
    }
    return result;
}

void check(VkResult result, const char* operation) {
    if (result != VK_SUCCESS) {
        throw std::runtime_error(std::string(operation) + " failed with VkResult " + std::to_string(result));
    }
}

struct Buffer {
    VkBuffer buffer = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    void* mapped = nullptr;
    VkMemoryPropertyFlags properties = 0;
    std::uint32_t heap = 0;
};

struct DeviceTimes {
    double staging_ns;
    double recording_ns;
    double submit_fence_ns;
};

using Clock = std::chrono::steady_clock;

double elapsed_ns(Clock::time_point begin, Clock::time_point end) {
    return std::chrono::duration<double, std::nano>(end - begin).count();
}

#define DEVICE_FUNCTIONS(X) \
    X(DestroyDevice) X(GetDeviceQueue) X(DeviceWaitIdle) \
    X(CreateBuffer) X(DestroyBuffer) X(GetBufferMemoryRequirements) \
    X(AllocateMemory) X(FreeMemory) X(BindBufferMemory) X(MapMemory) X(UnmapMemory) \
    X(CreateCommandPool) X(DestroyCommandPool) X(AllocateCommandBuffers) X(ResetCommandBuffer) \
    X(BeginCommandBuffer) X(EndCommandBuffer) X(CmdPipelineBarrier) X(CmdCopyBuffer) \
    X(CreateFence) X(DestroyFence) X(ResetFences) X(QueueSubmit) X(WaitForFences) \
    X(CreateShaderModule) X(DestroyShaderModule) X(CreateDescriptorSetLayout) X(DestroyDescriptorSetLayout) \
    X(CreateDescriptorPool) X(DestroyDescriptorPool) X(AllocateDescriptorSets) X(UpdateDescriptorSets) \
    X(CreatePipelineLayout) X(DestroyPipelineLayout) X(CreateComputePipelines) X(DestroyPipeline) \
    X(CmdBindPipeline) X(CmdBindDescriptorSets) X(CmdPushConstants) X(CmdDispatch)

class Vulkan {
public:
    Vulkan() = default;
    Vulkan(const Vulkan&) = delete;
    Vulkan& operator=(const Vulkan&) = delete;
    ~Vulkan() {
        if (device != VK_NULL_HANDLE && DestroyDevice) {
            if (DeviceWaitIdle) {
                DeviceWaitIdle(device);
            }
            if (pipeline != VK_NULL_HANDLE) {
                DestroyPipeline(device, pipeline, nullptr);
            }
            if (pipeline_layout != VK_NULL_HANDLE) {
                DestroyPipelineLayout(device, pipeline_layout, nullptr);
            }
            if (descriptor_pool != VK_NULL_HANDLE) {
                DestroyDescriptorPool(device, descriptor_pool, nullptr);
            }
            if (descriptor_layout != VK_NULL_HANDLE) {
                DestroyDescriptorSetLayout(device, descriptor_layout, nullptr);
            }
            if (shader_module != VK_NULL_HANDLE) {
                DestroyShaderModule(device, shader_module, nullptr);
            }
            release(readback);
            release(consumed);
            release(upload);
            for (auto& buffer : targets) {
                release(buffer);
            }
            if (fence != VK_NULL_HANDLE) {
                DestroyFence(device, fence, nullptr);
            }
            if (pool != VK_NULL_HANDLE) {
                DestroyCommandPool(device, pool, nullptr);
            }
            DestroyDevice(device, nullptr);
        }
        if (instance != VK_NULL_HANDLE && DestroyInstance) {
            DestroyInstance(instance, nullptr);
        }
        if (loader) {
            FreeLibrary(loader);
        }
    }

    void initialize(const Options& configuration, VkDeviceSize capacity = size_bytes) {
        if (capacity == 0 || capacity % sizeof(std::uint32_t) != 0
            || capacity / sizeof(std::uint32_t) > std::numeric_limits<std::uint32_t>::max()) {
            throw std::invalid_argument("unsupported Vulkan benchmark buffer size");
        }
        buffer_size = capacity;
        has_consumer = !configuration.shader.empty();
        // A default invocation remains CPU-only and keeps the explicit ICD gate.
        if (!configuration.physical && GetEnvironmentVariableW(L"VK_DRIVER_FILES", nullptr, 0) == 0) {
            throw std::runtime_error("set VK_DRIVER_FILES to a software ICD manifest for this process");
        }
        loader = LoadLibraryExW(L"vulkan-1.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
        if (!loader) {
            throw std::runtime_error("cannot load the system Vulkan loader");
        }
        instance_proc = reinterpret_cast<PFN_vkGetInstanceProcAddr>(GetProcAddress(loader, "vkGetInstanceProcAddr"));
        if (!instance_proc) {
            throw std::runtime_error("Vulkan loader does not export vkGetInstanceProcAddr");
        }

        VkApplicationInfo app{};
        app.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
        app.pApplicationName = "PortBridge transfer planner replay";
        app.apiVersion = VK_API_VERSION_1_0;
        VkInstanceCreateInfo instance_info{};
        instance_info.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
        instance_info.pApplicationInfo = &app;
        check(instance_function<PFN_vkCreateInstance>("vkCreateInstance")(&instance_info, nullptr, &instance),
              "vkCreateInstance");
        DestroyInstance = instance_function<PFN_vkDestroyInstance>("vkDestroyInstance");
        const auto enumerate = instance_function<PFN_vkEnumeratePhysicalDevices>("vkEnumeratePhysicalDevices");
        const auto get_properties = instance_function<PFN_vkGetPhysicalDeviceProperties>("vkGetPhysicalDeviceProperties");
        std::uint32_t device_count = 0;
        check(enumerate(instance, &device_count, nullptr), "vkEnumeratePhysicalDevices count");
        if (device_count == 0) {
            throw std::runtime_error("the configured Vulkan ICD exposes no devices");
        }
        std::vector<VkPhysicalDevice> available(device_count);
        check(enumerate(instance, &device_count, available.data()), "vkEnumeratePhysicalDevices");
        available.resize(device_count);
        VkPhysicalDeviceProperties chosen{};
        for (const auto candidate : available) {
            VkPhysicalDeviceProperties properties{};
            get_properties(candidate, &properties);
            const auto physical_match = properties.vendorID == 0x10de
                && properties.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
                && std::string_view(properties.deviceName) == "NVIDIA GeForce RTX 4070 Ti SUPER";
            if (configuration.physical ? physical_match : properties.deviceType == VK_PHYSICAL_DEVICE_TYPE_CPU) {
                if (physical != VK_NULL_HANDLE && configuration.physical) {
                    throw std::runtime_error("ambiguous NVIDIA GeForce RTX 4070 Ti SUPER devices");
                }
                physical = candidate;
                chosen = properties;
                if (!configuration.physical) break;
            }
        }
        if (physical == VK_NULL_HANDLE) {
            throw std::runtime_error(configuration.physical
                ? "requested physical NVIDIA GeForce RTX 4070 Ti SUPER not present"
                : "no CPU-only Vulkan device; refusing physical GPU execution");
        }
        if (has_consumer && (chosen.limits.maxComputeWorkGroupCount[0] == 0
            || chosen.limits.maxComputeWorkGroupSize[0] < compute_group_size
            || chosen.limits.maxComputeWorkGroupInvocations < compute_group_size
            || buffer_size > chosen.limits.maxStorageBufferRange)) {
            throw std::runtime_error("Vulkan limits do not support the benchmark compute consumer");
        }
        max_dispatch_groups = std::min(chosen.limits.maxComputeWorkGroupCount[0], 65535u);
        std::cout << "device=" << chosen.deviceName << " type="
                  << (configuration.physical ? "DISCRETE_GPU" : "CPU")
                  << " vendor_id=" << chosen.vendorID << " device_id=" << chosen.deviceID
                  << " driver_version=" << chosen.driverVersion << " api_version=" << chosen.apiVersion << '\n';
        instance_function<PFN_vkGetPhysicalDeviceMemoryProperties>("vkGetPhysicalDeviceMemoryProperties")(
            physical, &memory_properties);

        const auto queue_properties =
            instance_function<PFN_vkGetPhysicalDeviceQueueFamilyProperties>("vkGetPhysicalDeviceQueueFamilyProperties");
        std::uint32_t family_count = 0;
        queue_properties(physical, &family_count, nullptr);
        std::vector<VkQueueFamilyProperties> families(family_count);
        queue_properties(physical, &family_count, families.data());
        const VkQueueFlags required_queue = has_consumer ? VK_QUEUE_COMPUTE_BIT : VK_QUEUE_TRANSFER_BIT;
        std::uint32_t family = 0;
        while (family < family_count
               && (families[family].queueCount == 0
                   || (families[family].queueFlags
                       & (has_consumer ? required_queue
                       : (required_queue | VK_QUEUE_GRAPHICS_BIT | VK_QUEUE_COMPUTE_BIT))) == 0)) {
            ++family;
        }
        if (family == family_count) {
            throw std::runtime_error("no Vulkan queue supports the requested benchmark operations");
        }

        const float priority = 1.0F;
        VkDeviceQueueCreateInfo queue_info{};
        queue_info.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        queue_info.queueFamilyIndex = family;
        queue_info.queueCount = 1;
        queue_info.pQueuePriorities = &priority;
        VkDeviceCreateInfo device_info{};
        device_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
        device_info.queueCreateInfoCount = 1;
        device_info.pQueueCreateInfos = &queue_info;
        device_proc = instance_function<PFN_vkGetDeviceProcAddr>("vkGetDeviceProcAddr");
        check(instance_function<PFN_vkCreateDevice>("vkCreateDevice")(physical, &device_info, nullptr, &device),
              "vkCreateDevice");
#define LOAD_DEVICE(name) name = device_function<PFN_vk##name>("vk" #name);
        DEVICE_FUNCTIONS(LOAD_DEVICE)
#undef LOAD_DEVICE
        GetDeviceQueue(device, family, 0, &queue);

        VkCommandPoolCreateInfo pool_info{};
        pool_info.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
        pool_info.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
        pool_info.queueFamilyIndex = family;
        check(CreateCommandPool(device, &pool_info, nullptr, &pool), "vkCreateCommandPool");
        VkCommandBufferAllocateInfo commands_info{};
        commands_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        commands_info.commandPool = pool;
        commands_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        commands_info.commandBufferCount = 1;
        check(AllocateCommandBuffers(device, &commands_info, &commands), "vkAllocateCommandBuffers");
        VkFenceCreateInfo fence_info{};
        fence_info.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
        check(CreateFence(device, &fence_info, nullptr, &fence), "vkCreateFence");

        constexpr VkMemoryPropertyFlags host_memory =
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
        const VkMemoryPropertyFlags forbidden_local =
            configuration.physical ? VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT : 0u;
        const VkMemoryPropertyFlags avoid_device_local =
            configuration.physical ? VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT : 0u;
        make_buffer(upload, buffer_size, VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
                    host_memory, 0, avoid_device_local, true);
        for (auto& target : targets) {
            const VkBufferUsageFlags storage = has_consumer ? VK_BUFFER_USAGE_STORAGE_BUFFER_BIT : 0u;
            make_buffer(target, buffer_size, VK_BUFFER_USAGE_TRANSFER_SRC_BIT
                        | VK_BUFFER_USAGE_TRANSFER_DST_BIT | storage,
                        VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, 0, forbidden_local, false);
        }
        if (has_consumer) {
            make_buffer(consumed, buffer_size, VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
                        VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, 0, forbidden_local, false);
        }
        make_buffer(readback, has_consumer ? 2 * buffer_size : buffer_size,
                    VK_BUFFER_USAGE_TRANSFER_DST_BIT, host_memory,
                    VK_MEMORY_PROPERTY_HOST_CACHED_BIT, avoid_device_local, true);
        std::cout << "upload_flags=" << upload.properties << " upload_heap=" << upload.heap
                  << " target_flags=" << targets[0].properties << " target_heap=" << targets[0].heap
                  << " readback_flags=" << readback.properties << " readback_heap=" << readback.heap << '\n';
        if (has_consumer) {
            create_consumer(configuration.shader);
        }
    }

    // Every policy records all upload regions with a single batched copy.
    // The historical software replay keeps its in-submit readback. On the
    // physical path verification is a separate, untimed submission.
    DeviceTimes copy(std::span<const transfer::Range> ranges, std::span<const std::uint32_t> source,
                     std::size_t bytes_per_unit = unit_bytes, std::size_t arm = 0,
                     bool legacy_readback = true, bool run_consumer = false) {
        const auto start = Clock::now();
        const VkDeviceSize active_bytes = source.size_bytes();
        if (active_bytes == 0 || active_bytes > buffer_size || bytes_per_unit == 0
            || bytes_per_unit % sizeof(std::uint32_t) != 0 || active_bytes % bytes_per_unit != 0
            || arm >= targets.size() || (run_consumer && !has_consumer)) {
            throw std::invalid_argument("invalid Vulkan benchmark copy size, arm or pipeline");
        }
        std::vector<VkBufferCopy> regions;
        regions.reserve(ranges.size());
        auto* staging = static_cast<std::byte*>(upload.mapped);
        const auto* input = reinterpret_cast<const std::byte*>(source.data());
        std::uint32_t previous_end = 0;
        for (const auto range : ranges) {
            if (range.begin < previous_end || range.begin >= range.end || range.end > active_bytes / bytes_per_unit) {
                throw std::invalid_argument("Vulkan upload ranges are not sorted, disjoint and in bounds");
            }
            previous_end = range.end;
            const std::size_t offset = range.begin * bytes_per_unit;
            const std::size_t bytes = (range.end - range.begin) * bytes_per_unit;
            std::memcpy(staging + offset, input + offset, bytes);
            regions.push_back({offset, offset, bytes});
        }

        const auto stage_done = Clock::now();
        begin_commands();
        const auto destination = targets[arm].buffer;
        if (!regions.empty()) {
            CmdCopyBuffer(commands, upload.buffer, destination,
                          static_cast<std::uint32_t>(regions.size()), regions.data());
        }
        if (run_consumer) {
            dispatch(arm, static_cast<std::uint32_t>(source.size()));
        }
        if (legacy_readback) {
            record_readback(arm, active_bytes, run_consumer);
        }
        check(EndCommandBuffer(commands), "vkEndCommandBuffer");
        const auto recording_done = Clock::now();
        submit();
        return {elapsed_ns(start, stage_done), elapsed_ns(stage_done, recording_done),
                elapsed_ns(recording_done, Clock::now())};
    }

    void verify_readback(std::size_t arm, std::size_t words, bool with_consumer) {
        begin_commands();
        record_readback(arm, words * sizeof(std::uint32_t), with_consumer);
        check(EndCommandBuffer(commands), "vkEndCommandBuffer readback");
        submit();
    }

    std::span<const std::uint32_t> output(std::size_t words = extent * words_per_unit,
                                          bool consumer_output = false) const {
        const auto* mapped = static_cast<const std::uint32_t*>(readback.mapped);
        return {mapped + (consumer_output ? buffer_size / sizeof(std::uint32_t) : 0), words};
    }

private:
    template <typename Function>
    Function instance_function(const char* name) const {
        const auto result = reinterpret_cast<Function>(instance_proc(instance, name));
        if (!result) {
            throw std::runtime_error(std::string("missing Vulkan instance entry ") + name);
        }
        return result;
    }

    template <typename Function>
    Function device_function(const char* name) const {
        const auto result = reinterpret_cast<Function>(device_proc(device, name));
        if (!result) {
            throw std::runtime_error(std::string("missing Vulkan device entry ") + name);
        }
        return result;
    }

    void release(Buffer& buffer) {
        if (buffer.mapped) {
            UnmapMemory(device, buffer.memory);
        }
        if (buffer.buffer != VK_NULL_HANDLE) {
            DestroyBuffer(device, buffer.buffer, nullptr);
        }
        if (buffer.memory != VK_NULL_HANDLE) {
            FreeMemory(device, buffer.memory, nullptr);
        }
    }

    void begin_commands() {
        check(ResetCommandBuffer(commands, 0), "vkResetCommandBuffer");
        VkCommandBufferBeginInfo begin{};
        begin.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        check(BeginCommandBuffer(commands, &begin), "vkBeginCommandBuffer");
    }

    void submit() {
        check(ResetFences(device, 1, &fence), "vkResetFences");
        VkSubmitInfo submission{};
        submission.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submission.commandBufferCount = 1;
        submission.pCommandBuffers = &commands;
        check(QueueSubmit(queue, 1, &submission, fence), "vkQueueSubmit");
        check(WaitForFences(device, 1, &fence, VK_TRUE, std::numeric_limits<std::uint64_t>::max()),
              "vkWaitForFences");
    }

    void record_readback(std::size_t arm, VkDeviceSize size, bool with_consumer) {
        const auto destination = targets.at(arm).buffer;
        barrier(destination, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_TRANSFER_WRITE_BIT,
                VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_TRANSFER_READ_BIT);
        const VkBufferCopy full{0, 0, size};
        CmdCopyBuffer(commands, destination, readback.buffer, 1, &full);
        if (with_consumer) {
            barrier(consumed.buffer, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_ACCESS_SHADER_WRITE_BIT,
                    VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_TRANSFER_READ_BIT);
            const VkBufferCopy transformed{0, buffer_size, size};
            CmdCopyBuffer(commands, consumed.buffer, readback.buffer, 1, &transformed);
        }
        barrier(readback.buffer, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_TRANSFER_WRITE_BIT,
                VK_PIPELINE_STAGE_HOST_BIT, VK_ACCESS_HOST_READ_BIT);
    }

    void dispatch(std::size_t arm, std::uint32_t words) {
        barrier(targets.at(arm).buffer, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_TRANSFER_WRITE_BIT,
                VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_ACCESS_SHADER_READ_BIT);
        const auto requested = 1 + (words - 1) / compute_group_size;
        const auto groups = std::min(max_dispatch_groups, requested);
        const std::array constants{words, groups * compute_group_size};
        CmdBindPipeline(commands, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline);
        CmdBindDescriptorSets(commands, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline_layout, 0,
                              1, &sets[arm], 0, nullptr);
        CmdPushConstants(commands, pipeline_layout, VK_SHADER_STAGE_COMPUTE_BIT, 0,
                         sizeof(constants), constants.data());
        CmdDispatch(commands, groups, 1, 1);
    }

    void create_consumer(const std::filesystem::path& path) {
        const auto bytes = std::filesystem::file_size(path);
        if (bytes < 5 * sizeof(std::uint32_t) || bytes % sizeof(std::uint32_t) != 0
            || bytes > static_cast<std::uintmax_t>(std::numeric_limits<std::streamsize>::max())) {
            throw std::invalid_argument("invalid SPIR-V compute consumer size");
        }
        std::ifstream input(path, std::ios::binary);
        std::vector<std::uint32_t> words(bytes / sizeof(std::uint32_t));
        if (!input.read(reinterpret_cast<char*>(words.data()), static_cast<std::streamsize>(bytes))
            || words.front() != 0x07230203u) {
            throw std::runtime_error("invalid or unreadable SPIR-V compute consumer");
        }
        VkShaderModuleCreateInfo shader{};
        shader.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO;
        shader.codeSize = bytes;
        shader.pCode = words.data();
        check(CreateShaderModule(device, &shader, nullptr, &shader_module), "vkCreateShaderModule");

        const std::array<VkDescriptorSetLayoutBinding, 2> bindings{{
            {0, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr},
            {1, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr}
        }};
        VkDescriptorSetLayoutCreateInfo layout{};
        layout.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
        layout.bindingCount = static_cast<std::uint32_t>(bindings.size());
        layout.pBindings = bindings.data();
        check(CreateDescriptorSetLayout(device, &layout, nullptr, &descriptor_layout), "vkCreateDescriptorSetLayout");
        const VkDescriptorPoolSize pool_size{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 2 * arm_count};
        VkDescriptorPoolCreateInfo descriptor_pool_info{};
        descriptor_pool_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO;
        descriptor_pool_info.maxSets = arm_count;
        descriptor_pool_info.poolSizeCount = 1;
        descriptor_pool_info.pPoolSizes = &pool_size;
        check(CreateDescriptorPool(device, &descriptor_pool_info, nullptr, &descriptor_pool), "vkCreateDescriptorPool");
        std::array<VkDescriptorSetLayout, arm_count> layouts{};
        layouts.fill(descriptor_layout);
        VkDescriptorSetAllocateInfo allocate_sets{};
        allocate_sets.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
        allocate_sets.descriptorPool = descriptor_pool;
        allocate_sets.descriptorSetCount = arm_count;
        allocate_sets.pSetLayouts = layouts.data();
        check(AllocateDescriptorSets(device, &allocate_sets, sets.data()), "vkAllocateDescriptorSets");
        for (std::size_t arm = 0; arm < sets.size(); ++arm) {
            const std::array<VkDescriptorBufferInfo, 2> buffers{{
                {targets[arm].buffer, 0, buffer_size}, {consumed.buffer, 0, buffer_size}
            }};
            std::array<VkWriteDescriptorSet, 2> writes{};
            for (std::uint32_t binding = 0; binding < 2; ++binding) {
                auto& write = writes[binding];
                write.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
                write.dstSet = sets[arm];
                write.dstBinding = binding;
                write.descriptorCount = 1;
                write.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
                write.pBufferInfo = &buffers[binding];
            }
            UpdateDescriptorSets(device, static_cast<std::uint32_t>(writes.size()), writes.data(), 0, nullptr);
        }
        const VkPushConstantRange constants{VK_SHADER_STAGE_COMPUTE_BIT, 0, 2 * sizeof(std::uint32_t)};
        VkPipelineLayoutCreateInfo pipeline_layout_info{};
        pipeline_layout_info.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO;
        pipeline_layout_info.setLayoutCount = 1;
        pipeline_layout_info.pSetLayouts = &descriptor_layout;
        pipeline_layout_info.pushConstantRangeCount = 1;
        pipeline_layout_info.pPushConstantRanges = &constants;
        check(CreatePipelineLayout(device, &pipeline_layout_info, nullptr, &pipeline_layout), "vkCreatePipelineLayout");
        VkComputePipelineCreateInfo pipeline_info{};
        pipeline_info.sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO;
        pipeline_info.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        pipeline_info.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
        pipeline_info.stage.module = shader_module;
        pipeline_info.stage.pName = "main";
        pipeline_info.layout = pipeline_layout;
        check(CreateComputePipelines(device, VK_NULL_HANDLE, 1, &pipeline_info, nullptr, &pipeline),
              "vkCreateComputePipelines");
    }

    void make_buffer(Buffer& buffer, VkDeviceSize size, VkBufferUsageFlags usage,
                     VkMemoryPropertyFlags required, VkMemoryPropertyFlags preferred,
                     VkMemoryPropertyFlags forbidden, bool map) {
        VkBufferCreateInfo info{};
        info.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
        info.size = size;
        info.usage = usage;
        info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        check(CreateBuffer(device, &info, nullptr, &buffer.buffer), "vkCreateBuffer");
        VkMemoryRequirements requirements{};
        GetBufferMemoryRequirements(device, buffer.buffer, &requirements);
        std::uint32_t type = memory_properties.memoryTypeCount;
        for (std::uint32_t candidate = 0; candidate < memory_properties.memoryTypeCount; ++candidate) {
            const auto properties = memory_properties.memoryTypes[candidate].propertyFlags;
            if (!(requirements.memoryTypeBits & (std::uint32_t{1} << candidate))
                || (properties & required) != required || (properties & forbidden) != 0) {
                continue;
            }
            if (type == memory_properties.memoryTypeCount) {
                type = candidate;
            }
            if ((properties & preferred) == preferred) {
                type = candidate;
                break;
            }
        }
        if (type == memory_properties.memoryTypeCount) {
            throw std::runtime_error("required Vulkan memory type unavailable");
        }
        VkMemoryAllocateInfo allocation{};
        allocation.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        allocation.allocationSize = requirements.size;
        allocation.memoryTypeIndex = type;
        buffer.properties = memory_properties.memoryTypes[type].propertyFlags;
        buffer.heap = memory_properties.memoryTypes[type].heapIndex;
        check(AllocateMemory(device, &allocation, nullptr, &buffer.memory), "vkAllocateMemory");
        check(BindBufferMemory(device, buffer.buffer, buffer.memory, 0), "vkBindBufferMemory");
        if (map) {
            check(MapMemory(device, buffer.memory, 0, size, 0, &buffer.mapped), "vkMapMemory");
        }
    }

    void barrier(VkBuffer buffer, VkPipelineStageFlags before, VkAccessFlags prior_access,
                 VkPipelineStageFlags after, VkAccessFlags next_access) {
        VkBufferMemoryBarrier range{};
        range.sType = VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER;
        range.srcAccessMask = prior_access;
        range.dstAccessMask = next_access;
        range.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        range.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        range.buffer = buffer;
        range.size = VK_WHOLE_SIZE;
        CmdPipelineBarrier(commands, before, after, 0, 0, nullptr, 1, &range, 0, nullptr);
    }

    HMODULE loader = nullptr;
    PFN_vkGetInstanceProcAddr instance_proc = nullptr;
    PFN_vkGetDeviceProcAddr device_proc = nullptr;
    PFN_vkDestroyInstance DestroyInstance = nullptr;
#define DECLARE_DEVICE(name) PFN_vk##name name = nullptr;
    DEVICE_FUNCTIONS(DECLARE_DEVICE)
#undef DECLARE_DEVICE
    VkInstance instance = VK_NULL_HANDLE;
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE;
    VkCommandPool pool = VK_NULL_HANDLE;
    VkCommandBuffer commands = VK_NULL_HANDLE;
    VkFence fence = VK_NULL_HANDLE;
    VkPhysicalDeviceMemoryProperties memory_properties{};
    VkShaderModule shader_module = VK_NULL_HANDLE;
    VkDescriptorSetLayout descriptor_layout = VK_NULL_HANDLE;
    VkDescriptorPool descriptor_pool = VK_NULL_HANDLE;
    std::array<VkDescriptorSet, arm_count> sets{};
    VkPipelineLayout pipeline_layout = VK_NULL_HANDLE;
    VkPipeline pipeline = VK_NULL_HANDLE;
    VkDeviceSize buffer_size = 0;
    std::uint32_t max_dispatch_groups = 0;
    bool has_consumer = false;
    Buffer upload;
    std::array<Buffer, arm_count> targets;
    Buffer consumed;
    Buffer readback;
};

#undef DEVICE_FUNCTIONS

struct Case {
    const char* name;
    std::uint32_t cap;
    transfer::Cost cost;
    std::vector<std::uint32_t> dirty;
};

std::vector<Case> scenarios() {
    Case sparse{"sparse_clustered", 32, {14, 1}, {}};
    Case dense{"dense", 64, {14, 1}, {}};
    Case capped{"greedy_capacity", 3, {3, 1}, {}};
    constexpr std::array sparse_offsets{0u, 1u, 8u, 9u, 10u};
    for (std::uint32_t unit = 0; unit < extent; ++unit) {
        if (unit >= protected_gap.begin && unit < protected_gap.end) {
            continue;
        }
        dense.dirty.push_back(unit);
        if (std::find(sparse_offsets.begin(), sparse_offsets.end(), unit % 113) != sparse_offsets.end()) {
            sparse.dirty.push_back(unit);
        }
        if (unit % 12 == 0 || (unit % 12 >= 2 && unit % 12 <= 4)) {
            capped.dirty.push_back(unit);
        }
    }
    return {sparse, dense, capped};
}

void compare(Vulkan& gpu, std::span<const std::uint32_t> expected) {
    const auto actual = gpu.output();
    const auto [wrong, expected_word] = std::mismatch(actual.begin(), actual.end(), expected.begin());
    if (wrong != actual.end()) {
        throw std::runtime_error("Vulkan readback mismatch at word " + std::to_string(wrong - actual.begin())
                                 + ", expected " + std::to_string(*expected_word)
                                 + ", got " + std::to_string(*wrong));
    }
}

void poison_gap(std::span<std::uint32_t> source) {
    for (auto& word : source.subspan(protected_gap.begin * words_per_unit,
                                    (protected_gap.end - protected_gap.begin) * words_per_unit)) {
        word ^= 0xdeadbeefU;
    }
}

void negative_control(Vulkan& gpu, std::span<const std::uint32_t> baseline) {
    const std::array whole{transfer::Range{0, extent}};
    gpu.copy(whole, baseline);
    compare(gpu, baseline);

    std::vector poisoned(baseline.begin(), baseline.end());
    poison_gap(poisoned);
    const std::array deliberately_forbidden{transfer::Range{protected_gap.begin, protected_gap.begin + 1}};
    gpu.copy(deliberately_forbidden, poisoned);
    const auto expected_change = protected_gap.begin * words_per_unit;
    const auto actual = gpu.output();
    const auto [changed, ignored] = std::mismatch(actual.begin(), actual.end(), baseline.begin());
    if (changed != actual.begin() + static_cast<std::ptrdiff_t>(expected_change)
        || *changed != poisoned[expected_change]) {
        throw std::runtime_error("forbidden upload failed to trip the readback canary");
    }
    std::cout << "negative_control=detected forbidden upload\n";
}

void replay(Vulkan& gpu, const Case& test, const std::vector<std::uint32_t>& baseline) {
    constexpr std::array islands{transfer::Range{0, protected_gap.begin},
                                 transfer::Range{protected_gap.end, extent}};
    constexpr std::array strategies{transfer::Strategy::exact, transfer::Strategy::greedy,
                                    transfer::Strategy::optimal};
    constexpr std::array names{"exact", "greedy", "optimal"};
    constexpr std::array whole{transfer::Range{0, extent}};
    const transfer::Problem problem{extent, test.cap, test.cost, test.dirty, islands};
    std::array<std::vector<double>, strategies.size()> times;
    auto expected = baseline;
    auto source = baseline;
    poison_gap(source);
    gpu.copy(whole, baseline);
    std::uint32_t sequence = 0;

    for (int round = 0; round < warms + trials; ++round) {
        for (std::size_t turn = 0; turn < strategies.size(); ++turn) {
            const auto strategy = (turn + static_cast<std::size_t>(round)) % strategies.size();
            ++sequence;
            for (const auto unit : test.dirty) {
                const auto start = unit * words_per_unit;
                for (std::size_t word = start; word < start + words_per_unit; ++word) {
                    const auto value = baseline[word] ^ (sequence * 0x26544357U);
                    source[word] = value;
                    expected[word] = value;
                }
            }
            const auto begin = std::chrono::steady_clock::now();
            const auto ranges = transfer::plan(problem, strategies[strategy]);
            gpu.copy(ranges, source);
            const auto end = std::chrono::steady_clock::now();
            compare(gpu, expected);
            if (round >= warms) {
                times[strategy].push_back(std::chrono::duration<double, std::micro>(end - begin).count());
            }
        }
    }
    for (std::size_t strategy = 0; strategy < strategies.size(); ++strategy) {
        const auto ranges = transfer::plan(problem, strategies[strategy]);
        std::uint64_t copied = 0;
        for (const auto range : ranges) {
            copied += range.end - range.begin;
        }
        auto& samples = times[strategy];
        std::sort(samples.begin(), samples.end());
        const auto median = (samples[samples.size() / 2 - 1] + samples[samples.size() / 2]) / 2;
        const auto p95 = samples[(95 * samples.size() + 99) / 100 - 1];
        std::cout << test.name << ',' << names[strategy] << ',' << test.dirty.size() << ',' << copied
                  << ',' << ranges.size() << ',' << transfer::score(ranges, test.cost) << ','
                  << std::fixed << std::setprecision(2) << median << ',' << p95 << ',' << samples.front() << '\n';
    }
}

std::size_t selected_index(std::size_t frame_count, std::size_t selected_count, std::size_t index) {
    return (index * frame_count + frame_count / 2) / selected_count;
}

void check_words(std::span<const std::uint32_t> actual, std::span<const std::uint32_t> expected) {
    const auto mismatch = std::mismatch(actual.begin(), actual.end(), expected.begin()).first;
    if (mismatch != actual.end()) {
        throw std::runtime_error("Vulkan traced upload readback mismatch at word "
                                 + std::to_string(mismatch - actual.begin()));
    }
}

std::uint32_t consumer_word(std::uint32_t source, std::uint32_t position) {
    return ((source ^ 0x9e3779b9u) * 0x85ebca6bu) ^ position;
}

void check_consumer(std::span<const std::uint32_t> actual, std::span<const std::uint32_t> expected) {
    for (std::size_t i = 0; i < actual.size(); ++i) {
        if (actual[i] != consumer_word(expected[i], static_cast<std::uint32_t>(i))) {
            throw std::runtime_error("Vulkan compute consumer readback mismatch at word " + std::to_string(i));
        }
    }
}

void poison_unowned(std::span<std::uint32_t> source, std::span<const transfer::Range> allowed, std::size_t words) {
    std::size_t end = 0;
    for (const auto island : allowed) {
        for (auto& word : source.subspan(end, island.begin * words - end)) {
            word ^= 0xdeadbeefu;
        }
        end = island.end * words;
    }
    for (auto& word : source.subspan(end)) {
        word ^= 0xdeadbeefu;
    }
}

void apply_epoch(const physical::Case& test, const physical::Epoch& epoch, std::size_t words,
                 std::span<std::uint32_t> source, std::span<std::uint32_t> expected) {
    std::size_t island = 0;
    for (const auto atom : epoch.dirty) {
        while (island < test.islands.size() && atom >= test.islands[island].end) {
            ++island;
        }
        if (island == test.islands.size() || atom < test.islands[island].begin) {
            throw std::invalid_argument("a traced dirty atom lacks a Vulkan upload authority");
        }
        for (std::size_t i = atom * words; i < (static_cast<std::size_t>(atom) + 1) * words; ++i) {
            const auto value = static_cast<std::uint32_t>(i) * 0x9e3779b9u ^ ((epoch.id + 1) * 0x85ebca6bu);
            source[i] = value;
            expected[i] = value;
        }
    }
}

void replay_trace(Vulkan& gpu, const physical::Trace& trace, const Options& configuration) {
    const auto words = trace.atom_bytes / sizeof(std::uint32_t);
    if (words == 0 || trace.atom_bytes % sizeof(std::uint32_t) != 0
        || (configuration.cap_bytes != 0 && configuration.cap_bytes % trace.atom_bytes != 0)) {
        throw std::invalid_argument("trace and copy cap must have compatible atom widths");
    }
    constexpr std::array strategies{transfer::Strategy::exact, transfer::Strategy::greedy, transfer::Strategy::optimal};
    constexpr std::array names{"exact", "greedy", "optimal"};
    std::cout << "mode=traced_upload_and_compute atom_bytes=" << trace.atom_bytes
              << " repeats=" << configuration.samples << " frame_limit=" << configuration.frame_limit
              << " cost_setup=" << configuration.cost.setup << " cost_unit=" << configuration.cost.unit << '\n'
              << "case,frame_id,frame_index,case_frames,sample,strategy,dirty_atoms,copied_bytes,regions,"
                 "modeled_cost,plan_ns,stage_ns,record_ns,submit_fence_ns,total_ns\n";
    for (const auto& test : trace.cases) {
        if (test.epochs.size() > std::numeric_limits<std::uint32_t>::max()) {
            throw std::invalid_argument("too many trace epochs to select");
        }
        const auto cap = configuration.cap_bytes == 0
            ? test.cap : std::min(test.cap, configuration.cap_bytes / trace.atom_bytes);
        const std::array whole{transfer::Range{0, test.extent}};
        std::vector<std::uint32_t> expected(test.extent * words);
        for (std::size_t i = 0; i < expected.size(); ++i) {
            expected[i] = static_cast<std::uint32_t>(i) * 0x9e3779b9u;
        }
        auto source = expected;
        poison_unowned(source, test.islands, words);
        const std::size_t selected = std::min(test.epochs.size(), static_cast<std::size_t>(configuration.frame_limit));
        std::size_t next = 0;
        for (std::size_t i = 0; i < test.epochs.size() && next < selected; ++i) {
            const auto& epoch = test.epochs[i];
            if (i != selected_index(test.epochs.size(), selected, next)) {
                apply_epoch(test, epoch, words, source, expected);
                continue;
            }
            const bool first_measured_epoch = next == 0;
            ++next;
            const auto before = expected;
            apply_epoch(test, epoch, words, source, expected);
            const transfer::Problem problem{test.extent, cap, configuration.cost, epoch.dirty, test.islands};
            if (first_measured_epoch) {
                for (std::size_t arm = 0; arm < strategies.size(); ++arm) {
                    gpu.copy(whole, before, trace.atom_bytes, arm, false);
                    gpu.copy(transfer::plan(problem, strategies[arm]), source, trace.atom_bytes, arm, false, true);
                    gpu.verify_readback(arm, expected.size(), true);
                    check_words(gpu.output(expected.size()), expected);
                    check_consumer(gpu.output(expected.size(), true), expected);
                }
            }
            for (std::uint32_t sample = 0; sample < configuration.samples; ++sample) {
                for (std::size_t turn = 0; turn < strategies.size(); ++turn) {
                    const auto arm = (turn + i + sample) % strategies.size();
                    // Restore the exact pre-epoch state so a missing upload
                    // cannot pass after a previous repetition of this epoch.
                    gpu.copy(whole, before, trace.atom_bytes, arm, false);
                    const auto start = Clock::now();
                    const auto ranges = transfer::plan(problem, strategies[arm]);
                    const auto planned = Clock::now();
                    const auto device_times = gpu.copy(ranges, source, trace.atom_bytes, arm, false, true);
                    const auto done = Clock::now();
                    gpu.verify_readback(arm, expected.size(), true);
                    check_words(gpu.output(expected.size()), expected);
                    check_consumer(gpu.output(expected.size(), true), expected);

                    std::uint64_t copied = 0;
                    for (const auto range : ranges) {
                        copied += range.end - range.begin;
                    }
                    std::cout << test.name << ',' << epoch.id << ',' << i << ',' << test.epochs.size()
                              << ',' << sample << ',' << names[arm] << ',' << epoch.dirty.size()
                              << ',' << copied * trace.atom_bytes << ',' << ranges.size() << ','
                              << transfer::score(ranges, configuration.cost) << ','
                              << std::fixed << std::setprecision(0) << elapsed_ns(start, planned) << ','
                              << device_times.staging_ns << ',' << device_times.recording_ns << ','
                              << device_times.submit_fence_ns << ',' << elapsed_ns(start, done) << '\n';
                }
            }
        }
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const auto configuration = options(argc, argv);
        physical::Trace trace;
        VkDeviceSize capacity = size_bytes;
        if (!configuration.trace.empty()) {
            trace = physical::read_trace(configuration.trace);
            for (const auto& test : trace.cases) {
                const auto case_bytes = static_cast<VkDeviceSize>(test.extent) * trace.atom_bytes;
                if (case_bytes > 64u * 1024u * 1024u) {
                    throw std::invalid_argument("trace buffers must be at most 64 MiB per case");
                }
                capacity = std::max(capacity, case_bytes);
            }
        }
        Vulkan gpu;
        gpu.initialize(configuration, capacity);
        std::vector<std::uint32_t> baseline(extent * words_per_unit);
        for (std::size_t word = 0; word < baseline.size(); ++word) {
            baseline[word] = static_cast<std::uint32_t>(word) * 0x9e3779b9U;
        }
        negative_control(gpu, baseline);
        if (!trace.cases.empty()) {
            replay_trace(gpu, trace, configuration);
            return 0;
        }
        std::cout << "samples_per_strategy=" << trials << " unit_bytes=" << unit_bytes
                  << " readback_bytes=" << size_bytes << '\n';
        std::cout << "case,strategy,dirty_units,copied_units,regions,modeled_cost,median_us,p95_us,min_us\n";
        for (const auto& test : scenarios()) {
            replay(gpu, test, baseline);
        }
    } catch (const std::exception& error) {
        std::cerr << "Vulkan replay failed: " << error.what() << '\n';
        return 1;
    }
}
