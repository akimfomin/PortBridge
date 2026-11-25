import createModule from './preview_host.mjs';

const size = 512;
const pixelCount = size * size;
const imageSha256 = '88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5';
const sigmaSequence = [0.55, 0.75, 1, 1.45, 2.15, 2.95, 2.55, 1.8, 1.25, 0.62].map(Math.fround);
const params = new URLSearchParams(location.search);
const pairs = Number(params.get('pairs') ?? 8);
const frames = Number(params.get('frames') ?? 10);
const trace = params.get('trace') === '1';
const canvas = document.getElementById('preview');
const context = canvas.getContext('2d');
const button = document.getElementById('run');
const output = document.getElementById('output');

function pipelineKey(descriptor) {
    const compute = descriptor.compute;
    if (descriptor.layout !== 'auto' || !compute?.module || typeof compute.entryPoint !== 'string') {
        return null;
    }
    if (Object.keys(descriptor).some(key => !['label', 'layout', 'compute'].includes(key)) ||
        Object.keys(compute).some(key => !['module', 'entryPoint', 'constants'].includes(key))) {
        return null;
    }
    const constants = Object.entries(compute.constants ?? {}).sort(([name], [other]) =>
        name < other ? -1 : name > other ? 1 : 0);
    if (constants.some(([, value]) => typeof value !== 'number' || !Number.isFinite(value))) return null;
    return JSON.stringify([descriptor.label, compute.entryPoint, constants.map(([name, value]) =>
        [name, Object.is(value, -0) ? '-0' : value])]);
}

function installRecorder() {
    const restore = [];
    const devices = new WeakMap();
    const shaderIds = new WeakMap();
    const capturedAdapters = [];
    let nextShaderId = 0;
    let recorded;
    let pending = [];
    let mode = 'stock';
    let waitKind;

    function wrap(prototype, method, makeWrapper) {
        const native = prototype[method];
        prototype[method] = makeWrapper(native);
        restore.push(() => { prototype[method] = native; });
    }

    wrap(GPU.prototype, 'requestAdapter', native => async function (...args) {
        const adapter = await native.apply(this, args);
        if (adapter) {
            const fields = ['vendor', 'architecture', 'device', 'description', 'isFallbackAdapter'];
            capturedAdapters.push(Object.fromEntries(fields.map(key => [key, adapter.info[key]])));
        }
        return adapter;
    });

    wrap(GPUDevice.prototype, 'createShaderModule', native => function (desc) {
        if (recorded) ++recorded.shaderCreates;
        return native.call(this, desc);
    });

    wrap(GPUDevice.prototype, 'createComputePipeline', native => function (desc) {
        const key = trace || mode === 'reuse' ? pipelineKey(desc) : null;
        if (recorded) {
            ++recorded.pipelineRequests;
            if (trace && key !== null) {
                const shader = desc.compute.module;
                if (!shaderIds.has(shader)) shaderIds.set(shader, ++nextShaderId);
                recorded.descriptors.add(`${shaderIds.get(shader)}:${key}`);
            }
        }
        let byDescriptor;
        if (mode === 'reuse' && key !== null) {
            if (!devices.has(this)) devices.set(this, new WeakMap());
            const modules = devices.get(this);
            const shader = desc.compute.module;
            if (!modules.has(shader)) modules.set(shader, new Map());
            byDescriptor = modules.get(shader);
            if (byDescriptor.has(key)) return byDescriptor.get(key);
        }
        if (recorded) ++recorded.nativePipelineCreates;
        const started = trace ? performance.now() : 0;
        const pipeline = native.call(this, desc);
        if (trace && recorded) recorded.pipelineCreateMs += performance.now() - started;
        if (byDescriptor && byDescriptor.size < 8) pending.push([byDescriptor, key, pipeline]);
        return pipeline;
    });

    wrap(GPUDevice.prototype, 'popErrorScope', native => function () {
        const scope = recorded;
        if (scope) ++scope.errorPops;
        if (trace) waitKind = 'scope';
        const start = trace ? performance.now() : 0;
        const result = native.call(this);
        if (trace && scope) {
            result.then(error => {
                scope.errorCallbackMs += performance.now() - start;
                if (error) ++scope.gpuErrors;
            }, () => { ++scope.gpuErrors; });
        }
        return result;
    });

    for (const [prototype, method, counter] of [
        [GPUQueue.prototype, 'submit', 'submissions'],
        [GPUCommandEncoder.prototype, 'copyBufferToBuffer', 'bufferCopies'],
    ]) {
        wrap(prototype, method, native => function (...args) {
            if (recorded) ++recorded[counter];
            return native.apply(this, args);
        });
    }

    wrap(GPUBuffer.prototype, 'mapAsync', native => function (...args) {
        const active = recorded;
        if (active) ++active.bufferMaps;
        if (trace) waitKind = 'map';
        const start = trace ? performance.now() : 0;
        const result = native.apply(this, args);
        if (trace && active) {
            result.then(() => { active.mapCallbackMs += performance.now() - start; }, () => { ++active.gpuErrors; });
        }
        return result;
    });

    if (trace) {
        wrap(globalThis, 'setTimeout', native => function (callback, delay, ...args) {
            const active = recorded;
            if (!active || delay !== 1 || !Error().stack?.includes('_emscripten_sleep')) {
                return native.call(globalThis, callback, delay, ...args);
            }
            const category = waitKind ?? 'other';
            ++active.pollCounts[category];
            const start = performance.now();
            return native.call(globalThis, (...values) => {
                active.pollMs[category] += performance.now() - start;
                return callback(...values);
            }, delay, ...args);
        });
    }

    return {
        start(which) {
            mode = which;
            waitKind = undefined;
            recorded = {
                descriptors: new Set(), shaderCreates: 0, pipelineRequests: 0,
                nativePipelineCreates: 0, errorPops: 0, submissions: 0, bufferCopies: 0,
                bufferMaps: 0, ...(trace ? {
                    pipelineCreateMs: 0, errorCallbackMs: 0, mapCallbackMs: 0, gpuErrors: 0,
                    pollCounts: { scope: 0, map: 0, other: 0 }, pollMs: { scope: 0, map: 0, other: 0 },
                } : {}),
            };
        },
        finish() {
            const { descriptors, ...counts } = recorded;
            recorded = undefined;
            return { ...counts, ...(trace ? { distinctDescriptors: descriptors.size } : {}) };
        },
        commit() {
            for (const [byDescriptor, key, pipeline] of pending) {
                if (byDescriptor.size < 8) byDescriptor.set(key, pipeline);
            }
            pending = [];
        },
        actualAdapter() {
            if (capturedAdapters.length !== 1 || capturedAdapters[0].isFallbackAdapter !== false) {
                throw Error(`Expected one device acquisition by the Halide runtime, got ${JSON.stringify(capturedAdapters)}`);
            }
            return capturedAdapters[0];
        },
        restore() {
            for (const reset of restore.reverse()) reset();
        },
    };
}

async function sha256(data) {
    return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', data)),
        octet => octet.toString(16).padStart(2, '0')).join('');
}

async function loadPhoto() {
    const response = await fetch('./astronaut.png');
    if (!response.ok) throw Error(`Source image failed: ${response.status}`);
    const image = await response.arrayBuffer();
    if (await sha256(image) !== imageSha256) throw Error('Wrong source image');
    const bitmap = await createImageBitmap(new Blob([image], { type: 'image/png' }));
    if (bitmap.width !== size || bitmap.height !== size) throw Error('Unexpected image dimensions');
    const decoding = new OffscreenCanvas(size, size).getContext('2d', { willReadFrequently: true });
    decoding.drawImage(bitmap, 0, 0);
    bitmap.close();
    const rgba = decoding.getImageData(0, 0, size, size).data;
    const input = new Float32Array(pixelCount);
    for (let p = 0; p < pixelCount; ++p) {
        input[p] = (rgba[4*p]*0.2126 + rgba[4*p+1]*0.7152 + rgba[4*p+2]*0.0722) / 255;
    }
    return input;
}

function calculateReference(input, sigma) {
    const weights = Array.from({length: 9}, (_, i) => Math.exp(-((i - 4)**2)/(2*sigma**2)));
    const sum = weights.reduce((a, b) => a + b);
    const temporary = new Float64Array(pixelCount);
    const reference = new Float64Array(pixelCount);
    const bound = value => Math.max(0, Math.min(size - 1, value));
    for (let y = 0; y < size; ++y) {
        for (let x = 0; x < size; ++x) {
            for (let k = 0; k < 9; ++k) temporary[y*size+x] += input[bound(y+k-4)*size+x] * weights[k] / sum;
        }
    }
    for (let y = 0; y < size; ++y) {
        for (let x = 0; x < size; ++x) {
            for (let k = 0; k < 9; ++k) reference[y*size+x] += temporary[y*size+bound(x+k-4)] * weights[k] / sum;
        }
    }
    return reference;
}

function draw(pixels, rgba) {
    for (let p = 0; p < pixelCount; ++p) {
        rgba.data[4*p] = rgba.data[4*p+1] = rgba.data[4*p+2] = pixels[p]*255;
        rgba.data[4*p+3] = 255;
    }
    context.putImageData(rgba, 0, 0);
}

async function runComparison() {
    if (!globalThis.GPUDevice || !context) throw Error('WebGPU or canvas unavailable');
    if (!Number.isInteger(pairs) || pairs < 2 || pairs > 20 || pairs % 2 ||
        !Number.isInteger(frames) || frames < 2 || frames > sigmaSequence.length) {
        throw Error('Use 2 to 20 even pairs and 2 to 10 frames');
    }
    const sigmas = sigmaSequence.slice(0, frames);
    const input = await loadPhoto();
    const inputSha256 = await sha256(input);
    const references = new Map(sigmas.map(sigma => [sigma, calculateReference(input, sigma)]));
    const referenceHashes = new Map();
    const rgba = context.createImageData(size, size);
    const messages = [];
    const record = installRecorder();
    try {
        const app = await createModule({ printErr: message => messages.push(message) });
        app.HEAPF32.set(input, app._preview_input()/4);
        const outputStart = app._preview_output()/4;
        const render = async sigma => {
            const start = performance.now();
            const status = await app.ccall('preview_render', 'number', ['number'], [sigma], { async: true });
            const readbackEnd = performance.now();
            if (status !== 0) throw Error(`Halide preview returned ${status}: ${messages.join('\n')}`);
            record.commit();
            const pixels = app.HEAPF32.subarray(outputStart, outputStart + pixelCount);
            draw(pixels, rgba);
            const bitmapEnd = performance.now();
            return { pixels, inputToBitmapMs: bitmapEnd - start, inputToReadbackMs: readbackEnd - start };
        };
        const start = performance.now();
        const status = await app.ccall('preview_upload', 'number', [], [], { async: true });
        const initializeAndUploadMs = performance.now() - start;
        if (status !== 0) throw Error(`Halide upload returned ${status}: ${messages.join('\n')}`);
        const adapter = record.actualAdapter();
        const warmup = [];
        for (const mode of ['stock', 'reuse', 'reuse', 'stock']) {
            record.start(mode);
            const observed = await render(sigmas[0]);
            const { pixels, ...timings } = observed;
            warmup.push({ mode, ...timings, ...record.finish() });
        }
        const results = [];
        for (let pair = 0; pair < pairs; ++pair) {
            const order = pair % 2 === 0 ? ['stock', 'reuse'] : ['reuse', 'stock'];
            for (const mode of order) {
                record.start(mode);
                const times = [];
                let maxAbsoluteError = 0;
                for (const sigma of sigmas) {
                    const { pixels, ...timing } = await render(sigma);
                    const reference = references.get(sigma);
                    for (let p = 0; p < pixelCount; ++p) {
                        const error = Math.abs(pixels[p] - reference[p]);
                        if (!Number.isFinite(error) || error > 5e-6) throw Error(`Reference mismatch at ${sigma}:${p}: ${error}`);
                        maxAbsoluteError = Math.max(maxAbsoluteError, error);
                    }
                    const hash = await sha256(pixels);
                    if (!referenceHashes.has(sigma)) referenceHashes.set(sigma, hash);
                    if (referenceHashes.get(sigma) !== hash) throw Error(`Outputs were not bit-identical at ${sigma}`);
                    times.push(timing);
                }
                results.push({ mode, pair, times, maxAbsoluteError, ...record.finish() });
            }
        }
        return { adapter, userAgent: navigator.userAgent, imageSha256, inputSha256, initializeAndUploadMs,
                 pairs, frames, size, trace, sigmas, warmup, results, hashes: Array.from(referenceHashes) };
    } finally {
        record.restore();
    }
}

async function run() {
    button.disabled = true;
    output.textContent = 'Running...';
    let reply;
    try {
        reply = { ok: true, report: await runComparison() };
    } catch (error) {
        reply = { ok: false, error: String(error.stack || error) };
    }
    output.textContent = JSON.stringify(reply, null, 2);
    const path = params.get('result');
    if (path && /^\/result\/[A-Za-z0-9_-]+$/.test(path)) {
        const result = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                         body: JSON.stringify(reply) });
        if (!result.ok) output.textContent += `\nDelivery failed: ${result.status}`;
    }
    button.disabled = false;
}

button.addEventListener('click', run);
if (params.get('run') === '1') await run();
