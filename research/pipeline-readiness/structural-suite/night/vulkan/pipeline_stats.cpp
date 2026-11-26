// SPDX-License-Identifier: MIT
// Create one bounded graphics pipeline and retrieve only driver-described metadata.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <psapi.h>
#include <vulkan/vulkan.h>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <filesystem>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {
constexpr uint64_t MiB = 1024ull * 1024;

struct WorkerBudget {
    HANDLE job{};
    ~WorkerBudget() { if (job) CloseHandle(job); }
    void install(uint64_t limit) {
        PERFORMANCE_INFORMATION memory{};
        memory.cb = sizeof(memory);
        if (!GetPerformanceInfo(&memory, sizeof(memory)) || memory.CommitLimit < memory.CommitTotal)
            throw std::runtime_error("Cannot query system commit headroom");
        const auto commit = (memory.CommitLimit - memory.CommitTotal) * memory.PageSize;
        if (commit < limit + 768 * MiB || memory.PhysicalAvailable * memory.PageSize < limit + 512 * MiB)
            throw std::runtime_error("Insufficient system memory headroom for this bounded worker");
        job = CreateJobObjectW(nullptr, nullptr);
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_MEMORY;
        limits.ProcessMemoryLimit = static_cast<SIZE_T>(limit);
        if (!job || !SetInformationJobObject(job, JobObjectExtendedLimitInformation, &limits, sizeof(limits)) ||
            !AssignProcessToJobObject(job, GetCurrentProcess()))
            throw std::runtime_error("Cannot enforce process commitment limit");
    }
};

void check(VkResult result, const char* operation) {
    if (result != VK_SUCCESS)
        throw std::runtime_error(std::string(operation) + " returned " + std::to_string(result));
}

std::string quote(const std::string& s) {
    std::string out = "\"";
    constexpr char hex[] = "0123456789abcdef";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { out += '\\'; out += static_cast<char>(c); }
        else if (c < 32) { out += "\\u00"; out += hex[c >> 4]; out += hex[c & 15]; }
        else out += static_cast<char>(c);
    }
    return out + '"';
}

std::vector<uint32_t> read_module(const char* path) {
    std::ifstream f(path, std::ios::binary | std::ios::ate);
    const auto n = f.tellg();
    if (n < 20 || n > 8 * 1024 * 1024 || n % 4 != 0)
        throw std::runtime_error(std::string("Invalid or oversized SPIR-V module: ") + path);
    std::vector<uint32_t> words(static_cast<size_t>(n) / 4);
    f.seekg(0);
    if (!f.read(reinterpret_cast<char*>(words.data()), n) || words[0] != 0x07230203)
        throw std::runtime_error(std::string("Cannot read SPIR-V module: ") + path);
    return words;
}

VkSubgroupFeatureFlags required_subgroup_ops(const std::vector<uint32_t>& spirv) {
    // SPIR-V OpCapability = 17, GroupNonUniform..GroupNonUniformQuad = 61..68.
    constexpr std::array<VkSubgroupFeatureFlagBits, 8> mapping{
        VK_SUBGROUP_FEATURE_BASIC_BIT, VK_SUBGROUP_FEATURE_VOTE_BIT, VK_SUBGROUP_FEATURE_ARITHMETIC_BIT,
        VK_SUBGROUP_FEATURE_BALLOT_BIT, VK_SUBGROUP_FEATURE_SHUFFLE_BIT, VK_SUBGROUP_FEATURE_SHUFFLE_RELATIVE_BIT,
        VK_SUBGROUP_FEATURE_CLUSTERED_BIT, VK_SUBGROUP_FEATURE_QUAD_BIT};
    VkSubgroupFeatureFlags flags = 0;
    for (size_t i = 5; i < spirv.size();) {
        const auto count = spirv[i] >> 16, opcode = spirv[i] & 0xffffu;
        if (!count || count > spirv.size() - i) throw std::runtime_error("Malformed SPIR-V instruction length");
        if (opcode == 17 && count == 2 && spirv[i + 1] >= 61 && spirv[i + 1] <= 68)
            flags |= mapping[spirv[i + 1] - 61];
        i += count;
    }
    return flags;
}

template<typename T, typename F>
std::vector<T> enumerate(const T& prototype, F call, const char* name) {
    for (unsigned attempt = 0; attempt < 3; ++attempt) {
        uint32_t count = 0;
        check(call(&count, nullptr), name);
        if (count > 4096) throw std::runtime_error(std::string("Enumeration limit: ") + name);
        if (!count) return {};
        std::vector<T> values(count, prototype);
        auto result = call(&count, values.data());
        if (result == VK_INCOMPLETE) continue;
        check(result, name);
        values.resize(count);
        return values;
    }
    throw std::runtime_error(std::string("Unstable enumeration: ") + name);
}

struct Pipeline {
    VkInstance instance{};
    VkDevice device{};
    VkRenderPass render_pass{};
    VkPipelineLayout layout{};
    VkDescriptorSetLayout image_set{};
    std::array<VkShaderModule, 2> shaders{};
    VkPipeline handle{};
    ~Pipeline() {
        if (device) {
            if (handle) vkDestroyPipeline(device, handle, nullptr);
            for (auto module : shaders) if (module) vkDestroyShaderModule(device, module, nullptr);
            if (layout) vkDestroyPipelineLayout(device, layout, nullptr);
            if (image_set) vkDestroyDescriptorSetLayout(device, image_set, nullptr);
            if (render_pass) vkDestroyRenderPass(device, render_pass, nullptr);
            vkDestroyDevice(device, nullptr);
        }
        if (instance) vkDestroyInstance(instance, nullptr);
    }
};

template<typename T>
T command(VkDevice device, const char* name) {
    auto p = vkGetDeviceProcAddr(device, name);
    if (!p) throw std::runtime_error(std::string("Missing extension command: ") + name);
    return reinterpret_cast<T>(p);
}

#include "ray_draw.inl"

void report_executables(std::ostream& out, const Pipeline& p) {
    auto properties = command<PFN_vkGetPipelineExecutablePropertiesKHR>(p.device, "vkGetPipelineExecutablePropertiesKHR");
    auto statistics = command<PFN_vkGetPipelineExecutableStatisticsKHR>(p.device, "vkGetPipelineExecutableStatisticsKHR");
    auto representations = command<PFN_vkGetPipelineExecutableInternalRepresentationsKHR>(p.device, "vkGetPipelineExecutableInternalRepresentationsKHR");
    VkPipelineInfoKHR pipeline_info{VK_STRUCTURE_TYPE_PIPELINE_INFO_KHR};
    pipeline_info.pipeline = p.handle;
    auto units = enumerate(VkPipelineExecutablePropertiesKHR{VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_PROPERTIES_KHR},
        [&](auto n, auto v) { return properties(p.device, &pipeline_info, n, v); }, "executable properties");
    out << "[";
    for (uint32_t i = 0; i < units.size(); ++i) {
        if (i) out << ",";
        const auto& unit = units[i];
        VkPipelineExecutableInfoKHR info{VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_INFO_KHR};
        info.pipeline = p.handle;
        info.executableIndex = i;
        auto stats = enumerate(VkPipelineExecutableStatisticKHR{VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_STATISTIC_KHR},
            [&](auto n, auto v) { return statistics(p.device, &info, n, v); }, "statistics");
        auto reps = enumerate(VkPipelineExecutableInternalRepresentationKHR{VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_INTERNAL_REPRESENTATION_KHR},
            [&](auto n, auto v) { return representations(p.device, &info, n, v); }, "representations");
        out << "{\"index\":" << i << ",\"name\":" << quote(unit.name) << ",\"description\":" << quote(unit.description)
            << ",\"stage_flags\":" << unit.stages << ",\"subgroup_size\":" << unit.subgroupSize << ",\"statistics\":[";
        for (size_t s = 0; s < stats.size(); ++s) {
            if (s) out << ",";
            const auto& v = stats[s];
            out << "{\"name\":" << quote(v.name) << ",\"description\":" << quote(v.description) << ",\"format\":" << v.format << ",\"value\":";
            switch (v.format) {
                case VK_PIPELINE_EXECUTABLE_STATISTIC_FORMAT_BOOL32_KHR: out << (v.value.b32 ? "true" : "false"); break;
                case VK_PIPELINE_EXECUTABLE_STATISTIC_FORMAT_INT64_KHR: out << v.value.i64; break;
                case VK_PIPELINE_EXECUTABLE_STATISTIC_FORMAT_UINT64_KHR: out << v.value.u64; break;
                case VK_PIPELINE_EXECUTABLE_STATISTIC_FORMAT_FLOAT64_KHR: out.precision(17); out << v.value.f64; break;
                default: throw std::runtime_error("Unknown statistic type");
            }
            out << "}";
        }
        out << "],\"internal_representations\":[";
        for (size_t r = 0; r < reps.size(); ++r) {
            if (r) out << ",";
            const auto& rep = reps[r];
            out << "{\"name\":" << quote(rep.name) << ",\"description\":" << quote(rep.description)
                << ",\"is_text\":" << (rep.isText ? "true" : "false") << ",\"reported_data_bytes\":" << rep.dataSize << "}";
        }
        out << "]}";
    }
    out << "]";
}

void run(const char* vertex_path, const char* fragment_path, const char* requested_device, std::string_view profile,
         const DrawRequest* draw) {
    const bool native_nerf = profile == "source-nerf";
    if (profile != "source" && !native_nerf && profile != "xcl-ray-roots" && profile != "xcl-nerf-roots")
        throw std::runtime_error("Unknown pipeline layout profile");
    const bool translated = profile == "xcl-ray-roots" || profile == "xcl-nerf-roots";
    const bool bindless = profile == "xcl-nerf-roots";
    const bool capture = !draw || draw->capture;
    if (draw && bindless) throw std::runtime_error("Draw supports only the reviewed procedural ray scene");
    const uint64_t worker_limit = (translated ? 2048ull : 512ull) * MiB;
    WorkerBudget budget;
    budget.install(worker_limit);
    auto vert = read_module(vertex_path);
    auto frag = read_module(fragment_path);
    Pipeline p;
    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    app.pApplicationName = "PortBridge pipeline executable audit";
    app.apiVersion = VK_API_VERSION_1_3;
    VkInstanceCreateInfo instance_info{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    instance_info.pApplicationInfo = &app;
    check(vkCreateInstance(&instance_info, nullptr, &p.instance), "vkCreateInstance");
    auto adapters = enumerate(VkPhysicalDevice{},
        [&](auto n, auto v) { return vkEnumeratePhysicalDevices(p.instance, n, v); }, "adapters");
    VkPhysicalDevice physical{};
    VkPhysicalDeviceProperties props{};
    for (auto candidate : adapters) {
        VkPhysicalDeviceProperties current{};
        vkGetPhysicalDeviceProperties(candidate, &current);
        if (std::strcmp(current.deviceName, requested_device) == 0) { physical = candidate; props = current; break; }
    }
    if (!physical || props.apiVersion < VK_API_VERSION_1_3)
        throw std::runtime_error("Requested Vulkan 1.3 adapter unavailable");
    auto extensions = enumerate(VkExtensionProperties{},
        [&](auto n, auto v) { return vkEnumerateDeviceExtensionProperties(physical, nullptr, n, v); }, "device extensions");
    const char* extension = VK_KHR_PIPELINE_EXECUTABLE_PROPERTIES_EXTENSION_NAME;
    bool available = false;
    for (const auto& e : extensions) available |= std::strcmp(e.extensionName, extension) == 0;
    if (capture && !available) throw std::runtime_error("VK_KHR_pipeline_executable_properties unavailable");
    VkPhysicalDevicePipelineExecutablePropertiesFeaturesKHR executable{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PIPELINE_EXECUTABLE_PROPERTIES_FEATURES_KHR};
    VkPhysicalDeviceVulkan12Features observed12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};
    VkPhysicalDeviceVulkan13Features observed13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES};
    executable.pNext = &observed12; observed12.pNext = &observed13;
    VkPhysicalDeviceFeatures2 features{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2};
    features.pNext = available ? static_cast<void*>(&executable) : static_cast<void*>(&observed12);
    vkGetPhysicalDeviceFeatures2(physical, &features);
    if (capture && !executable.pipelineExecutableInfo) throw std::runtime_error("pipelineExecutableInfo feature unavailable");
    if (translated && (!observed12.vulkanMemoryModel || !observed12.bufferDeviceAddress || !observed13.shaderDemoteToHelperInvocation))
        throw std::runtime_error("Converted module needs Vulkan memory model, buffer device address and shader demote");
    if (bindless && (!observed12.runtimeDescriptorArray || !observed12.shaderSampledImageArrayNonUniformIndexing ||
        !features.features.shaderInt64 || !features.features.shaderSampledImageArrayDynamicIndexing))
        throw std::runtime_error("Converted bindless module requires unsupported indexing or int64");
    if (native_nerf && (!observed12.runtimeDescriptorArray || !observed12.shaderUniformBufferArrayNonUniformIndexing ||
                       !features.features.shaderUniformBufferArrayDynamicIndexing))
        throw std::runtime_error("Mobile NeRF needs nonuniform UBO array indexing");
    VkPhysicalDeviceSubgroupProperties subgroup{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_PROPERTIES};
    VkPhysicalDeviceProperties2 physical_props{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2};
    physical_props.pNext = &subgroup;
    vkGetPhysicalDeviceProperties2(physical, &physical_props);
    const auto subgroup_ops = required_subgroup_ops(frag);
    if (subgroup_ops && (!(subgroup.supportedStages & VK_SHADER_STAGE_FRAGMENT_BIT) ||
        (subgroup.supportedOperations & subgroup_ops) != subgroup_ops))
        throw std::runtime_error("Device lacks subgroup features used by this fragment module");
    VkPhysicalDeviceVulkan12Features enabled12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};
    VkPhysicalDeviceVulkan13Features enabled13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES};
    VkPhysicalDeviceFeatures enabled{};
    executable.pNext = &enabled12; enabled12.pNext = &enabled13;
    enabled12.vulkanMemoryModel = translated;
    enabled12.bufferDeviceAddress = translated;
    enabled13.shaderDemoteToHelperInvocation = translated;
    enabled12.runtimeDescriptorArray = bindless || native_nerf;
    enabled12.shaderUniformBufferArrayNonUniformIndexing = native_nerf;
    enabled.shaderUniformBufferArrayDynamicIndexing = native_nerf;
    enabled12.shaderSampledImageArrayNonUniformIndexing = bindless;
    enabled.shaderInt64 = bindless;
    enabled.shaderSampledImageArrayDynamicIndexing = bindless;
    uint32_t count = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, nullptr);
    if (!count || count > 256) throw std::runtime_error("Unexpected queue-family count");
    std::vector<VkQueueFamilyProperties> families(count);
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, families.data());
    uint32_t family = 0;
    while (family < count && !(families[family].queueFlags & VK_QUEUE_GRAPHICS_BIT)) ++family;
    if (family == count) throw std::runtime_error("No graphics queue");
    float priority = 1.f;
    VkDeviceQueueCreateInfo queue_info{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
    queue_info.queueFamilyIndex = family;
    queue_info.queueCount = 1;
    queue_info.pQueuePriorities = &priority;
    VkDeviceCreateInfo device_info{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
    device_info.pNext = capture ? static_cast<void*>(&executable) : static_cast<void*>(&enabled12);
    device_info.pEnabledFeatures = &enabled;
    device_info.queueCreateInfoCount = 1;
    device_info.pQueueCreateInfos = &queue_info;
    device_info.enabledExtensionCount = capture ? 1u : 0u;
    device_info.ppEnabledExtensionNames = capture ? &extension : nullptr;
    check(vkCreateDevice(physical, &device_info, nullptr, &p.device), "vkCreateDevice");

    VkPushConstantRange push{VK_SHADER_STAGE_FRAGMENT_BIT, 0, translated ? 40u : 64u};
    VkPipelineLayoutCreateInfo layout_info{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    layout_info.pushConstantRangeCount = 1;
    layout_info.pPushConstantRanges = &push;
    if (native_nerf) {
        layout_info.pushConstantRangeCount = 0;
        std::array<VkDescriptorSetLayoutBinding, 5> bindings{};
        for (uint32_t i = 0; i < 4; ++i)
            bindings[i] = {i, VK_DESCRIPTOR_TYPE_INPUT_ATTACHMENT, 1, VK_SHADER_STAGE_FRAGMENT_BIT, nullptr};
        bindings[4] = {4, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 4, VK_SHADER_STAGE_FRAGMENT_BIT, nullptr};
        VkDescriptorSetLayoutCreateInfo ds{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
        ds.bindingCount = 5; ds.pBindings = bindings.data();
        check(vkCreateDescriptorSetLayout(p.device, &ds, nullptr, &p.image_set), "NeRF source set layout");
        layout_info.setLayoutCount = 1; layout_info.pSetLayouts = &p.image_set;
    }
    if (bindless) {
        if (props.limits.maxPerStageDescriptorSampledImages < 64 || props.limits.maxDescriptorSetSampledImages < 64)
            throw std::runtime_error("Requested sampled image array exceeds device limits");
        VkDescriptorSetLayoutBinding images{0, VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE, 64, VK_SHADER_STAGE_FRAGMENT_BIT, nullptr};
        VkDescriptorSetLayoutCreateInfo ds{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
        ds.bindingCount = 1; ds.pBindings = &images;
        check(vkCreateDescriptorSetLayout(p.device, &ds, nullptr, &p.image_set), "bindless image set layout");
        layout_info.setLayoutCount = 1;
        layout_info.pSetLayouts = &p.image_set;
    }
    check(vkCreatePipelineLayout(p.device, &layout_info, nullptr, &p.layout), "vkCreatePipelineLayout");
    VkAttachmentDescription color{};
    color.format = VK_FORMAT_R32G32B32A32_SFLOAT;
    color.samples = VK_SAMPLE_COUNT_1_BIT;
    color.loadOp = draw ? VK_ATTACHMENT_LOAD_OP_CLEAR : VK_ATTACHMENT_LOAD_OP_DONT_CARE;
    color.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
    color.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    color.finalLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
    VkAttachmentReference attachment{0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
    VkSubpassDescription subpass{};
    subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
    subpass.colorAttachmentCount = 1;
    subpass.pColorAttachments = &attachment;
    VkRenderPassCreateInfo pass{VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO};
    pass.attachmentCount = 1; pass.pAttachments = &color;
    pass.subpassCount = 1; pass.pSubpasses = &subpass;
    std::array<VkAttachmentDescription, 5> attachments{color};
    std::array<VkAttachmentReference, 4> input_refs{};
    if (native_nerf) {
        for (uint32_t i = 0; i < 4; ++i) {
            auto& input = attachments[i + 1];
            input.format = i == 3 ? VK_FORMAT_R32_UINT : VK_FORMAT_R32G32B32A32_SFLOAT;
            input.samples = VK_SAMPLE_COUNT_1_BIT;
            input.loadOp = VK_ATTACHMENT_LOAD_OP_LOAD; input.storeOp = VK_ATTACHMENT_STORE_OP_NONE;
            input.stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
            input.stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
            input.initialLayout = input.finalLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
            input_refs[i] = {i + 1, input.initialLayout};
        }
        subpass.inputAttachmentCount = 4; subpass.pInputAttachments = input_refs.data();
        pass.attachmentCount = 5; pass.pAttachments = attachments.data();
    }
    check(vkCreateRenderPass(p.device, &pass, nullptr, &p.render_pass), "vkCreateRenderPass");
    std::array<VkPipelineShaderStageCreateInfo, 2> stages{};
    for (size_t i = 0; i < stages.size(); ++i) {
        const auto& source = i == 0 ? vert : frag;
        VkShaderModuleCreateInfo mod{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
        mod.codeSize = source.size() * sizeof(uint32_t); mod.pCode = source.data();
        check(vkCreateShaderModule(p.device, &mod, nullptr, &p.shaders[i]), "vkCreateShaderModule");
        stages[i].sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        stages[i].stage = i == 0 ? VK_SHADER_STAGE_VERTEX_BIT : VK_SHADER_STAGE_FRAGMENT_BIT;
        stages[i].module = p.shaders[i]; stages[i].pName = "main";
    }
    VkPipelineVertexInputStateCreateInfo inputs{VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
    VkPipelineInputAssemblyStateCreateInfo assembly{VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO};
    assembly.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
    VkExtent2D extent = draw ? draw->extent : VkExtent2D{16, 16};
    VkViewport vp{0, 0, static_cast<float>(extent.width), static_cast<float>(extent.height), 0, 1};
    VkRect2D scissor{{0, 0}, extent};
    VkPipelineViewportStateCreateInfo viewport{VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO};
    viewport.viewportCount = 1; viewport.pViewports = &vp;
    viewport.scissorCount = 1; viewport.pScissors = &scissor;
    VkPipelineRasterizationStateCreateInfo raster{VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO};
    raster.lineWidth = 1.f; raster.frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE;
    VkPipelineMultisampleStateCreateInfo ms{VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO};
    ms.rasterizationSamples = VK_SAMPLE_COUNT_1_BIT;
    VkPipelineColorBlendAttachmentState dest{};
    dest.colorWriteMask = 15;
    VkPipelineColorBlendStateCreateInfo blend{VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO};
    blend.attachmentCount = 1; blend.pAttachments = &dest;
    VkGraphicsPipelineCreateInfo info{VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};
    if (capture) info.flags = VK_PIPELINE_CREATE_CAPTURE_STATISTICS_BIT_KHR | VK_PIPELINE_CREATE_CAPTURE_INTERNAL_REPRESENTATIONS_BIT_KHR;
    info.stageCount = 2; info.pStages = stages.data();
    info.pVertexInputState = &inputs; info.pInputAssemblyState = &assembly; info.pViewportState = &viewport;
    info.pRasterizationState = &raster; info.pMultisampleState = &ms; info.pColorBlendState = &blend;
    info.layout = p.layout; info.renderPass = p.render_pass;
    auto start = std::chrono::steady_clock::now();
    check(vkCreateGraphicsPipelines(p.device, VK_NULL_HANDLE, 1, &info, nullptr, &p.handle), "vkCreateGraphicsPipelines");
    auto us = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - start).count();
    std::ostringstream out;
    out << "{\"adapter\":" << quote(props.deviceName) << ",\"device_id\":" << props.deviceID << ",\"vendor_id\":" << props.vendorID
        << ",\"layout_profile\":" << quote(std::string(profile)) << ",\"subgroup_size\":" << subgroup.subgroupSize
        << ",\"driver_version_raw\":" << props.driverVersion << ",\"api_version_raw\":" << props.apiVersion
        << ",\"vertex_spirv_bytes\":" << vert.size() * 4 << ",\"fragment_spirv_bytes\":" << frag.size() * 4
        << ",\"pipeline_create_us\":" << us << ",\"capture_statistics\":" << (capture ? "true" : "false");
    if (draw) {
        draw_ray(out, p, physical, family, families[family].timestampValidBits, props.limits.timestampPeriod, extent, *draw, translated, native_nerf);
    }
    if (capture) {
        out << ",\"pipeline_create_with_capture_us\":" << us << ",\"executables\":";
        report_executables(out, p);
    }
    PROCESS_MEMORY_COUNTERS_EX mem{};
    mem.cb = sizeof(mem);
    if (!GetProcessMemoryInfo(GetCurrentProcess(), reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&mem), sizeof(mem)))
        throw std::runtime_error("Cannot read process memory counters");
    out << ",\"worker_commit_limit_bytes\":" << worker_limit << ",\"worker_peak_commit_bytes\":" << mem.PeakPagefileUsage
        << ",\"worker_peak_working_set_bytes\":" << mem.PeakWorkingSetSize << "}";
    std::cout << out.str() << "\n";
}
}

int main(int argc, char** argv) {
    if (argc != 5 && argc != 8 && argc != 9) {
        std::cerr << "Usage: pipeline_stats vertex.spv fragment.spv \"device name\" profile [512-byte-sgprs image.rgba32f extent [capture]]\n";
        return 2;
    }
    try {
        DrawRequest draw{};
        if (argc >= 8) {
            draw.registers = argv[5]; draw.output = argv[6];
            if (std::string_view(argv[7]) == "16x16") draw.extent = {16, 16};
            else if (std::string_view(argv[7]) == "96x96") draw.extent = {96, 96};
            else if (std::string_view(argv[7]) == "320x180") draw.extent = {320, 180};
            else if (std::string_view(argv[7]) != "800x450") throw std::runtime_error("Unsupported draw extent");
            if (argc == 9 && std::string_view(argv[8]) != "capture") throw std::runtime_error("Unknown draw option");
            draw.capture = argc == 9;
        }
        run(argv[1], argv[2], argv[3], argv[4], argc >= 8 ? &draw : nullptr);
    }
    catch (const std::exception& e) { std::cerr << e.what() << "\n"; return 1; }
}
