// Fixed BC7 fixture; physical range [0x1d0000,0x1e0000), 4096 changed elements.
constexpr unsigned width = 1024, height = 1024;
constexpr unsigned array_size = 2, mip_levels = 2;
constexpr unsigned target = 2;
constexpr D3D12_BOX dirty_region{256, 256, 0, 512, 512, 1};
