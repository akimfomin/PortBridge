"""Run the same photograph preview through Halide's vectorized Wasm CPU path."""
import argparse
import math
from pathlib import Path
import re
from statistics import median

import run_preview


CPU_COMPARISON = """async function runComparison() {
    if (!context || !Number.isInteger(frames) || frames < 2 || frames > sigmaSequence.length) {
        throw Error('Canvas or required frame count unavailable');
    }
    const sigmas = sigmaSequence.slice(0, frames);
    const input = await loadPhoto();
    const inputSha256 = await sha256(input);
    const references = new Map(sigmas.map(sigma => [sigma, calculateReference(input, sigma)]));
    const hashes = new Map();
    const rgba = context.createImageData(size, size);
    const app = await createModule();
    app.HEAPF32.set(input, app._preview_input()/4);
    const outputStart = app._preview_output()/4;
    if (app._preview_upload() !== 0) throw Error('Halide CPU input binding failed');

    function render(sigma) {
        const start = performance.now();
        if (app._preview_render(sigma) !== 0) throw Error('Halide CPU preview failed');
        const resultEnd = performance.now();
        const pixels = app.HEAPF32.subarray(outputStart, outputStart+pixelCount);
        draw(pixels, rgba);
        return { pixels, inputToBitmapMs: performance.now()-start, inputToResultMs: resultEnd-start };
    }

    for (let i = 0; i < 4; ++i) render(sigmas[0]);
    const results = [];
    let maxAbsoluteError = 0;
    for (let repetition = 0; repetition < pairs*2; ++repetition) {
        const sample = [];
        for (const sigma of sigmas) {
            const { pixels, ...times } = render(sigma);
            const reference = references.get(sigma);
            for (let p = 0; p < pixelCount; ++p) {
                const error = Math.abs(pixels[p]-reference[p]);
                if (!Number.isFinite(error) || error > 5e-6) throw Error(`CPU mismatch at ${sigma}:${p}: ${error}`);
                maxAbsoluteError = Math.max(maxAbsoluteError, error);
            }
            const hash = await sha256(pixels.buffer instanceof ArrayBuffer ? pixels : pixels.slice());
            if (hashes.has(sigma) && hash !== hashes.get(sigma)) throw Error(`CPU output was unstable at ${sigma}`);
            hashes.set(sigma, hash);
            sample.push(times);
        }
        results.push(sample);
    }
    return { userAgent: navigator.userAgent, imageSha256, inputSha256, pairs, frames, size, results,
             maxAbsoluteError, hashes: Array.from(hashes) };
}

"""


class CpuHandler(run_preview.PreviewHandler):
    def __init__(self, *args, assets, **kwargs):
        assets = dict(assets)
        assets["/preview.mjs"] = assets["/cpu_preview.mjs"]
        super().__init__(*args, assets=assets, **kwargs)

    def send_header(self, key, value):
        if key.casefold() == "content-security-policy":
            super().send_header("Cross-Origin-Opener-Policy", "same-origin")
            super().send_header("Cross-Origin-Embedder-Policy", "require-corp")
            value += "; worker-src 'self'"
        super().send_header(key, value)


def summarise(payload, args, inventory, reference):
    if payload.get("ok") is not True:
        raise ValueError("Browser CPU preview failed: " + str(payload.get("error", "empty result")))
    report = payload["report"]
    samples = report["results"]
    if (
        report["imageSha256"] != run_preview.IMAGE_SHA256 or report["pairs"] != args.pairs
        or report["frames"] != args.frames or report["size"] != args.width or report.get("height", 512) != args.height
        or len(report["hashes"]) != args.frames or len(samples) != args.pairs*2
        or len({len(row) for row in samples}) != 1 or len(samples[0]) != args.frames
        or not 0 <= report["maxAbsoluteError"] <= args.tolerance
    ):
        raise ValueError("CPU preview report did not match the requested workload")

    for row in samples:
        for timing in row:
            if not (0 <= timing["inputToResultMs"] <= timing["inputToBitmapMs"] and
                    math.isfinite(timing["inputToBitmapMs"])):
                raise ValueError("Invalid CPU latency sample")

    def timing_summary(field):
        values = [sum(observation[field] for observation in row)/args.frames for row in samples]
        return {"median_ms_per_preview": median(values), "mean_ms_per_repetition": values}

    return {
        "scope": f"Matching CPU Halide Wasm SIMD, {args.width}×{args.height} {args.case_name}, sigma change to canvas bitmap",
        "worker_variant": "threaded" if args.threads else "single-threaded",
        "exclusions": "Initial image decode, CPU reference checks, hashing, browser compositor and display scanout",
        "prepared_samples": args.pairs*2*args.frames,
        "verified_values": args.width*args.height*args.pairs*2*args.frames,
        "max_absolute_error": report["maxAbsoluteError"],
        "sample_count": len(samples), "frames_per_repetition": args.frames,
        "image_file_sha256": report["imageSha256"], "decoded_luma_sha256": report["inputSha256"],
        "browser_user_agent": report["userAgent"],
        "input_to_bitmap": timing_summary("inputToBitmapMs"),
        "input_to_cpu_result": timing_summary("inputToResultMs"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--chrome", type=Path, default=Path(
        run_preview.os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe")
    parser.add_argument("--pairs", type=int, default=8)
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=55)
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--threads", action="store_true")
    args = parser.parse_args()
    args.expect_gpu = "RTX 4070 Ti SUPER"
    args.trace = False
    binary = "cpu_preview_host_threaded" if args.threads else "cpu_preview_host"
    args.wasm_asset = binary + ".wasm"
    args.width, args.height, args.tolerance = (1000, 872, 1e-4) if args.log else (512, 512, 5e-6)
    args.case_name = "Hubble LoG" if args.log else "Astronaut Gaussian"

    js_comparison = CPU_COMPARISON
    source_name = "preview.mjs"
    if args.log:
        run_preview.ROOT = run_preview.ROOT / "hubble_case"
        run_preview.IMAGE_SHA256 = "3a19c5dd8a927a9334bb1229a6d63711b1c0c767fb27e2286e7c84a3e2c2f5f4"
        source_name = "preview_parking.mjs"
        js_comparison = CPU_COMPARISON.replace("createImageData(size, size)", "createImageData(width, height)").replace(
            "frames, size, results", "frames, size: width, height, results").replace("5e-6", "1e-4")

    source = (run_preview.ROOT / source_name).read_text(encoding="utf-8")
    source = re.sub(r"'\./preview_host(?:_parking)?\.mjs'", f"'./{binary}.mjs'", source)
    source, removed = re.subn(r"function pipelineKey\(descriptor\).*?(?=async function sha256\()", "", source, flags=re.S)
    source, replaced = re.subn(r"async function runComparison\(\).*?(?=async function run\(\))", js_comparison, source, flags=re.S)
    if removed != 1 or replaced != 1:
        raise ValueError("Unexpected shape for the GPU preview source")
    (run_preview.ROOT / "cpu_preview.mjs").write_text(source, encoding="utf-8", newline="\n")
    run_preview.PreviewHandler = CpuHandler
    run_preview.summarise = summarise
    run_preview.ASSETS = {
        "preview.html": "text/html; charset=utf-8",
        "cpu_preview.mjs": "text/javascript; charset=utf-8",
        binary + ".mjs": "text/javascript; charset=utf-8",
        binary + ".wasm": "application/wasm",
        "astronaut.png": "image/png",
    }
    if args.log:
        run_preview.ASSETS["hubble_deep_field.jpg"] = "image/jpeg"
        run_preview.IMAGE_ASSET = "hubble_deep_field.jpg"
        run_preview.ASSETS.pop("astronaut.png")
    run_preview.run(args)


if __name__ == "__main__":
    main()
