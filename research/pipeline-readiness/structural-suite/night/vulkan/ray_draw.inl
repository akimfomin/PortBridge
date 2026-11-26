// SPDX-License-Identifier: MIT
// Vulkan draw path shared with pipeline_stats.cpp's checked graphics pipeline setup.
struct DrawRequest { std::filesystem::path registers, output; VkExtent2D extent{800, 450}; bool capture{}; };

struct RayBuffer { VkBuffer buffer{}; VkDeviceMemory memory{}; };
struct RayResources {
    VkDevice device;
    VkPhysicalDevice physical;
    VkImage image{};
    VkDeviceMemory image_memory{};
    VkImageView view{};
    VkFramebuffer framebuffer{};
    VkCommandPool pool{};
    VkQueryPool timestamps{};
    VkFence fence{};
    bool submitted{};
    RayBuffer roots{}, readback{};

    ~RayResources() {
        if (submitted) vkDeviceWaitIdle(device);
        if (fence) vkDestroyFence(device, fence, nullptr);
        if (timestamps) vkDestroyQueryPool(device, timestamps, nullptr);
        if (pool) vkDestroyCommandPool(device, pool, nullptr);
        if (framebuffer) vkDestroyFramebuffer(device, framebuffer, nullptr);
        if (view) vkDestroyImageView(device, view, nullptr);
        if (image) vkDestroyImage(device, image, nullptr);
        if (image_memory) vkFreeMemory(device, image_memory, nullptr);
        for (auto b : {roots, readback}) {
            if (b.buffer) vkDestroyBuffer(device, b.buffer, nullptr);
            if (b.memory) vkFreeMemory(device, b.memory, nullptr);
        }
    }

    VkDeviceMemory allocate(VkMemoryRequirements req, VkMemoryPropertyFlags properties, bool address) {
        VkPhysicalDeviceMemoryProperties memory{};
        vkGetPhysicalDeviceMemoryProperties(physical, &memory);
        uint32_t type = 0;
        while (type < memory.memoryTypeCount && (!(req.memoryTypeBits & (1u << type)) ||
                (memory.memoryTypes[type].propertyFlags & properties) != properties)) ++type;
        if (type == memory.memoryTypeCount || req.size > 32 * MiB) throw std::runtime_error("No suitable bounded allocation");
        VkMemoryAllocateFlagsInfo flags{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_FLAGS_INFO};
        flags.flags = VK_MEMORY_ALLOCATE_DEVICE_ADDRESS_BIT;
        VkMemoryAllocateInfo info{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
        info.allocationSize = req.size; info.memoryTypeIndex = type;
        if (address) info.pNext = &flags;
        VkDeviceMemory allocation{};
        check(vkAllocateMemory(device, &info, nullptr, &allocation), "vkAllocateMemory");
        return allocation;
    }

    void make_buffer(RayBuffer& b, VkDeviceSize size, VkBufferUsageFlags usage) {
        VkBufferCreateInfo info{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
        info.size = size; info.usage = usage;
        check(vkCreateBuffer(device, &info, nullptr, &b.buffer), "vkCreateBuffer");
        VkMemoryRequirements req{};
        vkGetBufferMemoryRequirements(device, b.buffer, &req);
        b.memory = allocate(req, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
                            (usage & VK_BUFFER_USAGE_SHADER_DEVICE_ADDRESS_BIT) != 0);
        check(vkBindBufferMemory(device, b.buffer, b.memory, 0), "vkBindBufferMemory");
    }
};

void store_image(const std::filesystem::path& path, const unsigned char* data, DWORD n) {
    HANDLE out = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (out == INVALID_HANDLE_VALUE) throw std::runtime_error("Cannot create new image");
    DWORD written = 0;
    bool ok = WriteFile(out, data, n, &written, nullptr) && written == n;
    CloseHandle(out);
    if (!ok) throw std::runtime_error("Image write failed");
}

#include "nerf_inputs.inl"

void draw_ray(std::ostream& out, const Pipeline& p, VkPhysicalDevice physical, uint32_t family,
              uint32_t bits, float period, VkExtent2D extent, const DrawRequest& opts, bool translated, bool native_nerf, bool bounded_nerf) {
    if (!bits || bits > 64 || !(period > 0.0f)) throw std::runtime_error("Missing graphics timestamps");
    if (std::filesystem::exists(opts.output)) throw std::runtime_error("Output already exists");
    const size_t pixel_bytes = static_cast<size_t>(extent.width) * extent.height * 16;
    constexpr size_t pad = 256;
    const size_t stride = bounded_nerf ? 16384 + 2 * pad : 1024, root_bytes = 5 * stride;
    constexpr unsigned char canary = 0xa7;
    std::vector<unsigned char> input(root_bytes, canary);
    NeRFInputs nerf{p.device};
    RayResources r{p.device, physical};
    void* mapped{};
    std::array<unsigned char, 40> push{};
    std::ifstream camera;
    if (!native_nerf) {
        camera.open(bounded_nerf ? opts.registers / "sgprs.bin" : opts.registers, std::ios::binary | std::ios::ate);
        if (camera.tellg() != (translated ? 512 : 40)) throw std::runtime_error("Unexpected camera input size");
        camera.seekg(0);
    }
    if (translated) {
        if (!camera.read(reinterpret_cast<char*>(input.data() + pad), 512)) throw std::runtime_error("SGPR read");
        uint32_t uma_hi = 0;
        std::memcpy(&uma_hi, input.data() + pad + 112 * 4, sizeof(uma_hi));
        if (uma_hi != 4) throw std::runtime_error("Unexpected XCL UMA base");
        if (bounded_nerf) {
            auto words = NeRFInputs::read_words(opts.registers / "guest_mem.bin", 4 * 4096);
            for (size_t i = 0; i < 4; ++i)
                std::memcpy(input.data() + (i + 1) * stride + pad, words.data() + i * 4096, 16384);
        } else {
            for (size_t i = 1; i < 5; ++i) std::memset(input.data() + stride * i + pad, 0, 256);
        }
        r.make_buffer(r.roots, root_bytes, VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_SHADER_DEVICE_ADDRESS_BIT);
        check(vkMapMemory(p.device, r.roots.memory, 0, root_bytes, 0, &mapped), "map roots");
        std::memcpy(mapped, input.data(), input.size());
        vkUnmapMemory(p.device, r.roots.memory);
        VkBufferDeviceAddressInfo addr{VK_STRUCTURE_TYPE_BUFFER_DEVICE_ADDRESS_INFO};
        addr.buffer = r.roots.buffer;
        auto base = vkGetBufferDeviceAddress(p.device, &addr);
        if (!base || base % 8) throw std::runtime_error("Missing or unaligned buffer address");
        std::array<VkDeviceAddress, 5> addresses{};
        for (size_t i = 0; i < addresses.size(); ++i) addresses[i] = base + stride * i + pad;
        static_assert(sizeof(addresses) == sizeof(push));
        std::memcpy(push.data(), addresses.data(), push.size());
    } else if (!native_nerf && !camera.read(reinterpret_cast<char*>(push.data()), push.size())) {
        throw std::runtime_error("Native raylib camera read");
    }
    r.make_buffer(r.readback, pixel_bytes + 2 * pad, VK_BUFFER_USAGE_TRANSFER_DST_BIT);
    check(vkMapMemory(p.device, r.readback.memory, 0, pixel_bytes + 2 * pad, 0, &mapped), "map readback");
    std::memset(mapped, canary, pixel_bytes + 2 * pad);
    vkUnmapMemory(p.device, r.readback.memory);

    VkFormatProperties fp{};
    vkGetPhysicalDeviceFormatProperties(physical, VK_FORMAT_R32G32B32A32_SFLOAT, &fp);
    const auto required = VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT | VK_FORMAT_FEATURE_TRANSFER_SRC_BIT;
    if ((fp.optimalTilingFeatures & required) != required) throw std::runtime_error("Unsupported float render target");
    VkImageCreateInfo ic{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
    ic.imageType = VK_IMAGE_TYPE_2D; ic.format = VK_FORMAT_R32G32B32A32_SFLOAT;
    ic.extent = {extent.width, extent.height, 1}; ic.mipLevels = 1; ic.arrayLayers = 1;
    ic.samples = VK_SAMPLE_COUNT_1_BIT;
    ic.usage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
    check(vkCreateImage(p.device, &ic, nullptr, &r.image), "vkCreateImage");
    VkMemoryRequirements ir{};
    vkGetImageMemoryRequirements(p.device, r.image, &ir);
    r.image_memory = r.allocate(ir, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, false);
    check(vkBindImageMemory(p.device, r.image, r.image_memory, 0), "vkBindImageMemory");
    VkImageViewCreateInfo iv{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
    iv.image = r.image; iv.viewType = VK_IMAGE_VIEW_TYPE_2D; iv.format = ic.format;
    iv.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
    check(vkCreateImageView(p.device, &iv, nullptr, &r.view), "vkCreateImageView");
    VkFramebufferCreateInfo fb{VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO};
    fb.renderPass = p.render_pass; fb.attachmentCount = 1; fb.pAttachments = &r.view;
    std::array<VkImageView, 5> framebuffer_views{r.view};
    if (native_nerf || bounded_nerf) nerf.prepare(r, p.image_set, opts.registers, extent, bounded_nerf);
    if (native_nerf) {
        for (size_t i = 0; i < 4; ++i) framebuffer_views[i + 1] = nerf.inputs[i].view;
        fb.attachmentCount = 5; fb.pAttachments = framebuffer_views.data();
    }
    fb.width = extent.width; fb.height = extent.height; fb.layers = 1;
    check(vkCreateFramebuffer(p.device, &fb, nullptr, &r.framebuffer), "vkCreateFramebuffer");
    VkCommandPoolCreateInfo pc{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
    pc.queueFamilyIndex = family; pc.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    check(vkCreateCommandPool(p.device, &pc, nullptr, &r.pool), "vkCreateCommandPool");
    VkCommandBufferAllocateInfo ca{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    ca.commandPool = r.pool; ca.commandBufferCount = 1; ca.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    VkCommandBuffer cmd{};
    check(vkAllocateCommandBuffers(p.device, &ca, &cmd), "vkAllocateCommandBuffers");
    VkQueryPoolCreateInfo qp{VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO};
    qp.queryType = VK_QUERY_TYPE_TIMESTAMP; qp.queryCount = 2;
    check(vkCreateQueryPool(p.device, &qp, nullptr, &r.timestamps), "vkCreateQueryPool");
    VkFenceCreateInfo fc{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    check(vkCreateFence(p.device, &fc, nullptr, &r.fence), "vkCreateFence");
    VkQueue queue{};
    vkGetDeviceQueue(p.device, family, 0, &queue);
    constexpr uint32_t draws = 8, intervals = 5;
    std::array<uint64_t, intervals> elapsed{};
    for (uint32_t epoch = 0; epoch <= intervals; ++epoch) {
        if (epoch) {
            check(vkResetCommandBuffer(cmd, 0), "vkResetCommandBuffer");
            check(vkResetFences(p.device, 1, &r.fence), "vkResetFences");
        }
        VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
        begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        check(vkBeginCommandBuffer(cmd, &begin), "vkBeginCommandBuffer");
        vkCmdResetQueryPool(cmd, r.timestamps, 0, 2);
        if ((native_nerf || bounded_nerf) && epoch == 0) nerf.upload(cmd, extent);
        VkClearValue clear{};
        for (float& x : clear.color.float32) x = -3.f;
        VkRenderPassBeginInfo pass{VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO};
        pass.renderPass = p.render_pass; pass.framebuffer = r.framebuffer;
        pass.renderArea.extent = extent; pass.clearValueCount = 1; pass.pClearValues = &clear;
        vkCmdBeginRenderPass(cmd, &pass, VK_SUBPASS_CONTENTS_INLINE);
        vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, p.handle);
        if (native_nerf || bounded_nerf) vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, p.layout, 0, 1, &nerf.set, 0, nullptr);
        if (!native_nerf) vkCmdPushConstants(cmd, p.layout, VK_SHADER_STAGE_FRAGMENT_BIT, 0, sizeof(push), push.data());
        vkCmdWriteTimestamp(cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, r.timestamps, 0);
        for (uint32_t j = 0; j < (epoch ? draws : 1); ++j) vkCmdDraw(cmd, 3, 1, 0, 0);
        vkCmdWriteTimestamp(cmd, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, r.timestamps, 1);
        vkCmdEndRenderPass(cmd);
        if (epoch == intervals) {
            VkImageMemoryBarrier barrier{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
            barrier.srcAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT; barrier.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
            barrier.oldLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL; barrier.newLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
            barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED; barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
            barrier.image = r.image; barrier.subresourceRange = iv.subresourceRange;
            vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                                 0, 0, nullptr, 0, nullptr, 1, &barrier);
            VkBufferImageCopy region{};
            region.bufferOffset = pad; region.imageExtent = ic.extent;
            region.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
            vkCmdCopyImageToBuffer(cmd, r.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, r.readback.buffer, 1, &region);
            VkMemoryBarrier host{VK_STRUCTURE_TYPE_MEMORY_BARRIER};
            host.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT; host.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
            vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT, 0,
                                 1, &host, 0, nullptr, 0, nullptr);
        }
        check(vkEndCommandBuffer(cmd), "vkEndCommandBuffer");
        VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};
        submit.commandBufferCount = 1; submit.pCommandBuffers = &cmd;
        check(vkQueueSubmit(queue, 1, &submit, r.fence), "vkQueueSubmit");
        r.submitted = true;
        check(vkWaitForFences(p.device, 1, &r.fence, VK_TRUE, 10000000000ull), "vkWaitForFences");
        r.submitted = false;
        std::array<uint64_t, 2> counters{};
        check(vkGetQueryPoolResults(p.device, r.timestamps, 0, 2, sizeof(counters), counters.data(), sizeof(uint64_t),
                                    VK_QUERY_RESULT_64_BIT), "vkGetQueryPoolResults");
        uint64_t delta = counters[1] - counters[0];
        if (bits < 64) delta &= (1ull << bits) - 1;
        if (!delta) throw std::runtime_error("Zero timestamp interval");
        if (epoch) elapsed[epoch - 1] = delta;
    }
    if (translated) {
        check(vkMapMemory(p.device, r.roots.memory, 0, root_bytes, 0, &mapped), "check root data");
        const bool roots_untouched = std::memcmp(mapped, input.data(), input.size()) == 0;
        vkUnmapMemory(p.device, r.roots.memory);
        if (!roots_untouched) throw std::runtime_error("Root or adjacent guard modified");
    }
    check(vkMapMemory(p.device, r.readback.memory, 0, pixel_bytes + 2 * pad, 0, &mapped), "map image");
    auto data = static_cast<unsigned char*>(mapped);
    bool guard_ok = true;
    for (size_t i = 0; i < pad; ++i) guard_ok &= data[i] == canary && data[pad + pixel_bytes + i] == canary;
    std::vector<unsigned char> pixels(data + pad, data + pad + pixel_bytes);
    vkUnmapMemory(p.device, r.readback.memory);
    if (!guard_ok) throw std::runtime_error("Readback guard modified");
    store_image(opts.output, pixels.data(), static_cast<DWORD>(pixel_bytes));
    out << ",\"width\":" << extent.width << ",\"height\":" << extent.height
        << ",\"draws_per_interval\":" << draws << ",\"timestamp_valid_bits\":" << bits
        << ",\"timestamp_period_ns\":" << period << ",\"gpu_ticks\":[";
    for (size_t i = 0; i < elapsed.size(); ++i) out << (i ? "," : "") << elapsed[i];
    out << "],\"gpu_ms_per_draw\":[";
    for (size_t i = 0; i < elapsed.size(); ++i) out << (i ? "," : "") << elapsed[i] * static_cast<double>(period) / (draws * 1e6);
    out << "],\"root_and_readback_guards_intact\":true";
}
