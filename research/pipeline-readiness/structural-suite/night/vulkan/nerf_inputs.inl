// SPDX-License-Identifier: MIT
// Resources for the unmodified Khronos Mobile NeRF fragment pass.
struct NeRFInputs {
    VkDevice device;
    struct Attachment {
        VkImage image{};
        VkDeviceMemory memory{};
        VkImageView view{};
        RayBuffer staging{};
    };
    std::array<Attachment, 4> inputs{};
    std::array<RayBuffer, 4> networks{};
    VkImageView signed_indices{};
    VkDescriptorPool pool{};
    VkDescriptorSet set{};

    ~NeRFInputs() {
        if (signed_indices) vkDestroyImageView(device, signed_indices, nullptr);
        if (pool) vkDestroyDescriptorPool(device, pool, nullptr);
        for (auto& a : inputs) {
            if (a.view) vkDestroyImageView(device, a.view, nullptr);
            if (a.image) vkDestroyImage(device, a.image, nullptr);
            if (a.memory) vkFreeMemory(device, a.memory, nullptr);
            if (a.staging.buffer) vkDestroyBuffer(device, a.staging.buffer, nullptr);
            if (a.staging.memory) vkFreeMemory(device, a.staging.memory, nullptr);
        }
        for (auto& b : networks) {
            if (b.buffer) vkDestroyBuffer(device, b.buffer, nullptr);
            if (b.memory) vkFreeMemory(device, b.memory, nullptr);
        }
    }

    static std::vector<uint32_t> read_words(const std::filesystem::path& path, size_t count) {
        std::ifstream in(path, std::ios::binary | std::ios::ate);
        if (in.tellg() != static_cast<std::streamoff>(count * 4))
            throw std::runtime_error("Unexpected input byte count for " + path.filename().string());
        std::vector<uint32_t> result(count);
        in.seekg(0);
        if (!in.read(reinterpret_cast<char*>(result.data()), static_cast<std::streamsize>(count * 4)))
            throw std::runtime_error("Incomplete Mobile NeRF input");
        return result;
    }

    void fill(const RayBuffer& b, const uint32_t* data, size_t words) const {
        void* mapping{};
        check(vkMapMemory(device, b.memory, 0, words * 4, 0, &mapping), "map Mobile NeRF input");
        std::memcpy(mapping, data, words * 4);
        vkUnmapMemory(device, b.memory);
    }

    void prepare(RayResources& r, VkDescriptorSetLayout layout, const std::filesystem::path& dir, VkExtent2D extent, bool sampled) {
        constexpr size_t network_words = 532;
        const auto weights = read_words(dir / "weights.bin", 4 * network_words);
        const std::array<const char*, 4> names{"features0.rgba32f", "features1.rgba32f", "direction.rgba32f", "indices.r32u"};
        std::array<VkDescriptorImageInfo, 4> images{};
        std::array<VkDescriptorBufferInfo, 4> buffers{};
        for (size_t i = 0; i < 4; ++i) {
            if (!sampled) {
                r.make_buffer(networks[i], network_words * 4, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT);
                fill(networks[i], weights.data() + network_words * i, network_words);
                buffers[i] = {networks[i].buffer, 0, network_words * 4};
            }

            const size_t words = size_t(extent.width) * extent.height * (i == 3 ? 1 : 4);
            const auto data = read_words(dir / names[i], words);
            if (i == 3) {
                for (auto index : data)
                    if (index >= 4) throw std::runtime_error("Descriptor index exceeds four networks");
            }
            auto& a = inputs[i];
            r.make_buffer(a.staging, words * 4, VK_BUFFER_USAGE_TRANSFER_SRC_BIT);
            fill(a.staging, data.data(), words);
            VkImageCreateInfo ic{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
            ic.imageType = VK_IMAGE_TYPE_2D;
            ic.format = i == 3 ? VK_FORMAT_R32_UINT : VK_FORMAT_R32G32B32A32_SFLOAT;
            ic.extent = {extent.width, extent.height, 1};
            ic.mipLevels = ic.arrayLayers = 1; ic.samples = VK_SAMPLE_COUNT_1_BIT;
            ic.tiling = VK_IMAGE_TILING_OPTIMAL;
            ic.usage = (sampled ? VK_IMAGE_USAGE_SAMPLED_BIT : VK_IMAGE_USAGE_INPUT_ATTACHMENT_BIT) | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
            if (sampled && i == 3) ic.flags = VK_IMAGE_CREATE_MUTABLE_FORMAT_BIT;
            VkImageFormatProperties supported{};
            check(vkGetPhysicalDeviceImageFormatProperties(r.physical, ic.format, ic.imageType, ic.tiling,
                ic.usage, ic.flags, &supported), "support for Mobile NeRF attachment format");
            check(vkCreateImage(device, &ic, nullptr, &a.image), "create Mobile NeRF input image");
            VkMemoryRequirements req{};
            vkGetImageMemoryRequirements(device, a.image, &req);
            a.memory = r.allocate(req, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, false);
            check(vkBindImageMemory(device, a.image, a.memory, 0), "bind Mobile NeRF input image");
            VkImageViewCreateInfo view{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
            view.image = a.image; view.viewType = VK_IMAGE_VIEW_TYPE_2D; view.format = ic.format;
            view.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
            check(vkCreateImageView(device, &view, nullptr, &a.view), "create Mobile NeRF input view");
            images[i] = {VK_NULL_HANDLE, a.view, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
            if (sampled && i == 3) {
                view.format = VK_FORMAT_R32_SINT;
                VkFormatProperties props{};
                vkGetPhysicalDeviceFormatProperties(r.physical, view.format, &props);
                if (!(props.optimalTilingFeatures & VK_FORMAT_FEATURE_SAMPLED_IMAGE_BIT))
                    throw std::runtime_error("Missing R32_SINT sampled format");
                check(vkCreateImageView(device, &view, nullptr, &signed_indices), "create signed index view");
            }
        }
        const VkDescriptorPoolSize sizes[]{{VK_DESCRIPTOR_TYPE_INPUT_ATTACHMENT, 4}, {VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 4}};
        VkDescriptorPoolCreateInfo pc{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
        VkDescriptorPoolSize typed_size{VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE, 24};
        pc.maxSets = 1; pc.poolSizeCount = sampled ? 1 : 2; pc.pPoolSizes = sampled ? &typed_size : sizes;
        check(vkCreateDescriptorPool(device, &pc, nullptr, &pool), "create Mobile NeRF descriptor pool");
        VkDescriptorSetAllocateInfo alloc{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
        alloc.descriptorPool = pool; alloc.descriptorSetCount = 1; alloc.pSetLayouts = &layout;
        check(vkAllocateDescriptorSets(device, &alloc, &set), "allocate Mobile NeRF descriptor set");
        if (sampled) {
            std::array<std::array<VkDescriptorImageInfo, 8>, 3> typed{};
            typed[0].fill(images[3]);  // unsigned
            typed[1].fill({VK_NULL_HANDLE, signed_indices, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL});
            typed[2].fill(images[0]);  // floating point
            for (size_t i = 0; i < 3; ++i) typed[2][2 * i] = images[i];
            for (uint32_t b = 0; b < typed.size(); ++b) {
                VkWriteDescriptorSet write{VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET};
                write.dstSet = set; write.dstBinding = b; write.descriptorType = VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE;
                write.descriptorCount = static_cast<uint32_t>(typed[b].size()); write.pImageInfo = typed[b].data();
                vkUpdateDescriptorSets(device, 1, &write, 0, nullptr);
            }
            return;
        }
        std::array<VkWriteDescriptorSet, 5> writes{};
        for (uint32_t i = 0; i < writes.size(); ++i) {
            auto& w = writes[i];
            w.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET; w.dstSet = set; w.dstBinding = i;
            w.descriptorCount = i == 4 ? 4 : 1;
            if (i == 4) { w.descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER; w.pBufferInfo = buffers.data(); }
            else { w.descriptorType = VK_DESCRIPTOR_TYPE_INPUT_ATTACHMENT; w.pImageInfo = &images[i]; }
        }
        vkUpdateDescriptorSets(device, static_cast<uint32_t>(writes.size()), writes.data(), 0, nullptr);
    }

    void upload(VkCommandBuffer cmd, VkExtent2D extent) const {
        for (const auto& a : inputs) {
            VkImageMemoryBarrier b{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
            b.image = a.image; b.srcQueueFamilyIndex = b.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
            b.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
            b.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED; b.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
            b.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
            vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                0, 0, nullptr, 0, nullptr, 1, &b);
            VkBufferImageCopy copy{};
            copy.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
            copy.imageExtent = {extent.width, extent.height, 1};
            vkCmdCopyBufferToImage(cmd, a.staging.buffer, a.image, b.newLayout, 1, &copy);
            b.oldLayout = b.newLayout; b.newLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
            b.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
            b.dstAccessMask = VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_INPUT_ATTACHMENT_READ_BIT | VK_ACCESS_COLOR_ATTACHMENT_READ_BIT;
            vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT,
                VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT | VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
                0, 0, nullptr, 0, nullptr, 1, &b);
        }
    }
};
