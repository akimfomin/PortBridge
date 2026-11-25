#include "cpu-gaussian-preview.h"
#include <emscripten/emscripten.h>
#include <stdint.h>

static float input_pixels[512 * 512];
static float output_pixels[512 * 512];
static halide_dimension_t dims[2] = {{0, 512, 1, 0}, {0, 512, 512, 0}};
static halide_buffer_t source, output;

extern "C" EMSCRIPTEN_KEEPALIVE float *preview_input() {
    return input_pixels;
}

extern "C" EMSCRIPTEN_KEEPALIVE float *preview_output() {
    return output_pixels;
}

static void buffer_init(halide_buffer_t *buffer, float *storage) {
    buffer->host = reinterpret_cast<uint8_t *>(storage);
    buffer->type = halide_type_t(halide_type_float, 32);
    buffer->dimensions = 2;
    buffer->dim = dims;
}

extern "C" EMSCRIPTEN_KEEPALIVE int preview_upload() {
#ifdef CPU_PREVIEW_THREADS
    halide_set_num_threads(CPU_PREVIEW_THREADS);
#endif
    buffer_init(&source, input_pixels);
    buffer_init(&output, output_pixels);
    return 0;
}

extern "C" EMSCRIPTEN_KEEPALIVE int preview_render(float sigma) {
    if (!(sigma >= 0.5f && sigma <= 3.0f)) return -1;
    return cpu_gaussian_preview(&source, sigma, &output);
}
