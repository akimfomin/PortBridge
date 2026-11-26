#include <d3d12.h>
#include <dxgi1_4.h>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <wrl/client.h>

using Microsoft::WRL::ComPtr;

void check(HRESULT result, const char* operation) {
    if (FAILED(result)) {
        std::fprintf(stderr, "%s: HRESULT 0x%08lx\n", operation, static_cast<unsigned long>(result));
        std::exit(2);
    }
}

int main() {
    ComPtr<IDXGIFactory4> factory;
    check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)), "CreateDXGIFactory1");
    ComPtr<IDXGIAdapter1> adapter;
    for (UINT index = 0;; ++index) {
        const HRESULT status = factory->EnumAdapters1(index, &adapter);
        if (status == DXGI_ERROR_NOT_FOUND) return 2;
        check(status, "EnumAdapters1");
        DXGI_ADAPTER_DESC1 desc{};
        check(adapter->GetDesc1(&desc), "GetDesc1");
        if (desc.VendorId == 0x10de && !(desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE)) {
            std::printf("adapter=%ls vendor=%04x device=%04x\n", desc.Description, desc.VendorId, desc.DeviceId);
            break;
        }
        adapter.Reset();
    }
    ComPtr<ID3D12Device> device;
    check(D3D12CreateDevice(adapter.Get(), D3D_FEATURE_LEVEL_11_0, IID_PPV_ARGS(&device)), "D3D12CreateDevice");
    D3D12_FEATURE_DATA_D3D12_OPTIONS opts{};
    check(device->CheckFeatureSupport(D3D12_FEATURE_D3D12_OPTIONS, &opts, sizeof(opts)), "CheckFeatureSupport");
    std::printf("tiled_resources_tier=%u\n", static_cast<unsigned>(opts.TiledResourcesTier));

    struct Case {
        const char* name;
        DXGI_FORMAT format;
        UINT width, height, count;
        UINT texture_width = 512;
        UINT texture_height = 512;
        bool depth = false;
    };
    constexpr std::array cases{
        Case{"BC1_UNORM", DXGI_FORMAT_BC1_UNORM, 512, 256, 2},
        Case{"BC4_UNORM", DXGI_FORMAT_BC4_UNORM, 512, 256, 2},
        Case{"BC5_UNORM", DXGI_FORMAT_BC5_UNORM, 256, 256, 4},
        Case{"XCL_RGBA8_8", DXGI_FORMAT_R8G8B8A8_UNORM, 128, 128, 1, 8, 8},
        Case{"XCL_RGBA8_256", DXGI_FORMAT_R8G8B8A8_UNORM, 128, 128, 4, 256, 256},
        Case{"XCL_BC1_256", DXGI_FORMAT_BC1_UNORM, 512, 256, 1, 256, 256},
        Case{"XCL_D32_8", DXGI_FORMAT_D32_FLOAT, 128, 128, 1, 8, 8, true},
    };
    bool passed = true;
    for (const auto& test : cases) {
        D3D12_RESOURCE_DESC desc{};
        desc.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
        desc.Width = test.texture_width;
        desc.Height = test.texture_height;
        desc.DepthOrArraySize = 1;
        desc.MipLevels = 1;
        desc.Format = test.format;
        desc.SampleDesc.Count = 1;
        desc.Layout = D3D12_TEXTURE_LAYOUT_64KB_UNDEFINED_SWIZZLE;
        D3D12_CLEAR_VALUE clear{};
        clear.Format = test.format;
        clear.DepthStencil.Depth = 1.0f;
        if (test.depth) desc.Flags = D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL;
        ComPtr<ID3D12Resource> resource;
        const auto initial_state = test.depth ? D3D12_RESOURCE_STATE_DEPTH_WRITE : D3D12_RESOURCE_STATE_COMMON;
        check(device->CreateReservedResource(&desc, initial_state, test.depth ? &clear : nullptr,
                                              IID_PPV_ARGS(&resource)), test.name);
        UINT total = 0, returned = 1;
        D3D12_PACKED_MIP_INFO mips{};
        D3D12_TILE_SHAPE shape{};
        D3D12_SUBRESOURCE_TILING grid{};
        device->GetResourceTiling(resource.Get(), &total, &mips, &shape, &returned, 0, &grid);
        const bool standard_shape = shape.WidthInTexels == test.width && shape.HeightInTexels == test.height &&
                                    shape.DepthInTexels == 1;
        const auto grid_tiles = grid.WidthInTiles * grid.HeightInTiles * grid.DepthInTiles;
        const bool standard = mips.NumStandardMips == 1 && mips.NumPackedMips == 0 && standard_shape &&
                              total == test.count && grid.StartTileIndexInOverallResource == 0 &&
                              grid_tiles == total;
        const bool packed = mips.NumStandardMips == 0 && mips.NumPackedMips == 1 &&
                            grid_tiles == 0 && grid.StartTileIndexInOverallResource == D3D12_PACKED_TILE &&
                            mips.NumTilesForPackedMips >= 1 &&
                            static_cast<UINT64>(mips.StartTileIndexInOverallResource) + mips.NumTilesForPackedMips <= total &&
                            mips.NumTilesForPackedMips == total;
        const bool may_pack = test.texture_width < test.width || test.texture_height < test.height;
        const bool ok = returned == 1 && (standard || (may_pack && packed));
        std::printf("%s shape=%ux%ux%u grid=%ux%ux%u total=%u standard=%u packed=%u sub_start=%u "
                    "packed_start=%u packed_tiles=%u xcl_line_278=%s %s\n",
                    test.name, shape.WidthInTexels, shape.HeightInTexels, shape.DepthInTexels,
                    grid.WidthInTiles, grid.HeightInTiles, grid.DepthInTiles, total, mips.NumStandardMips,
                    mips.NumPackedMips, grid.StartTileIndexInOverallResource, mips.StartTileIndexInOverallResource,
                    mips.NumTilesForPackedMips,
                    grid_tiles ? "n/a" : grid.StartTileIndexInOverallResource < total ? "PASS" : "FAIL",
                    ok ? "PASS" : "FAIL");
        passed &= ok;
    }
    return passed ? 0 : 1;
}
