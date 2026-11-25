#include "HalideRuntime.h"
#include <emscripten/emscripten.h>
#include <stdio.h>

static void report_test_error(void *, const char *message) {
    fputs(message, stderr);
    fputc('\n', stderr);
}

extern "C" EMSCRIPTEN_KEEPALIVE void preview_enable_recoverable_errors() {
    halide_set_error_handler(report_test_error);
}
