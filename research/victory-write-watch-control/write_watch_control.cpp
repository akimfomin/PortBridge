#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>

constexpr std::size_t window_size = 4u * 1024 * 1024;
constexpr std::size_t window_count = 16;
constexpr std::size_t buffer_size = window_size * window_count;
constexpr unsigned rounds = 8;
constexpr unsigned repeats = 96;

void require(bool allowed, const char* detail) {
    if (!allowed) {
        std::fprintf(stderr, "%s\n", detail);
        std::exit(1);
    }
}

struct Region {
    char* start = static_cast<char*>(VirtualAlloc(nullptr, buffer_size,
        MEM_RESERVE | MEM_COMMIT | MEM_WRITE_WATCH, PAGE_READWRITE));
    ~Region() { if (start) VirtualFree(start, 0, MEM_RELEASE); }
};

struct Shape {
    const char* name;
    bool gap;
    std::array<bool, window_count> selected{};
    std::size_t first = window_count;
    std::size_t end = 0;
    std::size_t count = 0;

    Shape(const char* label, bool gapped) : name(label), gap(gapped) {
        for (std::size_t i = 0; i < window_count; ++i) {
            selected[i] = gap ? (i % 2 == 0) : (4 <= i && i < 12);
            if (selected[i]) {
                first = std::min(first, i);
                end = i + 1;
                ++count;
            }
        }
    }
};

struct Counts {
    std::uint64_t checksum = 0;
    std::size_t returned = 0;
    std::size_t kept = 0;
};

class Watch {
public:
    Watch(char* region, std::size_t page_bytes)
        : base(region), page_size(page_bytes), output(buffer_size / page_bytes) {}

    Counts run(const Shape& shape, bool batch, std::vector<std::size_t>* cells = nullptr) {
        Counts counts{};
        if (batch) {
            scan(shape, shape.first, shape.end - shape.first, shape.gap, counts, cells);
        } else {
            for (std::size_t i = shape.first; i < shape.end; ++i) {
                if (shape.selected[i]) scan(shape, i, 1, false, counts, cells);
            }
        }
        return counts;
    }

private:
    void scan(const Shape& shape, std::size_t first, std::size_t windows, bool filter,
              Counts& counts, std::vector<std::size_t>* cells) {
        ULONG_PTR size = static_cast<ULONG_PTR>(output.size());
        ULONG granularity = 0;
        UINT result = GetWriteWatch(0, base + first * window_size,
            windows * window_size, output.data(), &size, &granularity);
        require(result == 0 && granularity == page_size, "GetWriteWatch failed or returned unexpected granularity");
        counts.returned += size;
        for (ULONG_PTR i = 0; i < size; ++i) {
            const auto offset = reinterpret_cast<std::uintptr_t>(output[i]) -
                reinterpret_cast<std::uintptr_t>(base);
            require(offset < buffer_size && offset % page_size == 0, "Unexpected page");
            if (filter && !shape.selected[offset / window_size]) continue;
            const auto page = offset / page_size;
            ++counts.kept;
            counts.checksum += page + 1;
            if (cells) cells->push_back(page);
        }
    }

    char* base;
    const std::size_t page_size;
    std::vector<void*> output;
};

std::vector<std::size_t> expected_pages(const Shape& shape, bool dirty, std::size_t page_size) {
    std::vector<std::size_t> expected;
    if (dirty) {
        for (std::size_t page = 3; page < buffer_size / page_size; page += 53)
            if (shape.selected[page * page_size / window_size]) expected.push_back(page);
    }
    return expected;
}

int main() {
    SYSTEM_INFO info{};
    GetSystemInfo(&info);
    require(info.dwPageSize && window_size % info.dwPageSize == 0, "Unexpected system page size");
    Region region;
    require(region.start != nullptr, "MEM_WRITE_WATCH allocation failed");
    Watch watch(region.start, info.dwPageSize);
    const std::array shapes { Shape("adjacent", false), Shape("gapped", true) };

    puts("shape,pattern,arm,round,calls,bytes,returned,kept,repeats,total_ns,checksum");
    for (bool dirty : {false, true}) {
        require(ResetWriteWatch(region.start, buffer_size) == 0, "ResetWriteWatch failed");
        if (dirty) {
            volatile char* memory = region.start;
            for (std::size_t page = 3; page < buffer_size / info.dwPageSize; page += 53)
                memory[page * info.dwPageSize] = 1;
        }
        for (const auto& shape : shapes) {
            const auto expected = expected_pages(shape, dirty, info.dwPageSize);
            std::array<Counts, 2> checked{};
            for (bool batch : {false, true}) {
                std::vector<std::size_t> actual;
                checked[batch] = watch.run(shape, batch, &actual);
                std::sort(actual.begin(), actual.end());
                require(actual == expected, "Dirty-page membership differs from independent expected set");
            }
            for (unsigned round = 0; round < rounds; ++round) {
                for (unsigned arm = 0; arm < 2; ++arm) {
                    const bool batch = ((arm + round) % 2) != 0;
                    std::uint64_t total_checksum = 0;
                    const auto begin = std::chrono::steady_clock::now();
                    for (unsigned i = 0; i < repeats; ++i)
                        total_checksum += watch.run(shape, batch).checksum;
                    const auto duration = std::chrono::steady_clock::now() - begin;
                    require(total_checksum == checked[batch].checksum * repeats, "Query result changed during timing");
                    const auto bytes = (batch ? shape.end - shape.first : shape.count) * window_size;
                    std::printf("%s,%s,%s,%u,%zu,%zu,%zu,%zu,%u,%lld,%llu\n",
                        shape.name, dirty ? "dirty" : "clean", batch ? "union" : "ranges",
                        round, batch ? 1u : shape.count, bytes, checked[batch].returned, checked[batch].kept,
                        repeats, static_cast<long long>(std::chrono::duration_cast<std::chrono::nanoseconds>(duration).count()),
                        static_cast<unsigned long long>(total_checksum));
                }
            }
        }
    }
}
