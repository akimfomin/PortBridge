#include <d3d12.h>
#include <dxgi1_4.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <wrl/client.h>

using Microsoft::WRL::ComPtr;

void check(HRESULT hr, const char* operation) {
    if (FAILED(hr)) {
        std::fprintf(stderr, "%s: 0x%08lx\n", operation, static_cast<unsigned long>(hr));
        std::exit(2);
    }
}

D3D12_RESOURCE_DESC buffer(UINT64 bytes) {
    D3D12_RESOURCE_DESC desc{};
    desc.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
    desc.Width = bytes;
    desc.Height = desc.DepthOrArraySize = desc.MipLevels = desc.SampleDesc.Count = 1;
    desc.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    return desc;
}

ComPtr<ID3D12Resource> committed(ID3D12Device* device, D3D12_HEAP_TYPE type, UINT64 bytes, D3D12_RESOURCE_STATES state) {
    D3D12_HEAP_PROPERTIES properties{};
    properties.Type = type;
    properties.CreationNodeMask = properties.VisibleNodeMask = 1;
    const auto desc = buffer(bytes);
    ComPtr<ID3D12Resource> resource;
    check(device->CreateCommittedResource(&properties, D3D12_HEAP_FLAG_NONE, &desc, state, nullptr,
                                         IID_PPV_ARGS(&resource)), "CreateCommittedResource");
    return resource;
}

int main() {
    constexpr UINT64 tile = 65536;
    constexpr UINT64 span = 3 * tile;
    ComPtr<IDXGIFactory4> factory;
    check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)), "CreateDXGIFactory1");
    ComPtr<IDXGIAdapter1> adapter;
    for (UINT index = 0;; ++index) {
        check(factory->EnumAdapters1(index, &adapter), "EnumAdapters1");
        DXGI_ADAPTER_DESC1 desc{};
        check(adapter->GetDesc1(&desc), "GetDesc1");
        if (desc.VendorId == 0x10de && !(desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE)) {
            std::printf("adapter=%ls\n", desc.Description);
            break;
        }
        adapter.Reset();
    }
    ComPtr<ID3D12Device> device;
    check(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_11_0, IID_PPV_ARGS(&device)), "D3D12CreateDevice");
    unsigned failures = 0;
    for (UINT64 offset : {0ull, 4096ull, 65536ull, 69632ull}) {
        D3D12_COMMAND_QUEUE_DESC qdesc{};
        ComPtr<ID3D12CommandQueue> queue;
        check(device->CreateCommandQueue(&qdesc, IID_PPV_ARGS(&queue)), "CreateCommandQueue");
        ComPtr<ID3D12CommandAllocator> allocator;
        check(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT, IID_PPV_ARGS(&allocator)),
              "CreateCommandAllocator");
        ComPtr<ID3D12GraphicsCommandList> list;
        check(device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, allocator.Get(), nullptr,
                                        IID_PPV_ARGS(&list)), "CreateCommandList");
        auto upload = committed(device.Get(), D3D12_HEAP_TYPE_UPLOAD, 2 * span, D3D12_RESOURCE_STATE_GENERIC_READ);
        auto readback = committed(device.Get(), D3D12_HEAP_TYPE_READBACK, span, D3D12_RESOURCE_STATE_COPY_DEST);
        auto desc = buffer(tile);
        ComPtr<ID3D12Resource> reserved;
        check(device->CreateReservedResource(&desc, D3D12_RESOURCE_STATE_COPY_DEST, nullptr,
                                             IID_PPV_ARGS(&reserved)), "CreateReservedResource");
        D3D12_HEAP_DESC heap_desc{};
        heap_desc.SizeInBytes = tile;
        heap_desc.Properties.Type = D3D12_HEAP_TYPE_DEFAULT;
        heap_desc.Properties.CreationNodeMask = heap_desc.Properties.VisibleNodeMask = 1;
        heap_desc.Flags = D3D12_HEAP_FLAG_ALLOW_ONLY_BUFFERS;
        ComPtr<ID3D12Heap> heap;
        check(device->CreateHeap(&heap_desc, IID_PPV_ARGS(&heap)), "CreateHeap");
        const D3D12_TILED_RESOURCE_COORDINATE origin{};
        const D3D12_TILE_REGION_SIZE region{1, FALSE, 1, 1, 1};
        const UINT one = 1, start = 0;
        queue->UpdateTileMappings(reserved.Get(), 1, &origin, &region, heap.Get(), 1, nullptr, &start,
                                  &one, D3D12_TILE_MAPPING_FLAG_NONE);

        unsigned char* bytes = nullptr;
        const D3D12_RANGE none{0, 0};
        check(upload->Map(0, &none, reinterpret_cast<void**>(&bytes)), "Map upload");
        std::memset(bytes, 0xa2, 2 * span);
        for (UINT64 i = 0; i < tile; ++i) bytes[offset + i] = static_cast<unsigned char>((i * 13 + i / 4096) & 255);
        upload->Unmap(0, nullptr);
        list->CopyBufferRegion(readback.Get(), 0, upload.Get(), span, span);
        list->CopyTiles(reserved.Get(), &origin, &region, upload.Get(), offset,
                        D3D12_TILE_COPY_FLAG_LINEAR_BUFFER_TO_SWIZZLED_TILED_RESOURCE);
        D3D12_RESOURCE_BARRIER barrier{};
        barrier.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        barrier.Transition = {reserved.Get(), D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,
                              D3D12_RESOURCE_STATE_COPY_DEST, D3D12_RESOURCE_STATE_COPY_SOURCE};
        list->ResourceBarrier(1, &barrier);
        list->CopyTiles(reserved.Get(), &origin, &region, readback.Get(), offset,
                        D3D12_TILE_COPY_FLAG_SWIZZLED_TILED_RESOURCE_TO_LINEAR_BUFFER);
        check(list->Close(), "Close");
        ID3D12CommandList* lists[]{list.Get()};
        queue->ExecuteCommandLists(1, lists);
        ComPtr<ID3D12Fence> fence;
        check(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&fence)), "CreateFence");
        const HANDLE event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
        if (!event) return 2;
        check(queue->Signal(fence.Get(), 1), "Signal");
        check(fence->SetEventOnCompletion(1, event), "SetEventOnCompletion");
        const auto completion = WaitForSingleObject(event, 5000);
        CloseHandle(event);
        if (completion != WAIT_OBJECT_0) return 2;
        check(device->GetDeviceRemovedReason(), "Device status");

        const D3D12_RANGE full{0, span};
        check(readback->Map(0, &full, reinterpret_cast<void**>(&bytes)), "Map readback");
        unsigned payload = 0, guard = 0;
        for (UINT64 i = 0; i < span; ++i) {
            if (i >= offset && i < offset + tile) {
                const UINT64 j = i - offset;
                payload += bytes[i] != static_cast<unsigned char>((j * 13 + j / 4096) & 255);
            } else {
                guard += bytes[i] != 0xa2;
            }
        }
        readback->Unmap(0, &none);
        std::printf("offset=%llu payload_mismatches=%u guard_mismatches=%u\n", offset, payload, guard);
        failures += payload != 0 || guard != 0;
    }
    return failures != 0;
}
