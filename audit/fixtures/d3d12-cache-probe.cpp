#include <cstdio>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>
#include <d3d12.h>
#include <dxgi1_4.h>
#include <wrl/client.h>

using Microsoft::WRL::ComPtr;

static std::vector<uint8_t> read_file(const char* path) {
    std::ifstream file(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}

static bool run_probe(ID3D12Device* device, D3D12_COMPUTE_PIPELINE_STATE_DESC desc,
                      const char* name, const std::vector<uint8_t>& input, bool keep_success) {
    desc.CachedPSO = {input.data(), input.size()};
    ComPtr<ID3D12PipelineState> state;
    const HRESULT first = device->CreateComputePipelineState(&desc, IID_PPV_ARGS(&state));
    ComPtr<ID3DBlob> returned;
    HRESULT readback = E_FAIL;
    if (SUCCEEDED(first)) readback = state->GetCachedBlob(&returned);
    const size_t size = returned ? returned->GetBufferSize() : 0;
    const bool same_bytes = returned && size == input.size()
        && std::memcmp(returned->GetBufferPointer(), input.data(), size) == 0;
    int creates = 1;
    HRESULT final = first;
    if (FAILED(first) || (!keep_success && (FAILED(readback) || size != input.size()))) {
        desc.CachedPSO = {};
        state.Reset();
        final = device->CreateComputePipelineState(&desc, IID_PPV_ARGS(&state));
        creates++;
    }
    std::printf("%s %s input=%zu probe=0x%08lx returned=%zu same_bytes=%d creates=%d final=0x%08lx\n",
        name, keep_success ? "keep" : "size", input.size(), static_cast<unsigned long>(first),
        size, same_bytes, creates, static_cast<unsigned long>(final));
    return SUCCEEDED(final);
}

int main(int argc, char** argv) {
    if (argc != 2) return 1;
    const auto shader = read_file(argv[1]);
    if (shader.empty()) return 2;

    ComPtr<ID3D12Device> device;
    if (FAILED(D3D12CreateDevice(nullptr, D3D_FEATURE_LEVEL_11_0, IID_PPV_ARGS(&device)))) return 3;
    ComPtr<IDXGIFactory4> factory;
    ComPtr<IDXGIAdapter1> adapter;
    DXGI_ADAPTER_DESC1 info{};
    if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&factory))) ||
        FAILED(factory->EnumAdapterByLuid(device->GetAdapterLuid(), IID_PPV_ARGS(&adapter))) ||
        FAILED(adapter->GetDesc1(&info))) return 4;
    std::printf("PCI %04x:%04x\n", unsigned(info.VendorId), unsigned(info.DeviceId));

    D3D12_ROOT_SIGNATURE_DESC root{};
    ComPtr<ID3DBlob> serialized;
    if (FAILED(D3D12SerializeRootSignature(&root, D3D_ROOT_SIGNATURE_VERSION_1,
                                          &serialized, nullptr))) return 5;
    ComPtr<ID3D12RootSignature> signature;
    if (FAILED(device->CreateRootSignature(0, serialized->GetBufferPointer(),
                                          serialized->GetBufferSize(), IID_PPV_ARGS(&signature)))) return 6;
    D3D12_COMPUTE_PIPELINE_STATE_DESC desc{};
    desc.pRootSignature = signature.Get();
    desc.CS = {shader.data(), shader.size()};
    ComPtr<ID3D12PipelineState> seed;
    if (FAILED(device->CreateComputePipelineState(&desc, IID_PPV_ARGS(&seed)))) return 7;
    ComPtr<ID3DBlob> blob;
    if (FAILED(seed->GetCachedBlob(&blob)) || !blob || !blob->GetBufferSize()) return 8;
    const auto* bytes = static_cast<const uint8_t*>(blob->GetBufferPointer());
    const std::vector<uint8_t> original(bytes, bytes + blob->GetBufferSize());
    auto padded = original;
    padded.resize(original.size() + 16, 0);

    bool passed = true;
    for (const bool keep_success : {false, true}) {
        passed &= run_probe(device.Get(), desc, "unchanged", original, keep_success);
        passed &= run_probe(device.Get(), desc, "padded", padded, keep_success);
    }
    return passed ? 0 : 9;
}
