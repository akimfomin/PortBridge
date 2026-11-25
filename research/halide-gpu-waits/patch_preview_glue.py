"""Connect a pinned Emscripten 4.0.17 WebGPU bridge to callback parking."""

import argparse
from pathlib import Path


SLEEP = "var _emscripten_sleep=ms=>Asyncify.handleSleep(wakeUp=>safeSetTimeout(wakeUp,ms));"
BRIDGES = {
    "_wgpuDevicePopErrorScope": ("device.popErrorScope().then(", "_wgpuDevicePushErrorScope"),
    "_wgpuBufferMapAsync": ("buffer.mapAsync(mode,offset,size).then(", "_wgpuBufferReference"),
}


def attach_parking(source):
    if source.count(SLEEP) != 1:
        raise ValueError("Expected the pinned Asyncify sleep import")
    source = source.replace(
        SLEEP,
        'var parking=createCallbackParking(()=>Module["portbridgeCallbackParking"]===true,'
        "safeSetTimeout,callUserCallback);"
        "var _emscripten_sleep=ms=>Asyncify.handleSleep(wakeUp=>parking.sleep(wakeUp,ms));",
    )
    for name, (operation, next_name) in BRIDGES.items():
        definition = f"var {name}="
        if source.count(definition) != 1:
            raise ValueError(f"Expected one generated bridge for {name}")
        start = source.index(definition)
        end = source.index(f";var {next_name}=", start)
        function = source[start:end]
        if function.count(operation) != 1 or not function.endswith(")}"):
            raise ValueError(f"Unexpected call shape for {name}")
        function = function.replace(operation, f"parking.watch({operation}")[:-1] + ")}"
        source = source[:start] + function + source[end:]
    return "import {createCallbackParking} from './callback_parking.mjs';\n" + source


FAILURE_PROBE = """
        app._preview_enable_recoverable_errors();
        const errors = [];
        for (const variant of ['stock', 'park']) {
            app.portbridgeCallbackParking = variant === 'park';
            record.start(variant);
            const native = GPUDevice.prototype.createComputePipeline;
            const firstMessage = messages.length;
            let injected = false;
            GPUDevice.prototype.createComputePipeline = function (descriptor) {
                if (injected) return native.call(this, descriptor);
                injected = true;
                return native.call(this, {
                    ...descriptor,
                    compute: { ...descriptor.compute, entryPoint: 'portbridge_missing_test_entry' },
                });
            };
            let status;
            try {
                status = await app.ccall('preview_render', 'number', ['number'], [sigmas[0]], { async: true });
            } finally {
                GPUDevice.prototype.createComputePipeline = native;
            }
            const recorded = record.finish();
            const log = messages.slice(firstMessage);
            if (!injected || !status || !log.some(message => /validation error/i.test(message))) {
                throw Error(`Expected the scoped validation failure for ${variant}: ${status}, ${log}`);
            }
            record.start(variant);
            const { pixels } = await render(sigmas[0]);
            const recoveryHash = await sha256(pixels);
            if (recoveryHash !== referenceHashes.get(sigmas[0])) throw Error(`Recovery failed for ${variant}`);
            record.finish();
            errors.push({ variant, status, log, recoveryHash, errorPops: recorded.errorPops });
        }
        if (errors[0].status !== errors[1].status ||
            errors[0].errorPops !== errors[1].errorPops) throw Error('Different scoped error observations');
"""


def add_preview_variants(source, failure_probe=False):
    host = "./preview_host_failures_parking.mjs" if failure_probe else "./preview_host_parking.mjs"
    edits = (
        ("./preview_host.mjs", host, 1),
        (
            "const size = 512;",
            """const variants = ['stock', 'reuse', 'park', 'reuse-park'];
const orders = [
    [0, 1, 3, 2], [1, 2, 0, 3], [2, 3, 1, 0], [3, 0, 2, 1],
].map(order => order.map(index => variants[index]));
const size = 512;""",
            1,
        ),
        ("mode = which;", "mode = which.startsWith('reuse') ? 'reuse' : 'stock';", 1),
        ("['stock', 'reuse', 'reuse', 'stock']", "variants", 1),
        ("pair % 2 === 0 ? ['stock', 'reuse'] : ['reuse', 'stock']",
         "orders[pair % orders.length]", 1),
        ("record.start(mode);",
         "app.portbridgeCallbackParking = mode.endsWith('park');\n            record.start(mode);", 2),
    )
    for older, replacement, expected in edits:
        if source.count(older) != expected:
            raise ValueError(f"Unexpected preview source shape at {older}")
        source = source.replace(older, replacement)
    if failure_probe:
        marker = "        return { adapter, userAgent:"
        if source.count(marker) != 1 or source.count("trace, sigmas, warmup, results, hashes:") != 1:
            raise ValueError("Unexpected preview report shape")
        source = source.replace(marker, FAILURE_PROBE + marker)
        source = source.replace("trace, sigmas, warmup, results, hashes:",
                                "trace, sigmas, warmup, results, errors, hashes:")
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--app", action="store_true", help="vary pipeline reuse and callback parking")
    parser.add_argument("--failure-probe", action="store_true", help="exercise a real WebGPU validation failure")
    arguments = parser.parse_args()
    stock = arguments.stock.read_text(encoding="utf-8")
    candidate = (add_preview_variants(stock, arguments.failure_probe)
                 if arguments.app else attach_parking(stock))
    with arguments.candidate.open("x", encoding="utf-8", newline="\n") as output:
        output.write(candidate)


if __name__ == "__main__":
    main()
