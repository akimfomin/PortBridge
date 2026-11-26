// SPDX-License-Identifier: MIT
#include <vulkan/vulkan.h>

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <latch>
#include <mutex>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
using namespace std::chrono_literals;
using std::uint32_t;
constexpr unsigned recipe_count = 6;
constexpr unsigned foreground = recipe_count - 1;
constexpr unsigned output_words = 512;
constexpr unsigned group_size = 32;
constexpr uint32_t canary = 0x9baf0392u;
constexpr VkDeviceSize output_bytes = (output_words + 2) * sizeof(uint32_t);
constexpr std::uint64_t fence_timeout_ns = 1'000'000'000;

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

void check(VkResult result, const char* operation) {
    if (result != VK_SUCCESS)
        throw std::runtime_error(std::string(operation) + " returned " + std::to_string(result));
}

template <typename T>
T info(VkStructureType type) {
    T value{};
    value.sType = type;
    return value;
}

double ms(Clock::duration interval) {
    return std::chrono::duration<double, std::milli>(interval).count();
}

struct Job {
    VkShaderModule module{};
    VkPipeline pipeline{};
    VkPipelineCreationFeedback feedback{};
    VkResult preflight = VK_NOT_READY;
    VkResult status = VK_NOT_READY;
    Clock::time_point requested{}, entered{}, returned{};
};

struct Vulkan {
    VkInstance instance{};
    VkPhysicalDevice physical{};
    VkPhysicalDeviceProperties properties{};
    VkDevice device{};
    VkQueue queue{};
    VkPipelineCache cache{};
    VkDescriptorSetLayout bindings{};
    VkPipelineLayout layout{};
    VkDescriptorPool descriptors{};
    VkDescriptorSet descriptor{};
    VkBuffer buffer{};
    VkDeviceMemory memory{};
    uint32_t* words{};
    VkCommandPool commands{};
    VkCommandBuffer command{};
    VkFence fence{};
    std::array<Job, recipe_count> jobs{};

    ~Vulkan() {
        if (device) {
            vkDeviceWaitIdle(device);
            for (const auto& job : jobs) {
                vkDestroyPipeline(device, job.pipeline, nullptr);
                vkDestroyShaderModule(device, job.module, nullptr);
            }
            if (words) vkUnmapMemory(device, memory);
            vkDestroyFence(device, fence, nullptr);
            vkDestroyCommandPool(device, commands, nullptr);
            vkDestroyDescriptorPool(device, descriptors, nullptr);
            vkDestroyBuffer(device, buffer, nullptr);
            vkFreeMemory(device, memory, nullptr);
            vkDestroyPipelineLayout(device, layout, nullptr);
            vkDestroyDescriptorSetLayout(device, bindings, nullptr);
            vkDestroyPipelineCache(device, cache, nullptr);
            vkDestroyDevice(device, nullptr);
        }
        vkDestroyInstance(instance, nullptr);
    }

    void start(std::string_view adapter) {
        auto app = info<VkApplicationInfo>(VK_STRUCTURE_TYPE_APPLICATION_INFO);
        app.pApplicationName = "PortBridge pipeline readiness";
        app.apiVersion = VK_API_VERSION_1_3;
        auto instance_info = info<VkInstanceCreateInfo>(VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO);
        instance_info.pApplicationInfo = &app;
        check(vkCreateInstance(&instance_info, nullptr, &instance), "vkCreateInstance");
        uint32_t count{};
        check(vkEnumeratePhysicalDevices(instance, &count, nullptr), "vkEnumeratePhysicalDevices count");
        require(count > 0 && count <= 64, "Unexpected physical device count");
        std::vector<VkPhysicalDevice> devices(count);
        check(vkEnumeratePhysicalDevices(instance, &count, devices.data()), "vkEnumeratePhysicalDevices");
        for (auto candidate : devices) {
            VkPhysicalDeviceProperties device_properties{};
            vkGetPhysicalDeviceProperties(candidate, &device_properties);
            if (adapter != device_properties.deviceName) continue;
            require(!physical && device_properties.apiVersion >= VK_API_VERSION_1_3 &&
                    (device_properties.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU ||
                     device_properties.deviceType == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU),
                    "Expected exactly one matching Vulkan 1.3 physical GPU");
            physical = candidate;
            properties = device_properties;
        }
        require(physical, "Exact physical GPU name not found");

        vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, nullptr);
        require(count > 0 && count <= 64, "Unexpected queue family count");
        std::vector<VkQueueFamilyProperties> families(count);
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, families.data());
        uint32_t family = 0;
        while (family < count && !(families[family].queueFlags & VK_QUEUE_COMPUTE_BIT)) ++family;
        require(family < count, "Compute queue unavailable");
        auto core = info<VkPhysicalDeviceVulkan13Features>(VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES);
        auto supported = info<VkPhysicalDeviceFeatures2>(VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2);
        supported.pNext = &core;
        vkGetPhysicalDeviceFeatures2(physical, &supported);
        require(core.pipelineCreationCacheControl, "Pipeline compile-required control unavailable");
        core = info<VkPhysicalDeviceVulkan13Features>(VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES);
        core.pipelineCreationCacheControl = VK_TRUE;
        const float priority = 1.0f;
        auto queue_info = info<VkDeviceQueueCreateInfo>(VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO);
        queue_info.queueFamilyIndex = family;
        queue_info.queueCount = 1;
        queue_info.pQueuePriorities = &priority;
        auto device_info = info<VkDeviceCreateInfo>(VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO);
        device_info.pNext = &core;
        device_info.queueCreateInfoCount = 1;
        device_info.pQueueCreateInfos = &queue_info;
        check(vkCreateDevice(physical, &device_info, nullptr, &device), "vkCreateDevice");
        vkGetDeviceQueue(device, family, 0, &queue);

        auto cache_info = info<VkPipelineCacheCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO);
        check(vkCreatePipelineCache(device, &cache_info, nullptr, &cache), "vkCreatePipelineCache");
        auto command_pool = info<VkCommandPoolCreateInfo>(VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO);
        command_pool.queueFamilyIndex = family;
        check(vkCreateCommandPool(device, &command_pool, nullptr, &commands), "vkCreateCommandPool");
        auto allocate = info<VkCommandBufferAllocateInfo>(VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO);
        allocate.commandPool = commands;
        allocate.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        allocate.commandBufferCount = 1;
        check(vkAllocateCommandBuffers(device, &allocate, &command), "vkAllocateCommandBuffers");
        auto fence_info = info<VkFenceCreateInfo>(VK_STRUCTURE_TYPE_FENCE_CREATE_INFO);
        check(vkCreateFence(device, &fence_info, nullptr, &fence), "vkCreateFence");
    }

    void make_output() {
        auto buffer_info = info<VkBufferCreateInfo>(VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO);
        buffer_info.size = output_bytes;
        buffer_info.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT;
        buffer_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        check(vkCreateBuffer(device, &buffer_info, nullptr, &buffer), "vkCreateBuffer");
        VkPhysicalDeviceMemoryProperties memory_types{};
        vkGetPhysicalDeviceMemoryProperties(physical, &memory_types);
        VkMemoryRequirements requirements{};
        vkGetBufferMemoryRequirements(device, buffer, &requirements);
        auto allocate = info<VkMemoryAllocateInfo>(VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO);
        allocate.allocationSize = requirements.size;
        constexpr auto required = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
        allocate.memoryTypeIndex = memory_types.memoryTypeCount;
        for (uint32_t i = 0; i < memory_types.memoryTypeCount; ++i) {
            const auto flags = memory_types.memoryTypes[i].propertyFlags;
            if (!(requirements.memoryTypeBits & (1u << i)) || (flags & required) != required) continue;
            allocate.memoryTypeIndex = i;
            if (flags & VK_MEMORY_PROPERTY_HOST_CACHED_BIT) break;
        }
        require(allocate.memoryTypeIndex < memory_types.memoryTypeCount, "Coherent host-visible memory unavailable");
        check(vkAllocateMemory(device, &allocate, nullptr, &memory), "vkAllocateMemory");
        check(vkBindBufferMemory(device, buffer, memory, 0), "vkBindBufferMemory");
        void* mapped{};
        check(vkMapMemory(device, memory, 0, output_bytes, 0, &mapped), "vkMapMemory");
        words = static_cast<uint32_t*>(mapped);
        std::fill_n(words, output_words + 2, canary);

        VkDescriptorSetLayoutBinding binding{0, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1,
                                             VK_SHADER_STAGE_COMPUTE_BIT, nullptr};
        auto descriptor_layout = info<VkDescriptorSetLayoutCreateInfo>(VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO);
        descriptor_layout.bindingCount = 1;
        descriptor_layout.pBindings = &binding;
        check(vkCreateDescriptorSetLayout(device, &descriptor_layout, nullptr, &bindings), "vkCreateDescriptorSetLayout");
        auto pipeline_layout = info<VkPipelineLayoutCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO);
        pipeline_layout.setLayoutCount = 1;
        pipeline_layout.pSetLayouts = &bindings;
        check(vkCreatePipelineLayout(device, &pipeline_layout, nullptr, &layout), "vkCreatePipelineLayout");
        VkDescriptorPoolSize size{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1};
        auto pool_info = info<VkDescriptorPoolCreateInfo>(VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO);
        pool_info.maxSets = pool_info.poolSizeCount = 1;
        pool_info.pPoolSizes = &size;
        check(vkCreateDescriptorPool(device, &pool_info, nullptr, &descriptors), "vkCreateDescriptorPool");
        auto descriptor_set = info<VkDescriptorSetAllocateInfo>(VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO);
        descriptor_set.descriptorPool = descriptors;
        descriptor_set.descriptorSetCount = 1;
        descriptor_set.pSetLayouts = &bindings;
        check(vkAllocateDescriptorSets(device, &descriptor_set, &descriptor), "vkAllocateDescriptorSets");
        VkDescriptorBufferInfo buffer_descriptor{buffer, 0, output_bytes};
        auto write = info<VkWriteDescriptorSet>(VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET);
        write.dstSet = descriptor;
        write.descriptorCount = 1;
        write.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
        write.pBufferInfo = &buffer_descriptor;
        vkUpdateDescriptorSets(device, 1, &write, 0, nullptr);
    }

    void load_recipes(const std::filesystem::path& folder) {
        for (unsigned id = 0; id != recipe_count; ++id) {
            const auto filename = folder / (std::to_string(id) + ".spv");
            std::ifstream stream(filename, std::ios::binary | std::ios::ate);
            require(bool(stream), "Cannot open shader recipe");
            const auto size = stream.tellg();
            require(size >= 20 && size <= 4096 && size % 4 == 0, "Invalid shader recipe length");
            std::vector<uint32_t> code(static_cast<std::size_t>(size) / 4);
            stream.seekg(0);
            require(bool(stream.read(reinterpret_cast<char*>(code.data()), size)) && code.front() == 0x07230203,
                    "Invalid SPIR-V recipe");
            auto module = info<VkShaderModuleCreateInfo>(VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO);
            module.codeSize = static_cast<std::size_t>(size);
            module.pCode = code.data();
            check(vkCreateShaderModule(device, &module, nullptr, &jobs[id].module), "vkCreateShaderModule");
        }
    }

    VkResult create(Job& job, VkPipelineCache target, VkPipelineCreateFlags flags, bool measure) {
        auto pipeline = info<VkComputePipelineCreateInfo>(VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO);
        pipeline.stage = info<VkPipelineShaderStageCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO);
        pipeline.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
        pipeline.stage.module = job.module;
        pipeline.stage.pName = "main";
        pipeline.layout = layout;
        pipeline.flags = flags;
        pipeline.basePipelineIndex = -1;
        auto feedback = info<VkPipelineCreationFeedbackCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_CREATION_FEEDBACK_CREATE_INFO);
        if (measure) {
            feedback.pPipelineCreationFeedback = &job.feedback;
            pipeline.pNext = &feedback;
            job.entered = Clock::now();
        }
        const auto status = vkCreateComputePipelines(device, target, 1, &pipeline, nullptr, &job.pipeline);
        if (measure) job.returned = Clock::now();
        return status;
    }

    void preflight(bool background) {
        for (unsigned id = background ? 0 : foreground; id != recipe_count; ++id) {
            auto& job = jobs[id];
            job.preflight = create(job, VK_NULL_HANDLE, VK_PIPELINE_CREATE_FAIL_ON_PIPELINE_COMPILE_REQUIRED_BIT, false);
            require(job.preflight == VK_PIPELINE_COMPILE_REQUIRED && !job.pipeline,
                    "Unique empty-cache recipe did not report compile required");
        }
    }

    void warm_foreground() {
        auto& job = jobs[foreground];
        check(create(job, cache, 0, false), "Warm pipeline creation");
        require(job.pipeline, "Warm pipeline missing");
        vkDestroyPipeline(device, job.pipeline, nullptr);
        job.pipeline = VK_NULL_HANDLE;
        job.preflight = create(job, cache, VK_PIPELINE_CREATE_FAIL_ON_PIPELINE_COMPILE_REQUIRED_BIT, false);
        require(job.preflight == VK_SUCCESS && job.pipeline, "Warm application cache could not supply pipeline");
        vkDestroyPipeline(device, job.pipeline, nullptr);
        job.pipeline = VK_NULL_HANDLE;
    }

    void observe(uint32_t salt) {
        require(jobs[foreground].pipeline, "Missing foreground pipeline");
        auto begin = info<VkCommandBufferBeginInfo>(VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO);
        begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        check(vkBeginCommandBuffer(command, &begin), "vkBeginCommandBuffer");
        vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_COMPUTE, jobs[foreground].pipeline);
        vkCmdBindDescriptorSets(command, VK_PIPELINE_BIND_POINT_COMPUTE, layout, 0, 1, &descriptor, 0, nullptr);
        vkCmdDispatch(command, output_words / group_size, 1, 1);
        auto barrier = info<VkMemoryBarrier>(VK_STRUCTURE_TYPE_MEMORY_BARRIER);
        barrier.srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT;
        barrier.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
        vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_HOST_BIT,
                             0, 1, &barrier, 0, nullptr, 0, nullptr);
        check(vkEndCommandBuffer(command), "vkEndCommandBuffer");
        auto submit = info<VkSubmitInfo>(VK_STRUCTURE_TYPE_SUBMIT_INFO);
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &command;
        check(vkQueueSubmit(queue, 1, &submit, fence), "vkQueueSubmit");
        check(vkWaitForFences(device, 1, &fence, VK_TRUE, fence_timeout_ns), "vkWaitForFences");
        require(words[0] == canary && words[output_words + 1] == canary, "Output guard changed");
        for (uint32_t i = 0; i != output_words; ++i)
            require(words[i + 1] == (i ^ salt), "GPU output differs from the CPU oracle");
    }
};

struct Measurements {
    Clock::time_point start, observed, drained;
};

Measurements measure(Vulkan& vk, std::string_view mode, uint32_t salt) {
    const bool demand_first = mode == "demand-first";
    const bool shared_workers = demand_first || mode == "fifo";
    const bool background = shared_workers || mode == "reserved";
    const unsigned workers = shared_workers ? 2 : background ? 1 : 0;
    std::latch begun(1), foreground_done(1);
    std::mutex pending_mutex;
    std::condition_variable pending_changed;
    unsigned next_background = 0;
    bool demand_ready = false, demand_taken = false, abort = false;
    const auto compile = [&](unsigned id) {
        auto& job = vk.jobs[id];
        job.status = vk.create(job, vk.cache, 0, true);
    };
    const auto dequeue = [&]() {
        std::unique_lock lock(pending_mutex);
        pending_changed.wait(lock, [&] {
            return abort || next_background < foreground || demand_ready || !shared_workers;
        });
        if (abort) return recipe_count;
        if (shared_workers && demand_ready && !demand_taken && (demand_first || next_background == foreground)) {
            demand_taken = true;
            return foreground;
        }
        if (next_background < foreground) return next_background++;
        return recipe_count;
    };
    const auto worker = [&] {
        begun.wait();
        for (auto id = dequeue(); id < recipe_count; id = dequeue()) {
            compile(id);
            if (id == foreground) foreground_done.count_down();
        }
    };
    std::vector<std::jthread> threads;
    threads.reserve(workers);
    try {
        for (unsigned i = 0; i != workers; ++i) threads.emplace_back(worker);
    } catch (...) {
        {
            std::lock_guard lock(pending_mutex);
            abort = true;
        }
        begun.count_down();
        pending_changed.notify_all();
        throw;
    }
    Measurements result{};
    result.start = Clock::now();
    if (background)
        for (unsigned id = 0; id != foreground; ++id) vk.jobs[id].requested = result.start;
    begun.count_down();
    if (background) std::this_thread::sleep_until(result.start + 1ms);
    auto& needed = vk.jobs[foreground];
    {
        std::lock_guard lock(pending_mutex);
        needed.requested = Clock::now();
        demand_ready = true;
    }
    pending_changed.notify_all();
    if (shared_workers) foreground_done.wait();
    else compile(foreground);
    check(needed.status, "Foreground pipeline creation");
    vk.observe(salt + foreground);
    result.observed = Clock::now();
    for (auto& thread : threads) thread.join();
    result.drained = Clock::now();
    return result;
}

void report(const Vulkan& vk, std::string_view mode, Measurements timing) {
    const bool background = mode == "fifo" || mode == "demand-first" || mode == "reserved";
    const auto& needed = vk.jobs[foreground];
    // Feedback validity and explicit application-cache conditions qualify every arm.
    for (unsigned id = background ? 0 : foreground; id != recipe_count; ++id) {
        const auto& job = vk.jobs[id];
        check(job.status, "Measured pipeline creation");
        require(job.pipeline && (job.feedback.flags & VK_PIPELINE_CREATION_FEEDBACK_VALID_BIT),
                "Valid pipeline and timing feedback required");
        const bool hit = (job.feedback.flags & VK_PIPELINE_CREATION_FEEDBACK_APPLICATION_PIPELINE_CACHE_HIT_BIT) != 0;
        require(hit == (mode == "warm"), "Application-cache feedback did not qualify the arm");
    }
    std::cout << std::fixed << std::setprecision(6)
              << "{\"mode\":\"" << mode << "\",\"vendor\":" << vk.properties.vendorID
              << ",\"device\":" << vk.properties.deviceID << ",\"driver\":" << vk.properties.driverVersion
              << ",\"api\":" << vk.properties.apiVersion
              << ",\"demand_to_verified_ms\":" << ms(timing.observed - needed.requested)
              << ",\"dispatch_and_verify_ms\":" << ms(timing.observed - needed.returned)
              << ",\"full_work_ms\":" << ms(timing.drained - timing.start)
              << ",\"verified_words\":" << output_words << ",\"intact_guards\":2,\"jobs\":[";
    for (unsigned id = background ? 0 : foreground; id != recipe_count; ++id) {
        const auto& job = vk.jobs[id];
        if (id != (background ? 0 : foreground)) std::cout << ',';
        std::cout << "{\"id\":" << id << ",\"preflight_result\":" << job.preflight
                  << ",\"feedback_flags\":" << job.feedback.flags << ",\"feedback_ns\":" << job.feedback.duration
                  << ",\"requested_ms\":" << ms(job.requested - timing.start)
                  << ",\"entered_ms\":" << ms(job.entered - timing.start)
                  << ",\"returned_ms\":" << ms(job.returned - timing.start)
                  << ",\"cpu_wall_ms\":" << ms(job.returned - job.entered) << '}';
    }
    std::cout << "]}\n";
}
} // namespace

int main(int argc, const char** args) {
    try {
        require(argc == 5, "Usage: native_probe cold|warm|fifo|demand-first|reserved adapter shader-folder base-salt");
        const std::string_view mode(args[1]);
        require(mode == "cold" || mode == "warm" || mode == "fifo" || mode == "demand-first" || mode == "reserved",
                "Unknown mode");
        const std::string_view salt_arg(args[4]);
        uint32_t salt{};
        const auto parsed = std::from_chars(salt_arg.data(), salt_arg.data() + salt_arg.size(), salt);
        require(parsed.ec == std::errc{} && parsed.ptr == salt_arg.data() + salt_arg.size() &&
                salt >= 100'000 && salt <= 3'000'000'000u, "Invalid recipe salt");
        Vulkan vk;
        vk.start(args[2]);
        vk.make_output();
        vk.load_recipes(args[3]);
        if (mode == "warm") vk.warm_foreground();
        else vk.preflight(mode != "cold");
        report(vk, mode, measure(vk, mode, salt));
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
