#include "../point_workers.hpp"

#include <cstddef>
#include <cstdint>
#if defined(__AVX2__)
#  include <immintrin.h>
#endif

#if defined(_WIN32)
#  define PORTBRIDGE_EXPORT __declspec(dllexport)
#else
#  define PORTBRIDGE_EXPORT __attribute__((visibility("default")))
#endif

namespace {

struct PreviewWorkers {
    std::vector<point_workers::Block> blocks;
    point_workers::WorkerTeam team;

    PreviewWorkers(std::uint32_t count, std::uint32_t workers)
        : blocks(point_workers::make_blocks(count, workers)), team(blocks) {}
};

}  // namespace

extern "C" {

PORTBRIDGE_EXPORT void *pb_view_create(std::uint32_t count, std::uint32_t workers) noexcept
{
    if (count == 0 || workers == 0 || workers > 64 || workers > count) {
        return nullptr;
    }
    try {
        return new PreviewWorkers(count, workers);
    }
    catch (...) {
        return nullptr;
    }
}

PORTBRIDGE_EXPORT void pb_view_destroy(void *state) noexcept
{
    delete static_cast<PreviewWorkers *>(state);
}

PORTBRIDGE_EXPORT int pb_view_edit(void *state, const float *source, float *target,
                                   float threshold) noexcept
{
    if (state == nullptr || source == nullptr || target == nullptr || source == target) {
        return 0;
    }
    try {
        auto &work = *static_cast<PreviewWorkers *>(state);
        work.team.run([&](point_workers::Block &block) {
            for (std::size_t i = block.begin; i < block.end; ++i) {
                const std::size_t index = i * 4;
                const bool edit = source[index] < threshold && source[index + 3] == 1.0f;
                target[index] = source[index];
                target[index + 1] = source[index + 1];
                target[index + 2] = edit ? 0.0f : source[index + 2];
                target[index + 3] = edit ? 2.0f : source[index + 3];
            }
        });
        return 1;
    }
    catch (...) {
        return 0;
    }
}

PORTBRIDGE_EXPORT int pb_view_mask(void *state, const float *x, const float *limits,
                                   const std::uint32_t *eligible, std::uint32_t *target,
                                   float threshold) noexcept
{
    if (state == nullptr || x == nullptr || limits == nullptr || eligible == nullptr || target == nullptr) {
        return 0;
    }
    try {
        auto &work = *static_cast<PreviewWorkers *>(state);
        work.team.run([&](point_workers::Block &block) {
            const std::size_t first = (block.begin + 31) / 32;
            const std::size_t last = (block.end + 31) / 32;
            for (std::size_t word = first; word < last; ++word) {
                const std::uint32_t class_bits = eligible[word];
                if (class_bits == 0 || threshold <= limits[2 * word]) {
                    target[word] = 0;
                    continue;
                }
                if (threshold > limits[2 * word + 1]) {
                    target[word] = class_bits;
                    continue;
                }
                const std::size_t begin = word * 32;
                std::uint32_t bits = 0;
#if defined(__AVX2__)
                const __m256 cut = _mm256_set1_ps(threshold);
                for (std::size_t bit = 0; bit < 32; bit += 8) {
                    const __m256 coords = _mm256_loadu_ps(x + begin + bit);
                    const int less = _mm256_movemask_ps(_mm256_cmp_ps(coords, cut, _CMP_LT_OQ));
                    bits |= static_cast<std::uint32_t>(less) << bit;
                }
#else
                for (std::size_t bit = 0; bit < 32; ++bit) {
                    bits |= static_cast<std::uint32_t>(x[begin + bit] < threshold) << bit;
                }
#endif
                target[word] = bits & class_bits;
            }
        });
        return 1;
    }
    catch (...) {
        return 0;
    }
}

}  // extern "C"
