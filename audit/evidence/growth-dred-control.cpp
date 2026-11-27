#include <cstdio>
#include <cstring>
#include <d3d12.h>
#include <dxgi1_4.h>
#include <wrl/client.h>

using Microsoft::WRL::ComPtr;

int main(int argc, char** argv) {
    if (argc != 2 || (std::strcmp(argv[1], "early") && std::strcmp(argv[1], "late"))) return 2;
    const bool early = std::strcmp(argv[1], "early") == 0;
    ComPtr<ID3D12DeviceRemovedExtendedDataSettings> settings;
    if (FAILED(D3D12GetDebugInterface(IID_PPV_ARGS(&settings)))) return 3;
    auto enable = [&] {
        settings->SetAutoBreadcrumbsEnablement(D3D12_DRED_ENABLEMENT_FORCED_ON);
        settings->SetPageFaultEnablement(D3D12_DRED_ENABLEMENT_FORCED_ON);
    };
    settings->SetAutoBreadcrumbsEnablement(D3D12_DRED_ENABLEMENT_FORCED_OFF);
    settings->SetPageFaultEnablement(D3D12_DRED_ENABLEMENT_FORCED_OFF);
    if (early) enable();
    ComPtr<ID3D12Device> device;
    if (FAILED(D3D12CreateDevice(nullptr, D3D_FEATURE_LEVEL_11_0, IID_PPV_ARGS(&device)))) return 4;
    if (!early) enable();
    ComPtr<ID3D12DeviceRemovedExtendedData> dred;
    if (FAILED(device.As(&dred))) return 5;
    D3D12_DRED_AUTO_BREADCRUMBS_OUTPUT crumb{};
    D3D12_DRED_PAGE_FAULT_OUTPUT fault{};
    const HRESULT breadcrumbs = dred->GetAutoBreadcrumbsOutput(&crumb);
    const HRESULT page_fault = dred->GetPageFaultAllocationOutput(&fault);
    const HRESULT removed = device->GetDeviceRemovedReason();
    ComPtr<IDXGIFactory4> factory;
    ComPtr<IDXGIAdapter1> adapter;
    DXGI_ADAPTER_DESC1 desc{};
    if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&factory))) ||
        FAILED(factory->EnumAdapterByLuid(device->GetAdapterLuid(), IID_PPV_ARGS(&adapter))) ||
        FAILED(adapter->GetDesc1(&desc))) return 6;
    std::printf("mode=%s adapter=%ls breadcrumbs=%08lx page_fault=%08lx device=%08lx\n",
                argv[1], desc.Description, static_cast<unsigned long>(breadcrumbs),
                static_cast<unsigned long>(page_fault), static_cast<unsigned long>(removed));
    const HRESULT expected = early ? DXGI_ERROR_NOT_CURRENTLY_AVAILABLE : DXGI_ERROR_UNSUPPORTED;
    return breadcrumbs == expected && page_fault == expected && removed == S_OK ? 0 : 7;
}
