// SPDX-License-Identifier: MIT
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <psapi.h>
#include <vulkan/vulkan.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <mutex>
#include <latch>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
using namespace std::chrono_literals;
constexpr uint32_t width = 1024, height = 768;
constexpr size_t color_size = width * height * 4;
constexpr unsigned pipeline_count = 6;
constexpr unsigned worker_count = 3;
constexpr VkFormat color_format = VK_FORMAT_R8G8B8A8_UNORM;
constexpr VkFormat depth_format = VK_FORMAT_D32_SFLOAT;
constexpr std::array<unsigned, 2> demanded{0, 3};
constexpr std::array<unsigned, 4> prewarm{1, 2, 4, 5};

double ms(Clock::duration time) { return std::chrono::duration<double, std::milli>(time).count(); }
void require(bool valid, std::string_view message) {
    if (!valid) throw std::runtime_error(std::string(message));
}
void check(VkResult result, std::string_view method) {
    if (result != VK_SUCCESS) {
        throw std::runtime_error(std::string(method) + " status " + std::to_string(result));
    }
}
template<class T> T structure(VkStructureType type) {
    T object{};
    object.sType = type;
    return object;
}
template<class T> void read(std::istream& stream, T* items, size_t count) {
    require(bool(stream.read(reinterpret_cast<char*>(items), sizeof(T) * count)), "Truncated input");
}
template<class T> std::vector<T> vector_read(std::istream& stream, size_t count) {
    std::vector<T> result(count);
    read(stream, result.data(), count);
    return result;
}

struct Vertex {float position[3], normal[3], uv[2];};
static_assert(sizeof(Vertex) == 32);
struct Packet {
    uint32_t first, count, base, transparent, material;
    float translation[3], rotation[4];
    uint32_t textures[4];
    float factor[4];
};
static_assert(sizeof(Packet) == 80);
struct Push {
    float translation[4], rotation[4], factor[4];
    uint32_t textures[4], controls[4];
};
static_assert(sizeof(Push) == 80);

struct Scene {
    std::vector<Vertex> vertices;
    std::vector<uint32_t> indices;
    std::vector<Packet> packets;
    std::vector<uint8_t> texels;
    uint32_t side{}, layers{};

    explicit Scene(const std::filesystem::path& path) {
        std::ifstream stream(path, std::ios::binary);
        std::array<char, 4> magic{};
        std::array<uint32_t, 5> counts{};
        read(stream, magic.data(), magic.size());
        read(stream, counts.data(), counts.size());
        require(magic == std::array{'P', 'B', 'S', 'C'} && counts[0] <= 500000 && counts[1] <= 2000000 &&
                counts[2] == 49 && counts[3] == 34 && counts[4] == 512, "Unexpected pinned scene shape");
        layers = counts[3];
        side = counts[4];
        vertices = vector_read<Vertex>(stream, counts[0]);
        indices = vector_read<uint32_t>(stream, counts[1]);
        packets = vector_read<Packet>(stream, counts[2]);
        texels = vector_read<uint8_t>(stream, size_t(layers) * side * side * 4);
        require(stream.peek() == EOF, "Trailing scene data");
        for (const Packet& packet : packets) {
            require(packet.first <= indices.size() && packet.count <= indices.size() - packet.first &&
                    packet.base < vertices.size() && packet.transparent <= 1 && packet.material < 15 &&
                    packet.count && packet.count % 3 == 0, "Invalid draw range");
            for (unsigned i = 0; i < 3; ++i) require(packet.textures[i] < layers, "Invalid texture layer");
            for (uint32_t index = packet.first; index != packet.first + packet.count; ++index)
                require(indices[index] < vertices.size() - packet.base, "Out of range geometry index");
        }
    }
    void release_upload_data() {
        std::vector<uint8_t>().swap(texels);
        std::vector<Vertex>().swap(vertices);
        std::vector<uint32_t>().swap(indices);
    }
};

struct Buffer {VkBuffer handle{}; VkDeviceMemory memory{}; void* mapped = nullptr;};
struct Image {VkImage handle{}; VkDeviceMemory memory{}; VkImageView view{};};
struct Build {
    VkPipeline handle{};
    VkResult probe = VK_NOT_READY, result = VK_NOT_READY;
    VkPipelineCreationFeedback feedback{};
    Clock::time_point start{}, end{};
};

struct Renderer {
    VkInstance instance{};
    VkPhysicalDevice physical{};
    VkPhysicalDeviceProperties props{};
    VkPhysicalDeviceMemoryProperties memory_types{};
    VkDevice device{};
    VkQueue queue{};
    VkPipelineCache cache{};
    VkCommandPool commands{};
    VkCommandBuffer command{};
    VkFence fence{};
    VkDescriptorPool descriptors{};
    VkDescriptorSetLayout bindings{};
    VkDescriptorSet descriptor{};
    VkPipelineLayout layout{};
    VkShaderModule vertex{}, pixel{};
    VkSampler sampler{};
    Buffer vertices, indices, readback, upload;
    Image color, depth, textures;
    std::array<Build, pipeline_count> builds{};
    VkDeviceSize allocated{};

    ~Renderer() {
        if (device) {
            vkDeviceWaitIdle(device);
            for (const auto& build : builds) vkDestroyPipeline(device, build.handle, nullptr);
            vkDestroyShaderModule(device, vertex, nullptr);
            vkDestroyShaderModule(device, pixel, nullptr);
            vkDestroyPipelineLayout(device, layout, nullptr);
            vkDestroyDescriptorPool(device, descriptors, nullptr);
            vkDestroyDescriptorSetLayout(device, bindings, nullptr);
            vkDestroySampler(device, sampler, nullptr);
            for (Image* image : {&color, &depth, &textures}) {
                vkDestroyImageView(device, image->view, nullptr);
                vkDestroyImage(device, image->handle, nullptr);
                vkFreeMemory(device, image->memory, nullptr);
            }
            for (Buffer* buffer : {&vertices, &indices, &readback, &upload}) release(*buffer);
            vkDestroyFence(device, fence, nullptr);
            vkDestroyCommandPool(device, commands, nullptr);
            vkDestroyPipelineCache(device, cache, nullptr);
            vkDestroyDevice(device, nullptr);
        }
        vkDestroyInstance(instance, nullptr);
    }
    void release(Buffer& buffer) {
        if (buffer.mapped) vkUnmapMemory(device, buffer.memory);
        vkDestroyBuffer(device, buffer.handle, nullptr);
        vkFreeMemory(device, buffer.memory, nullptr);
        buffer = {};
    }
    void start(std::string_view adapter) {
        auto app = structure<VkApplicationInfo>(VK_STRUCTURE_TYPE_APPLICATION_INFO);
        app.pApplicationName = "PortBridge open scene pipeline readiness";
        app.apiVersion = VK_API_VERSION_1_3;
        auto info = structure<VkInstanceCreateInfo>(VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO);
        info.pApplicationInfo = &app;
        check(vkCreateInstance(&info, nullptr, &instance), "vkCreateInstance");
        uint32_t count = 0;
        check(vkEnumeratePhysicalDevices(instance, &count, nullptr), "vkEnumeratePhysicalDevices count");
        require(count && count <= 64, "Unexpected adapter count");
        std::vector<VkPhysicalDevice> devices(count);
        check(vkEnumeratePhysicalDevices(instance, &count, devices.data()), "vkEnumeratePhysicalDevices");
        for (auto candidate : devices) {
            VkPhysicalDeviceProperties candidate_props{};
            vkGetPhysicalDeviceProperties(candidate, &candidate_props);
            if (candidate_props.deviceName != adapter) continue;
            require(!physical && candidate_props.apiVersion >= VK_API_VERSION_1_3 &&
                    (candidate_props.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU ||
                     candidate_props.deviceType == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU),
                    "Expected exact physical Vulkan 1.3 adapter");
            physical = candidate;
            props = candidate_props;
        }
        require(physical, "Selected adapter was not found");
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, nullptr);
        require(count && count <= 64, "Unexpected queue family count");
        std::vector<VkQueueFamilyProperties> families(count);
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, families.data());
        uint32_t family = 0;
        while (family != count && !(families[family].queueFlags & VK_QUEUE_GRAPHICS_BIT)) ++family;
        require(family != count, "No graphics queue");

        auto core = structure<VkPhysicalDeviceVulkan13Features>(VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES);
        auto features = structure<VkPhysicalDeviceFeatures2>(VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2);
        features.pNext = &core;
        vkGetPhysicalDeviceFeatures2(physical, &features);
        require(core.dynamicRendering && core.pipelineCreationCacheControl, "Missing required Vulkan 1.3 features");
        core = structure<VkPhysicalDeviceVulkan13Features>(VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES);
        core.dynamicRendering = core.pipelineCreationCacheControl = VK_TRUE;
        const float priority = 1.0f;
        auto queue_info = structure<VkDeviceQueueCreateInfo>(VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO);
        queue_info.queueCount = 1;
        queue_info.queueFamilyIndex = family;
        queue_info.pQueuePriorities = &priority;
        auto device_info = structure<VkDeviceCreateInfo>(VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO);
        device_info.pNext = &core;
        device_info.queueCreateInfoCount = 1;
        device_info.pQueueCreateInfos = &queue_info;
        check(vkCreateDevice(physical, &device_info, nullptr, &device), "vkCreateDevice");
        vkGetDeviceQueue(device, family, 0, &queue);
        vkGetPhysicalDeviceMemoryProperties(physical, &memory_types);

        const auto cache_info = structure<VkPipelineCacheCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO);
        check(vkCreatePipelineCache(device, &cache_info, nullptr, &cache), "vkCreatePipelineCache");
        auto pool = structure<VkCommandPoolCreateInfo>(VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO);
        pool.queueFamilyIndex = family;
        pool.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
        check(vkCreateCommandPool(device, &pool, nullptr, &commands), "vkCreateCommandPool");
        auto allocate = structure<VkCommandBufferAllocateInfo>(VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO);
        allocate.commandPool = commands;
        allocate.commandBufferCount = 1;
        check(vkAllocateCommandBuffers(device, &allocate, &command), "vkAllocateCommandBuffers");
        const auto fence_info = structure<VkFenceCreateInfo>(VK_STRUCTURE_TYPE_FENCE_CREATE_INFO);
        check(vkCreateFence(device, &fence_info, nullptr, &fence), "vkCreateFence");
    }
    void allocation(const VkMemoryRequirements& limits, VkMemoryPropertyFlags flags, VkDeviceMemory& output) {
        uint32_t type = 0;
        while (type < memory_types.memoryTypeCount &&
               (!(limits.memoryTypeBits & (1u << type)) ||
                (memory_types.memoryTypes[type].propertyFlags & flags) != flags)) ++type;
        require(type < memory_types.memoryTypeCount, "No compatible memory type");
        auto properties = structure<VkMemoryAllocateInfo>(VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO);
        properties.allocationSize = limits.size;
        properties.memoryTypeIndex = type;
        check(vkAllocateMemory(device, &properties, nullptr, &output), "vkAllocateMemory");
        allocated += limits.size;
    }
    void make_buffer(Buffer& output, VkDeviceSize size, VkBufferUsageFlags usage) {
        auto info = structure<VkBufferCreateInfo>(VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO);
        info.size = size;
        info.usage = usage;
        info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        check(vkCreateBuffer(device, &info, nullptr, &output.handle), "vkCreateBuffer");
        VkMemoryRequirements requirements{};
        vkGetBufferMemoryRequirements(device, output.handle, &requirements);
        allocation(requirements, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, output.memory);
        check(vkBindBufferMemory(device, output.handle, output.memory, 0), "vkBindBufferMemory");
        check(vkMapMemory(device, output.memory, 0, size, 0, &output.mapped), "vkMapMemory");
    }
    void make_image(Image& image, VkFormat format, VkExtent3D extent, uint32_t layers, VkImageUsageFlags usage,
                    VkImageAspectFlags aspect) {
        auto info = structure<VkImageCreateInfo>(VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO);
        info.imageType = VK_IMAGE_TYPE_2D;
        info.format = format;
        info.extent = extent;
        info.mipLevels = 1;
        info.arrayLayers = layers;
        info.samples = VK_SAMPLE_COUNT_1_BIT;
        info.tiling = VK_IMAGE_TILING_OPTIMAL;
        info.usage = usage;
        info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        check(vkCreateImage(device, &info, nullptr, &image.handle), "vkCreateImage");
        VkMemoryRequirements requirements{};
        vkGetImageMemoryRequirements(device, image.handle, &requirements);
        allocation(requirements, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, image.memory);
        check(vkBindImageMemory(device, image.handle, image.memory, 0), "vkBindImageMemory");
        auto view = structure<VkImageViewCreateInfo>(VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO);
        view.image = image.handle;
        view.viewType = layers == 1 ? VK_IMAGE_VIEW_TYPE_2D : VK_IMAGE_VIEW_TYPE_2D_ARRAY;
        view.format = format;
        view.subresourceRange = {aspect, 0, 1, 0, layers};
        check(vkCreateImageView(device, &view, nullptr, &image.view), "vkCreateImageView");
    }
    void begin() {
        auto info = structure<VkCommandBufferBeginInfo>(VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO);
        info.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        check(vkBeginCommandBuffer(command, &info), "vkBeginCommandBuffer");
    }
    void finish() {
        check(vkEndCommandBuffer(command), "vkEndCommandBuffer");
        auto submission = structure<VkSubmitInfo>(VK_STRUCTURE_TYPE_SUBMIT_INFO);
        submission.commandBufferCount = 1;
        submission.pCommandBuffers = &command;
        check(vkQueueSubmit(queue, 1, &submission, fence), "vkQueueSubmit");
        check(vkWaitForFences(device, 1, &fence, VK_TRUE, 3'000'000'000), "vkWaitForFences");
        check(vkResetFences(device, 1, &fence), "vkResetFences");
        check(vkResetCommandBuffer(command, 0), "vkResetCommandBuffer");
    }
    void transition(Image& image, VkImageLayout from, VkImageLayout to, VkImageSubresourceRange subresource,
                    VkPipelineStageFlags earlier, VkPipelineStageFlags later, VkAccessFlags written,
                    VkAccessFlags observed) {
        auto barrier = structure<VkImageMemoryBarrier>(VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER);
        barrier.srcAccessMask = written;
        barrier.dstAccessMask = observed;
        barrier.oldLayout = from;
        barrier.newLayout = to;
        barrier.srcQueueFamilyIndex = barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        barrier.image = image.handle;
        barrier.subresourceRange = subresource;
        vkCmdPipelineBarrier(command, earlier, later, 0, 0, nullptr, 0, nullptr, 1, &barrier);
    }
    void upload_scene(const Scene& scene) {
        make_buffer(vertices, scene.vertices.size() * sizeof(Vertex), VK_BUFFER_USAGE_VERTEX_BUFFER_BIT);
        make_buffer(indices, scene.indices.size() * sizeof(uint32_t), VK_BUFFER_USAGE_INDEX_BUFFER_BIT);
        make_buffer(readback, color_size, VK_BUFFER_USAGE_TRANSFER_DST_BIT);
        make_buffer(upload, scene.texels.size(), VK_BUFFER_USAGE_TRANSFER_SRC_BIT);
        std::memcpy(vertices.mapped, scene.vertices.data(), scene.vertices.size() * sizeof(Vertex));
        std::memcpy(indices.mapped, scene.indices.data(), scene.indices.size() * sizeof(uint32_t));
        std::memcpy(upload.mapped, scene.texels.data(), scene.texels.size());
        make_image(color, color_format, {width, height, 1}, 1,
                   VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT, VK_IMAGE_ASPECT_COLOR_BIT);
        make_image(depth, depth_format, {width, height, 1}, 1, VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT,
                   VK_IMAGE_ASPECT_DEPTH_BIT);
        make_image(textures, color_format, {scene.side, scene.side, 1}, scene.layers,
                   VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT, VK_IMAGE_ASPECT_COLOR_BIT);
        begin();
        const VkImageSubresourceRange region{VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, scene.layers};
        transition(textures, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, region,
                   VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0,
                   VK_ACCESS_TRANSFER_WRITE_BIT);
        VkBufferImageCopy transfer{};
        transfer.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, scene.layers};
        transfer.imageExtent = {scene.side, scene.side, 1};
        vkCmdCopyBufferToImage(command, upload.handle, textures.handle, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1,
                               &transfer);
        transition(textures, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,
                   region, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT,
                   VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT);
        finish();
        release(upload);
    }
    void layout_for_scene() {
        const std::array<VkDescriptorSetLayoutBinding, 2> binding_specs{{
            {0, VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE, 1, VK_SHADER_STAGE_FRAGMENT_BIT, nullptr},
            {1, VK_DESCRIPTOR_TYPE_SAMPLER, 1, VK_SHADER_STAGE_FRAGMENT_BIT, nullptr},
        }};
        auto spec = structure<VkDescriptorSetLayoutCreateInfo>(VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO);
        spec.bindingCount = binding_specs.size();
        spec.pBindings = binding_specs.data();
        check(vkCreateDescriptorSetLayout(device, &spec, nullptr, &bindings), "vkCreateDescriptorSetLayout");
        const VkPushConstantRange push{VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT, 0, sizeof(Push)};
        auto pipe = structure<VkPipelineLayoutCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO);
        pipe.setLayoutCount = 1;
        pipe.pSetLayouts = &bindings;
        pipe.pushConstantRangeCount = 1;
        pipe.pPushConstantRanges = &push;
        check(vkCreatePipelineLayout(device, &pipe, nullptr, &layout), "vkCreatePipelineLayout");
    }
    void descriptors_for_scene() {
        auto sampling = structure<VkSamplerCreateInfo>(VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO);
        sampling.magFilter = sampling.minFilter = VK_FILTER_LINEAR;
        sampling.addressModeU = sampling.addressModeV = sampling.addressModeW = VK_SAMPLER_ADDRESS_MODE_REPEAT;
        check(vkCreateSampler(device, &sampling, nullptr, &sampler), "vkCreateSampler");
        const std::array<VkDescriptorPoolSize, 2> sizes{{
            {VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE, 1}, {VK_DESCRIPTOR_TYPE_SAMPLER, 1},
        }};
        auto pool = structure<VkDescriptorPoolCreateInfo>(VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO);
        pool.maxSets = 1;
        pool.poolSizeCount = sizes.size();
        pool.pPoolSizes = sizes.data();
        check(vkCreateDescriptorPool(device, &pool, nullptr, &descriptors), "vkCreateDescriptorPool");
        auto allocate = structure<VkDescriptorSetAllocateInfo>(VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO);
        allocate.descriptorPool = descriptors;
        allocate.descriptorSetCount = 1;
        allocate.pSetLayouts = &bindings;
        check(vkAllocateDescriptorSets(device, &allocate, &descriptor), "vkAllocateDescriptorSets");
        const std::array<VkDescriptorImageInfo, 2> sampled{{
            {VK_NULL_HANDLE, textures.view, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL}, {sampler, {}, {}},
        }};
        std::array<VkWriteDescriptorSet, 2> writes{};
        for (unsigned i = 0; i < writes.size(); ++i) {
            auto& write = writes[i];
            write = structure<VkWriteDescriptorSet>(VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET);
            write.dstSet = descriptor;
            write.dstBinding = i;
            write.descriptorCount = 1;
            write.descriptorType = sizes[i].type;
            write.pImageInfo = &sampled[i];
        }
        vkUpdateDescriptorSets(device, writes.size(), writes.data(), 0, nullptr);
    }
    void shader(const std::filesystem::path& path, VkShaderModule& output) {
        std::ifstream file(path, std::ios::binary | std::ios::ate);
        auto bytes = file.tellg();
        require(bytes > 20 && bytes < 65536 && bytes % 4 == 0, "Unexpected shader size");
        file.seekg(0);
        auto spv = vector_read<uint32_t>(file, static_cast<size_t>(bytes) / 4);
        require(spv[0] == 0x07230203, "Bad SPIR-V signature");
        auto info = structure<VkShaderModuleCreateInfo>(VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO);
        info.codeSize = spv.size() * sizeof(uint32_t);
        info.pCode = spv.data();
        check(vkCreateShaderModule(device, &info, nullptr, &output), "vkCreateShaderModule");
    }

    VkResult make_pipeline(unsigned variant, VkPipelineCache selected_cache, VkPipelineCreateFlags flags,
                           VkPipeline& output, VkPipelineCreationFeedback* stats) {
        const VkSpecializationMapEntry entry{0, 0, sizeof(variant)};
        const VkSpecializationInfo specialize{1, &entry, sizeof(variant), &variant};
        std::array<VkPipelineShaderStageCreateInfo, 2> stages{};
        stages[0] = structure<VkPipelineShaderStageCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO);
        stages[0].stage = VK_SHADER_STAGE_VERTEX_BIT;
        stages[0].module = vertex;
        stages[0].pName = "vertex";
        stages[1] = structure<VkPipelineShaderStageCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO);
        stages[1].stage = VK_SHADER_STAGE_FRAGMENT_BIT;
        stages[1].module = pixel;
        stages[1].pName = "pixel";
        stages[1].pSpecializationInfo = &specialize;
        const VkVertexInputBindingDescription binding{0, sizeof(Vertex), VK_VERTEX_INPUT_RATE_VERTEX};
        const std::array<VkVertexInputAttributeDescription, 3> attributes{{
            {0, 0, VK_FORMAT_R32G32B32_SFLOAT, offsetof(Vertex, position)},
            {1, 0, VK_FORMAT_R32G32B32_SFLOAT, offsetof(Vertex, normal)},
            {2, 0, VK_FORMAT_R32G32_SFLOAT, offsetof(Vertex, uv)},
        }};
        auto input = structure<VkPipelineVertexInputStateCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO);
        input.vertexBindingDescriptionCount = 1;
        input.pVertexBindingDescriptions = &binding;
        input.vertexAttributeDescriptionCount = attributes.size();
        input.pVertexAttributeDescriptions = attributes.data();
        auto assembly = structure<VkPipelineInputAssemblyStateCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO);
        assembly.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
        const VkViewport view_port{0, 0, float(width), float(height), 0, 1};
        const VkRect2D scissor{{0, 0}, {width, height}};
        auto view = structure<VkPipelineViewportStateCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO);
        view.viewportCount = view.scissorCount = 1;
        view.pViewports = &view_port;
        view.pScissors = &scissor;
        auto raster = structure<VkPipelineRasterizationStateCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO);
        raster.polygonMode = VK_POLYGON_MODE_FILL;
        raster.cullMode = VK_CULL_MODE_NONE;
        raster.frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE;
        raster.lineWidth = 1;
        auto samples = structure<VkPipelineMultisampleStateCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO);
        samples.rasterizationSamples = VK_SAMPLE_COUNT_1_BIT;
        auto depth_state = structure<VkPipelineDepthStencilStateCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO);
        const bool transparent = variant >= 3;
        depth_state.depthTestEnable = VK_TRUE;
        depth_state.depthWriteEnable = !transparent;
        depth_state.depthCompareOp = VK_COMPARE_OP_LESS;
        VkPipelineColorBlendAttachmentState attachment{};
        attachment.blendEnable = transparent;
        attachment.colorWriteMask = 0xf;
        attachment.srcColorBlendFactor = VK_BLEND_FACTOR_SRC_ALPHA;
        attachment.dstColorBlendFactor = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
        attachment.colorBlendOp = VK_BLEND_OP_ADD;
        attachment.srcAlphaBlendFactor = VK_BLEND_FACTOR_ONE;
        attachment.dstAlphaBlendFactor = VK_BLEND_FACTOR_ZERO;
        attachment.alphaBlendOp = VK_BLEND_OP_ADD;
        auto blend = structure<VkPipelineColorBlendStateCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO);
        blend.attachmentCount = 1;
        blend.pAttachments = &attachment;
        auto feedback = structure<VkPipelineCreationFeedbackCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_CREATION_FEEDBACK_CREATE_INFO);
        feedback.pPipelineCreationFeedback = stats;
        auto rendering = structure<VkPipelineRenderingCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_RENDERING_CREATE_INFO);
        rendering.pNext = stats ? &feedback : nullptr;
        rendering.colorAttachmentCount = 1;
        rendering.pColorAttachmentFormats = &color_format;
        rendering.depthAttachmentFormat = depth_format;
        auto info = structure<VkGraphicsPipelineCreateInfo>(VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO);
        info.pNext = &rendering;
        info.flags = flags;
        info.stageCount = stages.size();
        info.pStages = stages.data();
        info.pVertexInputState = &input;
        info.pInputAssemblyState = &assembly;
        info.pViewportState = &view;
        info.pRasterizationState = &raster;
        info.pMultisampleState = &samples;
        info.pDepthStencilState = &depth_state;
        info.pColorBlendState = &blend;
        info.layout = layout;
        info.basePipelineIndex = -1;
        return vkCreateGraphicsPipelines(device, selected_cache, 1, &info, nullptr, &output);
    }
    void preflight(bool warm) {
        for (unsigned i = 0; i < builds.size(); ++i) {
            auto& build = builds[i];
            VkPipeline handle{};
            if (warm) {
                check(make_pipeline(i, cache, 0, handle, nullptr), "Warm vkCreateGraphicsPipelines");
                vkDestroyPipeline(device, handle, nullptr);
                handle = {};
            }
            build.probe = make_pipeline(i, warm ? cache : VK_NULL_HANDLE,
                VK_PIPELINE_CREATE_FAIL_ON_PIPELINE_COMPILE_REQUIRED_BIT, handle, nullptr);
            // A first-run stale recipe must never silently enter the cold comparison.
            require(build.probe == (warm ? VK_SUCCESS : VK_PIPELINE_COMPILE_REQUIRED),
                    "Graphics pipeline preflight found unexpected cache state");
            vkDestroyPipeline(device, handle, nullptr);
        }
    }
    void compile(unsigned id) {
        auto& build = builds[id];
        build.start = Clock::now();
        build.result = make_pipeline(id, cache, 0, build.handle, &build.feedback);
        build.end = Clock::now();
    }

    std::vector<uint8_t> draw(const Scene& scene, unsigned variant, unsigned camera, bool initial) {
        const auto old_color = initial ? VK_IMAGE_LAYOUT_UNDEFINED : VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
        const auto old_depth = initial ? VK_IMAGE_LAYOUT_UNDEFINED : VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;
        constexpr VkImageSubresourceRange color_range{VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        constexpr VkImageSubresourceRange depth_range{VK_IMAGE_ASPECT_DEPTH_BIT, 0, 1, 0, 1};
        begin();
        transition(color, old_color, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, color_range,
                   initial ? VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT : VK_PIPELINE_STAGE_TRANSFER_BIT,
                   VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, initial ? 0 : VK_ACCESS_TRANSFER_READ_BIT,
                   VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT);
        constexpr VkPipelineStageFlags depth_stages = VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT |
                                                     VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT;
        transition(depth, old_depth, VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL, depth_range,
                   initial ? VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT : depth_stages, depth_stages,
                   initial ? 0 : VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT,
                   VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_READ_BIT | VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT);
        auto color_attachment = structure<VkRenderingAttachmentInfo>(VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO);
        color_attachment.imageView = color.view;
        color_attachment.imageLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
        color_attachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
        color_attachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
        color_attachment.clearValue.color = {{0.0235294f, 0.0352941f, 0.0549020f, 1}};
        auto depth_attachment = structure<VkRenderingAttachmentInfo>(VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO);
        depth_attachment.imageView = depth.view;
        depth_attachment.imageLayout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;
        depth_attachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
        depth_attachment.storeOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        depth_attachment.clearValue.depthStencil = {1, 0};
        auto rendering = structure<VkRenderingInfo>(VK_STRUCTURE_TYPE_RENDERING_INFO);
        rendering.renderArea = {{0, 0}, {width, height}};
        rendering.layerCount = 1;
        rendering.colorAttachmentCount = 1;
        rendering.pColorAttachments = &color_attachment;
        rendering.pDepthAttachment = &depth_attachment;
        vkCmdBeginRendering(command, &rendering);
        vkCmdBindDescriptorSets(command, VK_PIPELINE_BIND_POINT_GRAPHICS, layout, 0, 1, &descriptor, 0, nullptr);
        const VkDeviceSize offset = 0;
        vkCmdBindVertexBuffers(command, 0, 1, &vertices.handle, &offset);
        vkCmdBindIndexBuffer(command, indices.handle, 0, VK_INDEX_TYPE_UINT32);
        const auto draw_packet = [&](const Packet& packet) {
            Push push{};
            std::copy_n(packet.translation, 3, push.translation);
            std::copy_n(packet.rotation, 4, push.rotation);
            std::copy_n(packet.factor, 4, push.factor);
            std::copy_n(packet.textures, 4, push.textures);
            push.controls[1] = camera;
            vkCmdPushConstants(command, layout, VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT,
                               0, sizeof(Push), &push);
            vkCmdDrawIndexed(command, packet.count, 1, packet.first, static_cast<int32_t>(packet.base), 0);
        };
        vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_GRAPHICS, builds[variant].handle);
        std::vector<const Packet*> translucent;
        for (const auto& packet : scene.packets) {
            if (packet.transparent) translucent.push_back(&packet);
            else draw_packet(packet);
        }
        constexpr std::array<std::array<float, 3>, 3> eyes{{{0.61f, 0.48f, 0.72f}, {-0.71f, 0.49f, 0.76f},
                                                           {0.29f, 0.86f, -0.54f}}};
        const auto distance = [&](const Packet* p) {
            float result = 0;
            for (unsigned i = 0; i < 3; ++i) {
                float displacement = p->translation[i] - eyes.at(camera)[i];
                result += displacement * displacement;
            }
            return result;
        };
        std::stable_sort(translucent.begin(), translucent.end(),
                         [&](auto left, auto right) {return distance(left) > distance(right);});
        vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_GRAPHICS, builds[variant + 3].handle);
        for (const auto* packet : translucent) draw_packet(*packet);
        vkCmdEndRendering(command);
        transition(color, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, color_range,
                   VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                   VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT);
        VkBufferImageCopy copy{};
        copy.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
        copy.imageExtent = {width, height, 1};
        vkCmdCopyImageToBuffer(command, color.handle, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, readback.handle, 1, &copy);
        auto visibility = structure<VkMemoryBarrier>(VK_STRUCTURE_TYPE_MEMORY_BARRIER);
        visibility.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        visibility.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
        vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT,
                             0, 1, &visibility, 0, nullptr, 0, nullptr);
        finish();
        const auto* pixels = static_cast<const uint8_t*>(readback.mapped);
        return {pixels, pixels + color_size};
    }
};

struct Memory {
    uint64_t commit{}, working_set{}, peak_commit{}, peak_working_set{};
};

Memory process_memory() {
    PROCESS_MEMORY_COUNTERS_EX counters{};
    require(GetProcessMemoryInfo(GetCurrentProcess(), reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&counters),
                                 sizeof(counters)), "GetProcessMemoryInfo");
    return {counters.PrivateUsage, counters.WorkingSetSize, counters.PeakPagefileUsage,
            counters.PeakWorkingSetSize};
}

struct Measurements {
    Clock::time_point schedule, request, frame, drained, all_frames;
    Clock::time_point upload_begin, upload_end;
    Memory initial, first_frame, last;
    uint64_t sampled_max_commit = 0;
    unsigned active = 0;
    uint64_t triangles = 0;
    std::array<size_t, 3> foreground_pixels{};
    std::array<std::vector<uint8_t>, 3> images;
};

size_t changed_pixels(const std::vector<uint8_t>& rgba) {
    size_t changed = 0;
    require(rgba.size() == color_size, "Unexpected frame size");
    for (size_t i = 0; i < rgba.size(); i += 4) {
        if (rgba[i] != 6 || rgba[i+1] != 9 || rgba[i+2] != 14 || rgba[i+3] != 255) ++changed;
    }
    require(changed > width * height / 10 && changed < width * height * 9 / 10, "Scene did not render");
    return changed;
}

Measurements measure(Renderer& renderer, Scene& scene, std::string_view mode, bool upload_pending) {
    const bool reserve = mode == "reserved";
    const bool early_create = mode == "phase-lead";
    const bool first_known = mode == "critical-first" || upload_pending;
    const unsigned first_background = reserve ? worker_count - 1 : worker_count;
    Measurements m{};
    m.initial = process_memory();
    for (const auto& packet : scene.packets) m.triangles += packet.count / 3;
    std::mutex lock;
    std::condition_variable work;
    std::latch ready(1), foreground_done(demanded.size());
    unsigned warmups_assigned = 0, required_assigned = 0, required_completed = 0;
    bool early_ready = false, demand_ready = false, abort = false;
    std::atomic<uint64_t> measured_commit{m.initial.commit};
    auto sample_commit = [&] {
        PROCESS_MEMORY_COUNTERS_EX metrics{};
        if (!GetProcessMemoryInfo(GetCurrentProcess(), reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&metrics),
                                  sizeof(metrics))) return;
        uint64_t old = measured_commit.load(std::memory_order_relaxed);
        while (old < metrics.PrivateUsage &&
               !measured_commit.compare_exchange_weak(old, metrics.PrivateUsage, std::memory_order_relaxed)) {}
    };
    auto worker = [&](const unsigned index) {
        const bool dedicated = reserve && index == worker_count - 1;
        ready.wait();
        for (;;) {
            unsigned job = 0;
            bool need;
            {
                std::unique_lock guard(lock);
                work.wait(guard, [&] {
                    return abort || demand_ready || (early_ready && required_assigned < demanded.size()) ||
                           (!first_known && !dedicated && warmups_assigned < prewarm.size());
                });
                if (abort) return;
                if ((demand_ready || early_ready) && required_assigned < demanded.size()) {
                    job = demanded[required_assigned++];
                    need = true;
                } else if (warmups_assigned < prewarm.size() && (!dedicated || required_completed == demanded.size())) {
                    job = prewarm[warmups_assigned++];
                    work.notify_all();
                    need = false;
                } else if (dedicated && required_completed != demanded.size()) {
                    work.wait(guard, [&] { return abort || required_completed == demanded.size(); });
                    continue;
                } else if (!demand_ready) {
                    continue;
                } else {
                    return;
                }
            }
            renderer.compile(job);
            sample_commit();
            if (need) {
                {
                    std::lock_guard guard(lock);
                    ++required_completed;
                }
                foreground_done.count_down();
                work.notify_all();
            }
        }
    };
    // Thread destructors must join before the state and actions they reference unwind.
    std::vector<std::jthread> workers;
    workers.reserve(worker_count);
    std::jthread monitor;
    try {
        for (unsigned i = 0; i < worker_count; ++i) workers.emplace_back(worker, i);
        monitor = std::jthread([&](std::stop_token stop) {
            ready.wait();
            while (!stop.stop_requested()) {
                sample_commit();
                std::this_thread::sleep_for(1ms);
            }
        });
    } catch (...) {
        {
            std::lock_guard guard(lock);
            abort = true;
        }
        ready.count_down();
        work.notify_all();
        throw;
    }
    m.schedule = Clock::now();
    ready.count_down();
    if (upload_pending) {
        try {
            if (early_create) {
                {
                    std::lock_guard guard(lock);
                    early_ready = true;
                }
                work.notify_all();
            }
            m.upload_begin = Clock::now();
            renderer.upload_scene(scene);
            m.upload_end = Clock::now();
            scene.release_upload_data();
            renderer.descriptors_for_scene();
        } catch (...) {
            {
                std::lock_guard guard(lock);
                abort = true;
            }
            work.notify_all();
            throw;
        }
    }
    {
        std::unique_lock guard(lock);
        if (!first_known) work.wait(guard, [&] { return warmups_assigned >= first_background; });
        m.request = Clock::now();
        demand_ready = true;
    }
    work.notify_all();
    foreground_done.wait();
    for (auto i : demanded) check(renderer.builds[i].result, "First output pipeline");
    m.images[0] = renderer.draw(scene, 0, 0, true);
    m.foreground_pixels[0] = changed_pixels(m.images[0]);
    m.frame = Clock::now();
    m.first_frame = process_memory();
    for (auto& thread : workers) thread.join();
    m.drained = Clock::now();
    for (auto i : prewarm) {
        auto& build = renderer.builds[i];
        check(build.result, "Diagnostic view pipeline");
        m.active += (build.start <= m.request && m.request < build.end);
    }
    m.images[1] = renderer.draw(scene, 1, 1, false);
    m.foreground_pixels[1] = changed_pixels(m.images[1]);
    m.images[2] = renderer.draw(scene, 2, 2, false);
    m.foreground_pixels[2] = changed_pixels(m.images[2]);
    m.all_frames = Clock::now();
    sample_commit();
    monitor.request_stop();
    monitor.join();
    m.last = process_memory();
    m.sampled_max_commit = measured_commit.load(std::memory_order_relaxed);
    return m;
}

void output_frames(const std::filesystem::path& dir, const Measurements& values) {
    for (unsigned i = 0; i < values.images.size(); ++i) {
        std::ofstream output(dir / (std::to_string(i) + ".rgba"), std::ios::binary | std::ios::trunc);
        const auto& image = values.images[i];
        require(bool(output.write(reinterpret_cast<const char*>(image.data()), image.size())), "Writing scene capture");
    }
}
} // namespace

int main(int argc, char** argv) {
    try {
        const auto begin = Clock::now();
        require(argc == 6, "scene MODE ADAPTER PREPARED_SCENE SHADER_DIR FRAME_DIR");
        const std::string_view mode = argv[1];
        const bool phase = mode == "phase-reference" || mode == "phase-lead";
        require(phase || mode == "shared" || mode == "reserved" || mode == "warm" || mode == "critical-first",
                "Unknown arm");
        const std::filesystem::path shaders = argv[4];
        const std::filesystem::path captured = argv[5];
        require(std::filesystem::is_directory(captured) && std::filesystem::is_empty(captured),
                "Expected empty output folder");
        Scene geometry(argv[3]);
        Renderer renderer;
        renderer.start(argv[2]);
        if (!phase) {
            renderer.upload_scene(geometry);
            geometry.release_upload_data();
        }
        renderer.layout_for_scene();
        if (!phase) renderer.descriptors_for_scene();
        renderer.shader(shaders / "vs.spv", renderer.vertex);
        renderer.shader(shaders / "ps.spv", renderer.pixel);
        renderer.preflight(mode == "warm");
        const auto result = measure(renderer, geometry, mode, phase);
        output_frames(captured, result);
        const auto& p = renderer.props;
        std::cout << std::fixed << std::setprecision(5)
                  << "{\"mode\":\"" << mode << "\",\"device\":" << p.deviceID << ",\"driver\":" << p.driverVersion
                  << ",\"api\":" << p.apiVersion << ",\"demand_ms\":" << ms(result.frame - result.request)
                  << ",\"setup_ms\":" << ms(result.schedule - begin)
                  << ",\"entry_ms\":" << ms(result.request - result.schedule)
                  << ",\"startup_to_frame_ms\":" << ms(result.frame - begin)
                  << ",\"schedule_to_drained_ms\":" << ms(result.drained - result.schedule)
                  << ",\"schedule_to_all_frames_ms\":" << ms(result.all_frames - result.schedule)
                  << ",\"upload_begin_ms\":" << (phase ? ms(result.upload_begin - result.request) : 0)
                  << ",\"upload_end_ms\":" << (phase ? ms(result.upload_end - result.request) : 0)
                  << ",\"process_commit_before\":" << result.initial.commit
                  << ",\"process_commit_at_frame\":" << result.first_frame.commit
                  << ",\"process_commit_sampled_peak\":" << result.sampled_max_commit
                  << ",\"lifetime_peak_commit\":" << result.last.peak_commit
                  << ",\"lifetime_peak_working_set\":" << result.last.peak_working_set
                  << ",\"explicit_vk_allocation_total_bytes\":" << renderer.allocated
                  << ",\"active_at_demand\":" << result.active
                  << ",\"triangles_per_frame\":" << result.triangles
                  << ",\"draws_per_frame\":" << geometry.packets.size()
                  << ",\"nonclear_pixels\":[" << result.foreground_pixels[0] << "," << result.foreground_pixels[1]
                  << "," << result.foreground_pixels[2] << "],\"jobs\":[";
        for (unsigned i = 0; i < renderer.builds.size(); ++i) {
            const auto& b = renderer.builds[i];
            require(b.result == VK_SUCCESS && b.handle && (b.feedback.flags & VK_PIPELINE_CREATION_FEEDBACK_VALID_BIT),
                    "Graphics driver did not produce valid creation feedback");
            if (i) std::cout << ",";
            std::cout << "{\"id\":" << i << ",\"preflight\":" << int(b.probe)
                      << ",\"feedback_flags\":" << b.feedback.flags
                      << ",\"feedback_ns\":" << b.feedback.duration
                      << ",\"start_ms\":" << ms(b.start - result.request)
                      << ",\"return_ms\":" << ms(b.end - result.request) << "}";
        }
        std::cout << "]}\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << "\n";
        return 1;
    }
}
