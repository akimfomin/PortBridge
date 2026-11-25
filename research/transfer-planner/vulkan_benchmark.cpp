// SPDX-License-Identifier: MIT
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#define VK_NO_PROTOTYPES
#include <windows.h>
#include <vulkan/vulkan.h>

#include "planner.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr std::uint32_t extent = 2048;
constexpr std::size_t unit_bytes = 256;
constexpr std::size_t words_per_unit = unit_bytes / sizeof(std::uint32_t);
constexpr VkDeviceSize size_bytes = extent * unit_bytes;
constexpr transfer::Range protected_gap{960, 1088};
constexpr int warms = 4;
constexpr int trials = 24;

void check(VkResult result, const char* operation) {
    if (result != VK_SUCCESS) {
        throw std::runtime_error(std::string(operation) + " failed with VkResult " + std::to_string(result));
    }
}

struct Buffer {
    VkBuffer buffer = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    void* mapped = nullptr;
};

#define DEVICE_FUNCTIONS(X) \
    X(DestroyDevice) X(GetDeviceQueue) X(DeviceWaitIdle) \
    X(CreateBuffer) X(DestroyBuffer) X(GetBufferMemoryRequirements) \
    X(AllocateMemory) X(FreeMemory) X(BindBufferMemory) X(MapMemory) X(UnmapMemory) \
    X(CreateCommandPool) X(DestroyCommandPool) X(AllocateCommandBuffers) X(ResetCommandBuffer) \
    X(BeginCommandBuffer) X(EndCommandBuffer) X(CmdPipelineBarrier) X(CmdCopyBuffer) \
    X(CreateFence) X(DestroyFence) X(ResetFences) X(QueueSubmit) X(WaitForFences)

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
            for (auto* buffer : {&readback, &target, &upload}) {
                if (buffer->mapped) {
                    UnmapMemory(device, buffer->memory);
                }
                if (buffer->buffer != VK_NULL_HANDLE) {
                    DestroyBuffer(device, buffer->buffer, nullptr);
                }
                if (buffer->memory != VK_NULL_HANDLE) {
                    FreeMemory(device, buffer->memory, nullptr);
                }
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

    void initialize() {
        // Require an explicitly selected ICD as well as a CPU device type.
        if (GetEnvironmentVariableW(L"VK_DRIVER_FILES", nullptr, 0) == 0) {
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
        app.pApplicationName = "PortBridge transfer planner software replay";
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
        for (const auto candidate : available) {
            VkPhysicalDeviceProperties properties{};
            get_properties(candidate, &properties);
            if (properties.deviceType == VK_PHYSICAL_DEVICE_TYPE_CPU) {
                physical = candidate;
                std::cout << "device=" << properties.deviceName << " type=CPU"
                          << " driver_version=" << properties.driverVersion << '\n';
                break;
            }
        }
        if (physical == VK_NULL_HANDLE) {
            throw std::runtime_error("no CPU-only Vulkan device; refusing physical GPU execution");
        }
        instance_function<PFN_vkGetPhysicalDeviceMemoryProperties>("vkGetPhysicalDeviceMemoryProperties")(
            physical, &memory_properties);

        const auto queue_properties =
            instance_function<PFN_vkGetPhysicalDeviceQueueFamilyProperties>("vkGetPhysicalDeviceQueueFamilyProperties");
        std::uint32_t family_count = 0;
        queue_properties(physical, &family_count, nullptr);
        std::vector<VkQueueFamilyProperties> families(family_count);
        queue_properties(physical, &family_count, families.data());
        std::uint32_t family = 0;
        while (family < family_count
               && (families[family].queueCount == 0
                   || (families[family].queueFlags
                       & (VK_QUEUE_TRANSFER_BIT | VK_QUEUE_GRAPHICS_BIT | VK_QUEUE_COMPUTE_BIT)) == 0)) {
            ++family;
        }
        if (family == family_count) {
            throw std::runtime_error("the CPU device exposes no queue that can copy buffers");
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

        constexpr auto host_memory = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
        make_buffer(upload, VK_BUFFER_USAGE_TRANSFER_SRC_BIT, host_memory, true);
        make_buffer(target, VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT,
                    VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, false);
        make_buffer(readback, VK_BUFFER_USAGE_TRANSFER_DST_BIT, host_memory, true);
    }

    // All upload regions use one vkCmdCopyBuffer and share the same submit and
    // completion fence with the full verification readback.
    void copy(std::span<const transfer::Range> ranges, std::span<const std::uint32_t> source) {
        std::vector<VkBufferCopy> regions;
        regions.reserve(ranges.size());
        auto* staging = static_cast<std::byte*>(upload.mapped);
        for (const auto range : ranges) {
            const std::size_t offset = range.begin * unit_bytes;
            const std::size_t bytes = (range.end - range.begin) * unit_bytes;
            std::memcpy(staging + offset, source.data() + range.begin * words_per_unit, bytes);
            regions.push_back({offset, offset, bytes});
        }
        check(ResetCommandBuffer(commands, 0), "vkResetCommandBuffer");
        VkCommandBufferBeginInfo begin{};
        begin.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        check(BeginCommandBuffer(commands, &begin), "vkBeginCommandBuffer");

        if (!regions.empty()) {
            CmdCopyBuffer(commands, upload.buffer, target.buffer,
                          static_cast<std::uint32_t>(regions.size()), regions.data());
        }
        barrier(target.buffer, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_TRANSFER_WRITE_BIT,
                VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_TRANSFER_READ_BIT);
        const VkBufferCopy full{0, 0, size_bytes};
        CmdCopyBuffer(commands, target.buffer, readback.buffer, 1, &full);
        barrier(readback.buffer, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_TRANSFER_WRITE_BIT,
                VK_PIPELINE_STAGE_HOST_BIT, VK_ACCESS_HOST_READ_BIT);
        check(EndCommandBuffer(commands), "vkEndCommandBuffer");

        check(ResetFences(device, 1, &fence), "vkResetFences");
        VkSubmitInfo submit{};
        submit.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &commands;
        check(QueueSubmit(queue, 1, &submit, fence), "vkQueueSubmit");
        check(WaitForFences(device, 1, &fence, VK_TRUE, std::numeric_limits<std::uint64_t>::max()),
              "vkWaitForFences");
    }

    std::span<const std::uint32_t> output() const {
        return {static_cast<const std::uint32_t*>(readback.mapped), extent * words_per_unit};
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

    void make_buffer(Buffer& buffer, VkBufferUsageFlags usage, VkMemoryPropertyFlags flags, bool map) {
        VkBufferCreateInfo info{};
        info.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
        info.size = size_bytes;
        info.usage = usage;
        info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        check(CreateBuffer(device, &info, nullptr, &buffer.buffer), "vkCreateBuffer");
        VkMemoryRequirements requirements{};
        GetBufferMemoryRequirements(device, buffer.buffer, &requirements);
        std::uint32_t type = 0;
        while (type < memory_properties.memoryTypeCount
               && ((requirements.memoryTypeBits & (std::uint32_t{1} << type)) == 0
                   || (memory_properties.memoryTypes[type].propertyFlags & flags) != flags)) {
            ++type;
        }
        if (type == memory_properties.memoryTypeCount) {
            throw std::runtime_error("required Vulkan memory type unavailable");
        }
        VkMemoryAllocateInfo allocation{};
        allocation.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        allocation.allocationSize = requirements.size;
        allocation.memoryTypeIndex = type;
        check(AllocateMemory(device, &allocation, nullptr, &buffer.memory), "vkAllocateMemory");
        check(BindBufferMemory(device, buffer.buffer, buffer.memory, 0), "vkBindBufferMemory");
        if (map) {
            check(MapMemory(device, buffer.memory, 0, size_bytes, 0, &buffer.mapped), "vkMapMemory");
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
        range.size = size_bytes;
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
    Buffer upload;
    Buffer target;
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

}  // namespace

int main() {
    try {
        Vulkan gpu;
        gpu.initialize();
        std::vector<std::uint32_t> baseline(extent * words_per_unit);
        for (std::size_t word = 0; word < baseline.size(); ++word) {
            baseline[word] = static_cast<std::uint32_t>(word) * 0x9e3779b9U;
        }
        negative_control(gpu, baseline);
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
