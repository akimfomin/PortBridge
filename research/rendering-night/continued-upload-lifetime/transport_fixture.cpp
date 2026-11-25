// SPDX-License-Identifier: GPL-3.0-or-later
// The extracted Continued transport is exercised exclusively with deterministic fake callbacks.
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string_view>
#include <type_traits>
#include <vector>

#ifdef PB_CANDIDATE
#include "candidate.inc"
#else
#include "stock.inc"
#endif

namespace {
#define REQUIRE(condition) do { \
    if (!(condition)) { \
        std::fprintf(stderr, "line %d: %s\n", __LINE__, #condition); \
        std::exit(1); \
    } \
} while (false)

template<class T>
T handle(std::uintptr_t value) {
    if constexpr (std::is_pointer_v<T>) return reinterpret_cast<T>(value);
    else return static_cast<T>(value);
}

struct FakeVulkan {
    const VkQueue primary = handle<VkQueue>(1);
    std::array<std::uint8_t, 4096> staging{};
    VkDeviceSize buffer_size{};
    std::uint64_t pending_signal{}, counter{};
    VkResult primary_result = VK_SUCCESS, wait_result = VK_SUCCESS, query_result = VK_SUCCESS;
    unsigned failed_consumer_index{}, consumers{}, queries{}, maps{}, grows{};
    unsigned overwritten_pending{}, destroyed_pending{};

    VkResult vkCreateCommandPool(VkDevice, const VkCommandPoolCreateInfo*, const VkAllocationCallbacks*,
                                 VkCommandPool* out) {
        *out = handle<VkCommandPool>(3);
        return VK_SUCCESS;
    }
    VkResult vkAllocateCommandBuffers(VkDevice, const VkCommandBufferAllocateInfo*, VkCommandBuffer* out) {
        *out = handle<VkCommandBuffer>(4);
        return VK_SUCCESS;
    }
    VkResult vkCreateSemaphore(VkDevice, const VkSemaphoreCreateInfo* info, const VkAllocationCallbacks*,
                               VkSemaphore* out) {
        const auto* type = static_cast<const VkSemaphoreTypeCreateInfo*>(info->pNext);
        REQUIRE(type->semaphoreType == VK_SEMAPHORE_TYPE_TIMELINE);
        *out = handle<VkSemaphore>(5);
        return VK_SUCCESS;
    }
    VkResult vkCreateBuffer(VkDevice, const VkBufferCreateInfo* info, const VkAllocationCallbacks*, VkBuffer* out) {
        REQUIRE(info->size <= staging.size());
        buffer_size = info->size;
        *out = handle<VkBuffer>(6 + grows++);
        return VK_SUCCESS;
    }
    void vkGetBufferMemoryRequirements(VkDevice, VkBuffer, VkMemoryRequirements* out) {
        *out = {buffer_size, 1, 1};
    }
    VkResult vkBindBufferMemory(VkDevice, VkBuffer, VkDeviceMemory, VkDeviceSize) { return VK_SUCCESS; }
    VkResult vkMapMemory(VkDevice, VkDeviceMemory, VkDeviceSize, VkDeviceSize, VkMemoryMapFlags, void** out) {
        ++maps;
        *out = staging.data();
        return VK_SUCCESS;
    }
    void vkDestroyBuffer(VkDevice, VkBuffer, const VkAllocationCallbacks*) {
        if (active()) ++destroyed_pending;
    }
    void vkFreeMemory(VkDevice, VkDeviceMemory, const VkAllocationCallbacks*) {
        if (active()) ++destroyed_pending;
    }
    VkResult vkQueueSubmit(VkQueue queue, std::uint32_t count, const VkSubmitInfo* info, VkFence) {
        REQUIRE(count == 1);
        const auto* timeline = static_cast<const VkTimelineSemaphoreSubmitInfo*>(info->pNext);
        if (queue == primary) {
            REQUIRE(!active());
            REQUIRE(timeline->signalSemaphoreValueCount == 1 && info->commandBufferCount == 1);
            if (primary_result == VK_SUCCESS) pending_signal = timeline->pSignalSemaphoreValues[0];
            return primary_result;
        }
        REQUIRE(!active());
        REQUIRE(timeline->waitSemaphoreValueCount == 1 && info->waitSemaphoreCount == 1);
        REQUIRE(timeline->pWaitSemaphoreValues[0] == counter);
        return ++consumers == failed_consumer_index ? VK_ERROR_OUT_OF_HOST_MEMORY : VK_SUCCESS;
    }
    VkResult vkWaitSemaphores(VkDevice, const VkSemaphoreWaitInfo* wait, std::uint64_t timeout) {
        REQUIRE(active() && wait->semaphoreCount == 1 && wait->pValues[0] == pending_signal);
        REQUIRE(timeout == UINT64_MAX);
        if (wait_result == VK_SUCCESS) finish();
        return wait_result;
    }
    VkResult vkGetSemaphoreCounterValue(VkDevice, VkSemaphore, std::uint64_t* out) {
        ++queries;
        if (query_result == VK_SUCCESS) *out = counter;
        return query_result;
    }
    void write() {
        if (active()) ++overwritten_pending;
        ++staging[0];
    }
    void finish() { counter = pending_signal; }
    bool active() const { return pending_signal > counter; }
};

struct Context {
    FakeVulkan vk;
    bool lost{};
    bool is_device_lost() const { return lost; }
    VkResult observe_result(VkResult result, const char*) { return result; }
};

struct Device {
    struct Info {
        VkDevice device = handle<VkDevice>(2);
        VkQueue queue = handle<VkQueue>(1);
        std::uint32_t queue_family{};
        std::vector<VkQueue> command_queues{queue};
        std::vector<VkQueue> compute_queues{handle<VkQueue>(3)};
        std::vector<VkQueue> copy_queues{handle<VkQueue>(4), handle<VkQueue>(3)};
    } info;
    Context storage;
    Context* context = &storage;
    VkDeviceMemory allocate(const VkMemoryRequirements& requirements, VkMemoryPropertyFlags, unsigned) {
        REQUIRE(requirements.size <= storage.vk.staging.size());
        return handle<VkDeviceMemory>(11);
    }
};

unsigned wait_failure(bool growing) {
    Device device;
    TitleImageUpload subject;
    auto& vk = device.storage.vk;
    REQUIRE(subject.prepare(device, 256));
    vk.write();
    vk.wait_result = VK_ERROR_OUT_OF_HOST_MEMORY;
    REQUIRE(subject.submit(device) == VK_ERROR_OUT_OF_HOST_MEMORY);
    REQUIRE(vk.active() && vk.consumers == 0);
    const unsigned new_size = growing ? 512 : 256;
    const bool accepted = subject.prepare(device, new_size);
    if (accepted) vk.write();
#ifdef PB_CANDIDATE
    const auto unresolved = subject.progress();
    REQUIRE(unresolved.accepted == 1 && unresolved.completed == 0 && unresolved.published == 0);
    REQUIRE(!accepted && vk.queries == 1 && vk.maps == 1);
    vk.query_result = VK_ERROR_OUT_OF_DEVICE_MEMORY;
    REQUIRE(!subject.prepare(device, new_size));
    REQUIRE(vk.queries == 2 && vk.destroyed_pending == 0 && vk.overwritten_pending == 0);
    vk.finish();
    vk.query_result = VK_SUCCESS;
    REQUIRE(subject.prepare(device, new_size));
    const auto resolved = subject.progress();
    REQUIRE(resolved.accepted == 1 && resolved.completed == 1 && resolved.published == 0);
    REQUIRE(vk.queries == 3 && vk.maps == (growing ? 2u : 1u));
    vk.wait_result = VK_SUCCESS;
    REQUIRE(subject.submit(device) == VK_SUCCESS);
    REQUIRE(subject.progress().published == 2);
#else
    REQUIRE(accepted && vk.queries == 0 && vk.maps == (growing ? 2u : 1u));
    REQUIRE(vk.overwritten_pending == 1);
    REQUIRE(vk.destroyed_pending == (growing ? 2u : 0u));
#endif
    std::printf("failed_wait_grow=%d overwrite_while_pending=%u destroy_while_pending=%u queries=%u\n",
                int(growing), vk.overwritten_pending, vk.destroyed_pending, vk.queries);
    return vk.overwritten_pending + vk.destroyed_pending;
}

void finished_paths() {
    {
        Device device;
        TitleImageUpload subject;
        auto& vk = device.storage.vk;
        REQUIRE(subject.prepare(device, 256));
        vk.primary_result = VK_ERROR_OUT_OF_DEVICE_MEMORY;
        REQUIRE(subject.submit(device) == VK_ERROR_OUT_OF_DEVICE_MEMORY);
        REQUIRE(!vk.active() && subject.prepare(device, 256) && vk.queries == 0);
#ifdef PB_CANDIDATE
        const auto progress = subject.progress();
        REQUIRE(progress.accepted == 0 && progress.completed == 0 && progress.published == 0);
#endif
        vk.primary_result = VK_SUCCESS;
        REQUIRE(subject.submit(device) == VK_SUCCESS && vk.counter == 2 && vk.consumers == 2);
#ifdef PB_CANDIDATE
        REQUIRE(subject.progress().published == 2);
#endif
    }
    {
        Device device;
        TitleImageUpload subject;
        auto& vk = device.storage.vk;
        REQUIRE(subject.prepare(device, 256));
        vk.failed_consumer_index = 2;
        REQUIRE(subject.submit(device) == VK_ERROR_OUT_OF_HOST_MEMORY);
        REQUIRE(!vk.active() && vk.consumers == 2);
        REQUIRE(subject.prepare(device, 512) && vk.queries == 0 && vk.destroyed_pending == 0);
#ifdef PB_CANDIDATE
        const auto progress = subject.progress();
        REQUIRE(progress.accepted == 1 && progress.completed == 1 && progress.published == 0);
#endif
        vk.failed_consumer_index = 0;
        REQUIRE(subject.submit(device) == VK_SUCCESS && vk.counter == 2);
    }
#ifdef PB_CANDIDATE
    {
        Device device;
        TitleImageUpload subject;
        auto& vk = device.storage.vk;
        REQUIRE(subject.prepare(device, 256));
        vk.wait_result = VK_ERROR_OUT_OF_DEVICE_MEMORY;
        REQUIRE(subject.submit(device) == VK_ERROR_OUT_OF_DEVICE_MEMORY);
        vk.query_result = VK_ERROR_DEVICE_LOST;
        REQUIRE(!subject.prepare(device, 256) && vk.queries == 1);
        device.storage.lost = true;  // The device owner reports terminal loss.
        vk.finish();
        REQUIRE(!subject.prepare(device, 256) && vk.queries == 1 && vk.maps == 1);
    }
#endif
    std::puts("healthy_reuse_no_query=ok queue_reject_reuse=ok completed_unpublished_reuse=ok");
}
} // namespace

int main(int argc, char** argv) {
    if (argc > 2 || (argc == 2 && std::string_view(argv[1]) != "--require-safe-reuse")) return 2;
    const auto overwrite = wait_failure(false);
    const auto growth = wait_failure(true);
    finished_paths();
    if (argc == 2 && (overwrite || growth)) return 1;
}
