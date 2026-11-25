"""Create the separate Hubble preview from exactly the measured Gaussian harness."""

from pathlib import Path
import re
from shutil import copy2

ROOT = Path(__file__).resolve().parent
CASE = ROOT / "hubble_case"
OLD_HASH = "88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5"
NEW_HASH = "3a19c5dd8a927a9334bb1229a6d63711b1c0c767fb27e2286e7c84a3e2c2f5f4"
ORACLE = """function calculateReference(input, sigma) {
    const radius = 16;
    const weights = Array.from({length: 2*radius + 1}, (_, i) => Math.exp(-((i-radius)**2)/(2*sigma**2)));
    const sum = weights.reduce((a, b) => a + b);
    weights.forEach((value, i) => { weights[i] = value/sum; });
    const temporary = new Float64Array(pixelCount);
    const smooth = new Float64Array(pixelCount);
    const output = new Float64Array(pixelCount);
    const bound = (value, limit) => Math.max(0, Math.min(limit - 1, value));
    for (let y = 0; y < height; ++y) {
        const rows = weights.map((_, i) => bound(y+i-radius, height)*width);
        for (let x = 0; x < width; ++x) {
            let value = 0;
            for (let k = 0; k < weights.length; ++k) value += input[rows[k]+x]*weights[k];
            temporary[y*width+x] = value;
        }
    }
    for (let y = 0; y < height; ++y) {
        const row = y*width;
        for (let x = 0; x < width; ++x) {
            let value = 0;
            for (let k = 0; k < weights.length; ++k) value += temporary[row+bound(x+k-radius, width)]*weights[k];
            smooth[row+x] = value;
        }
    }
    for (let y = 0; y < height; ++y) {
        const row = y*width;
        const above = bound(y-1, height)*width;
        const below = bound(y+1, height)*width;
        for (let x = 0; x < width; ++x) {
            output[row+x] = (4*smooth[row+x]-smooth[row+bound(x-1,width)]-smooth[row+bound(x+1,width)]
                             -smooth[above+x]-smooth[below+x])*sigma*sigma;
        }
    }
    return output;
}
"""


def write_transformation(name, edits, *, before=None):
    source = (ROOT / name).read_text(encoding="utf-8")
    if before:
        source = before(source)
    for old, replacement in edits:
        if old not in source:
            raise ValueError(f"Expected the source fragment {old!r} in {name}")
        source = source.replace(old, replacement)
    (CASE / name).write_text(source, encoding="utf-8", newline="\n")


def replace_oracle(source):
    result, count = re.subn(r"function calculateReference\(input, sigma\) \{.*?\n\}\n", ORACLE, source, flags=re.S)
    if count != 1:
        raise ValueError("Expected one independent CPU reference")
    return result


def main():
    CASE.mkdir(exist_ok=True)
    for name in ("callback_parking.mjs", "hubble_deep_field.jpg", "patch_preview_glue.py", "browser_runner.py"):
        copy2(ROOT / name, CASE / name)
    write_transformation("preview_host.cpp", (
        ("gaussian-preview.h", "log-preview.h"), ("gaussian_preview", "log_preview"),
        ("512 * 512", "1000 * 872"), ("{0, 512, 1, 0}, {0, 512, 512, 0}", "{0, 1000, 1, 0}, {0, 872, 1000, 0}"),
        ("sigma <= 3.0f", "sigma <= 5.0f"),
    ))
    write_transformation("cpu_preview_host.cpp", (
        ("512 * 512", "1000 * 872"),
        ("{0, 512, 1, 0}, {0, 512, 512, 0}", "{0, 1000, 1, 0}, {0, 872, 1000, 0}"),
        ("sigma <= 3.0f", "sigma <= 5.0f"),
    ))
    write_transformation("preview.html", (
        ('width="512" height="512"', 'width="1000" height="872"'),
        ("photograph preview", "scale-normalized Laplacian of Gaussian"),
    ))
    photo = ("astronaut.png", "hubble_deep_field.jpg")
    write_transformation("preview_parking.mjs", (
        ("const size = 512;\nconst pixelCount = size * size;", "const width = 1000, height = 872;\nconst pixelCount = width * height;"),
        (OLD_HASH, NEW_HASH), photo, ("'image/png'", "'image/jpeg'"),
        ("bitmap.width !== size || bitmap.height !== size", "bitmap.width !== width || bitmap.height !== height"),
        ("OffscreenCanvas(size, size)", "OffscreenCanvas(width, height)"),
        ("0, 0, size, size", "0, 0, width, height"), ("createImageData(size, size)", "createImageData(width, height)"),
        ("0.55, 0.75, 1, 1.45, 2.15, 2.95, 2.55, 1.8, 1.25, 0.62", "0.55, 1.25, 2.25, 3.1, 4.2, 5, 4.7, 3.5, 1.8, 0.8"),
        ("pixels[p]*255", "128 + pixels[p]*2040"), ("5e-6", "1e-4"),
        ("pairs, frames, size, trace", "pairs, frames, size: width, height, trace"),
    ), before=replace_oracle)
    write_transformation("run_preview.py", (
        (OLD_HASH, NEW_HASH), photo, ("image/png", "image/jpeg"),
        ('    "preview.mjs": "text/javascript; charset=utf-8",\n', ""),
    ))
    write_transformation("run_parking_preview.py", (
        ('report["size"] != 512', 'report["size"] != 1000 or report["height"] != 872'),
        ("512 * 512", "1000 * 872"), ("5e-6", "1e-4"),
        ("Sigma change through Halide/WebGPU", "Hubble photograph Laplacian-of-Gaussian scale change through Halide/WebGPU"),
    ))


if __name__ == "__main__":
    main()
