// Reuse the readback test device, buffers and synchronization helpers.
// Its executable entry point is unused in this correctness test.
#define main portbridge_readback_unused_main
#include "../../readback-epochs/replay_vulkan.cpp"
#undef main

static constexpr uint32_t sentinel = 0xba5eb411;

struct Point {
    uint32_t id;
    uint32_t value;
    bool live;
};

static std::vector<Point> load_points(const char *path)
{
    std::ifstream input(path);
    uint32_t count{};
    require(bool(input >> count) && count >= 1 && count <= 4096, "invalid row count");
    std::vector<Point> points(count);
    for (auto &point : points) {
        uint32_t live{};
        require(bool(input >> point.id >> point.value >> live) && live <= 1,
                "invalid point row");
        point.live = live != 0;
    }
    std::string trailing;
    require(!(input >> trailing), "unexpected trailing input");
    return points;
}

static VkPipeline create_other_pipeline(const Replay &replay, const char *path)
{
    std::ifstream file(path, std::ios::ate | std::ios::binary);
    const std::streamoff size = file.tellg();
    require(size >= 20 && size % 4 == 0, "invalid observation SPIR-V length");
    std::vector<uint32_t> code(static_cast<size_t>(size / 4));
    file.seekg(0);
    require(bool(file.read(reinterpret_cast<char *>(code.data()), size)) &&
            code.front() == 0x07230203u, "cannot read observation SPIR-V");
    auto module_info = vk_structure<VkShaderModuleCreateInfo>(VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO);
    module_info.codeSize = static_cast<size_t>(size);
    module_info.pCode = code.data();
    VkShaderModule module{};
    check(vkCreateShaderModule(replay.device, &module_info, nullptr, &module), "vkCreateShaderModule");
    auto info = vk_structure<VkComputePipelineCreateInfo>(VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO);
    info.stage = vk_structure<VkPipelineShaderStageCreateInfo>(VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO);
    info.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
    info.stage.module = module;
    info.stage.pName = "main";
    info.layout = replay.pipeline_layout;
    VkPipeline pipeline{};
    const auto result = vkCreateComputePipelines(replay.device, VK_NULL_HANDLE, 1, &info, nullptr, &pipeline);
    vkDestroyShaderModule(replay.device, module, nullptr);
    check(result, "vkCreateComputePipelines observation");
    return pipeline;
}

struct PipelineHandle {
    VkDevice device;
    VkPipeline pipeline;

    ~PipelineHandle() { vkDestroyPipeline(device, pipeline, nullptr); }
};

static void validation(const char *input_path, const char *filter_spv, const char *observe_spv,
                       std::string_view adapter, bool physical_index)
{
    const auto points = load_points(input_path);
    const auto count = static_cast<uint32_t>(points.size());
    const uint32_t words = (count + 31) / 32;
    const uint32_t first_mask = 2 * count;
    const uint32_t initial_size = first_mask + words;
    const uint32_t first_observation = first_mask + 4 * words;
    const uint32_t full_size = first_observation + 4 * count;
    const VkDeviceSize byte_count = static_cast<VkDeviceSize>(full_size) * 4;
    const VkDeviceSize upload = static_cast<VkDeviceSize>(initial_size) * 4;
    std::vector<uint32_t> initial(initial_size, 0);
    std::vector<uint32_t> dense;
    for (uint32_t i = 0; i < count; ++i) {
        initial[i] = points[i].id;
        initial[count + i] = points[i].value;
        if (points[i].live) {
            initial[first_mask + i / 32] |= 1u << (i % 32);
            dense.push_back(i);
        }
    }

    Replay replay;
    replay.initialize(filter_spv, byte_count, {byte_count, 4, 4}, adapter);
    const PipelineHandle observer{replay.device, create_other_pipeline(replay, observe_spv)};
    const auto &slot = replay.slots.front();
    replay.begin(slot);
    vkCmdUpdateBuffer(slot.command, replay.source.handle, 0, upload, initial.data());
    vkCmdFillBuffer(slot.command, replay.source.handle, upload, byte_count - upload, sentinel);
    barrier(slot.command, replay.source.handle, VK_PIPELINE_STAGE_TRANSFER_BIT,
            VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_ACCESS_TRANSFER_WRITE_BIT,
            VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT);
    vkCmdBindDescriptorSets(slot.command, VK_PIPELINE_BIND_POINT_COMPUTE, replay.pipeline_layout,
                            0, 1, &replay.descriptor, 0, nullptr);
    const auto dispatch = [&](VkPipeline pipeline, uint32_t operation, uint32_t groups) {
        vkCmdBindPipeline(slot.command, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline);
        const PushConstants command{count, operation, physical_index ? 1u : 0u};
        vkCmdPushConstants(slot.command, replay.pipeline_layout, VK_SHADER_STAGE_COMPUTE_BIT,
                           0, sizeof(command), &command);
        vkCmdDispatch(slot.command, groups, 1, 1);
        barrier(slot.command, replay.source.handle, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_ACCESS_SHADER_WRITE_BIT,
                VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT);
    };
    for (uint32_t stage = 0; stage < 2; ++stage) {
        dispatch(replay.pipeline, stage * 3, 1);
        dispatch(replay.pipeline, stage * 3 + 1, words);
        dispatch(replay.pipeline, stage * 3 + 2, 1);
        dispatch(observer.pipeline, stage, words);
    }
    barrier(slot.command, replay.source.handle,
            VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT | VK_PIPELINE_STAGE_TRANSFER_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT, VK_ACCESS_SHADER_WRITE_BIT | VK_ACCESS_TRANSFER_WRITE_BIT,
            VK_ACCESS_TRANSFER_READ_BIT);
    const VkBufferCopy copy{0, 0, byte_count};
    vkCmdCopyBuffer(slot.command, replay.source.handle, slot.staging.handle, 1, &copy);
    barrier(slot.command, slot.staging.handle, VK_PIPELINE_STAGE_TRANSFER_BIT,
            VK_PIPELINE_STAGE_HOST_BIT, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_HOST_READ_BIT);
    replay.submit(slot);
    replay.wait(slot);

    std::cout << replay.properties.deviceName << " Vulkan " << VK_VERSION_MAJOR(replay.properties.apiVersion)
              << '.' << VK_VERSION_MINOR(replay.properties.apiVersion) << '.'
              << VK_VERSION_PATCH(replay.properties.apiVersion) << '\n';
    require(std::equal(initial.begin(), initial.end(), slot.mapped), "immutable source changed");
    for (uint32_t stage = 0; stage < 2; ++stage) {
        std::vector<uint32_t> filtered;
        for (uint32_t rank = 0; rank < static_cast<uint32_t>(dense.size()); ++rank) {
            const auto i = dense[rank];
            const auto value = points[i].value;
            const bool selected = stage == 0 ? (value + 2 * rank) % 7 < 4
                                             : (3 * value + rank) % 5 != 1;
            if (selected) filtered.push_back(i);
        }
        dense = std::move(filtered);
        std::vector<uint32_t> expected_mask(words, 0);
        for (auto i : dense) expected_mask[i / 32] |= 1u << (i % 32);
        const auto offset = first_mask + (stage + 1) * words;
        require(std::equal(expected_mask.begin(), expected_mask.end(), slot.mapped + offset),
                stage == 0 ? "first mask differs from stable compact reference"
                           : "second mask differs from stable compact reference");
        const auto out_start = stage == 0 ? 5u : 2u;
        const auto out_len = stage == 0 ? 7u : count / 2;
        size_t observed{};
        for (uint32_t i = 0; i < count; ++i) {
            const bool in_window = i < out_len && i + out_start < dense.size();
            const uint32_t id = in_window ? points[dense[i + out_start]].id : sentinel;
            const uint32_t value = in_window ? points[dense[i + out_start]].value : sentinel;
            const auto pos = first_observation + 2 * (stage * count + i);
            require(slot.mapped[pos] == id && slot.mapped[pos + 1] == value,
                    "ordered observation differs or unrequested row was written");
            observed += in_window;
        }
        std::cout << "stage=" << stage + 1 << " survivors=" << dense.size()
                  << " observed=" << observed << '\n';
    }
    std::cout << count << " slots, " << words << " leaf words, both ordered frontiers exact\n";
}

int main(int argc, char **argv)
{
    try {
        require(argc == 5 || (argc == 6 && std::string_view(argv[5]) == "--physical-index"),
                "usage: validate-rank filter.spv observe.spv points.txt device-substring [--physical-index]");
        validation(argv[3], argv[1], argv[2], argv[4], argc == 6);
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
