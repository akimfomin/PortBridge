"""Render the pinned, unmodified Khronos Mobile NeRF MLP fragment on shared inputs."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import struct
import subprocess


SOURCE_HASHES = {
    "quad.vert": "e57f9e925495f85fffa9d6d69436c9353f6e9f66de5cce4bcb4e4986b7ebbada",
    "mlp_combo.frag": "67d467aafa1fecb9cb92816abd313b84d55cb09241877e46d6e5821ee6137764",
    "mlp_morpheus_combo.frag": "5b7966176ba012f865a8bd45bc2b493173e4a994316323f5494eee527d44e752",
}
ATTACHMENTS = ("features0.rgba32f", "features1.rgba32f", "direction.rgba32f", "indices.r32u")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_layout(ir):
    for i, name in enumerate(("inputFeature_0", "inputFeature_1", "rayDirectionIn", "weightsIndex", "weights_arr")):
        for field in (f"Binding {i}", "DescriptorSet 0", *([f"InputAttachmentIndex {i}"] if i < 4 else [])):
            if not re.search(rf"OpDecorate %{name} {field}$", ir, re.M):
                raise ValueError(f"Unexpected descriptor {name} {field}")
    for required in ("UniformBufferArrayNonUniformIndexing", "RuntimeDescriptorArray",
                     "OpTypeRuntimeArray %mlp_weights", "ArrayStride 16",
                     "OpTypeImage %float SubpassData", "OpTypeImage %uint SubpassData"):
        if required not in ir:
            raise ValueError(f"Missing SPIR-V layout component {required}")


def compare(actual, oracle, width, height):
    if len(actual) != len(oracle) or len(actual) != width * height * 16:
        raise ValueError("Incomplete image")
    differences = []
    discarded = exact_pixels = 0
    for index, (pixel, expected) in enumerate(zip(struct.iter_unpack("<4f", actual), struct.iter_unpack("<4f", oracle))):
        if not all(map(math.isfinite, pixel + expected)) or pixel[3] != expected[3]:
            raise ValueError(f"Invalid values or alpha at pixel {index}")
        if expected[3] == -3:
            if pixel != (-3, -3, -3, -3) or pixel != expected:
                raise ValueError(f"Discarded pixel changed at {index}")
            discarded += 1
        elif expected[3] == 1:
            differences.extend(abs(a - b) for a, b in zip(pixel[:3], expected[:3]))
        else:
            raise ValueError(f"Unexpected oracle alpha at {index}")
        exact_pixels += pixel == expected
    if not 0 < discarded < width * height:
        raise ValueError("Expected a mixture of drawn and discarded pixels")
    differences.sort()
    if differences[-1] > 1e-4:
        raise ValueError(f"RGB error exceeds the agreed 1e-4 tolerance: {differences[-1]}")
    return dict(pixels=width * height, exact_alpha=width * height, exact_clear_rgba=discarded,
                exact_pixels=exact_pixels, live_rgb_p99_abs=differences[math.ceil(.99 * len(differences)) - 1],
                max_abs=differences[-1], rgba32f_sha256=sha(actual), oracle_sha256=sha(oracle))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("worker", "sources", "inputs", "out"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--model", choices=("mlp_combo", "mlp_morpheus_combo"), required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--glslang", default="glslang")
    parser.add_argument("--val", default="spirv-val")
    parser.add_argument("--dis", default="spirv-dis")
    args = parser.parse_args()
    manifest = json.loads((args.inputs / "manifest.json").read_bytes())
    w, h = manifest["width"], manifest["height"]
    if (w, h) not in ((16, 16), (320, 180)) or manifest["clear"] != [-3] * 4:
        raise ValueError("Unsupported image profile")
    oracle_name = f"{args.model}.cpu.rgba32f"
    names = [*ATTACHMENTS, "weights.bin", oracle_name]
    inputs = {name: sha((args.inputs / name).read_bytes()) for name in names}
    if any(inputs[name] != manifest["sha256"][name] for name in names):
        raise ValueError("Source file differs from the shared input manifest")
    args.out.mkdir(parents=True, exist_ok=False)
    modules = []
    for name in ("quad.vert", args.model + ".frag"):
        src = args.sources / name
        if sha(src.read_bytes().replace(b"\r\n", b"\n")) != SOURCE_HASHES[name]:
            raise ValueError(f"Unexpected Khronos source {name}")
        module = args.out / (name + ".spv")
        subprocess.run([args.glslang, "-V", "--target-env", "vulkan1.2", src, "-o", module], check=True, timeout=30)
        subprocess.run([args.val, "--target-env", "vulkan1.2", module], check=True, timeout=30)
        modules.append(module)
    dis = subprocess.check_output([args.dis, modules[1]], text=True, timeout=30)
    validate_layout(dis)
    image = args.out / "frame.rgba32f"
    result = subprocess.run([args.worker.resolve(), *modules, args.device, "source-nerf", args.inputs,
                             image, f"{w}x{h}"], check=True, capture_output=True, text=True, timeout=45)
    gpu = json.loads(result.stdout)
    metrics = compare(image.read_bytes(), (args.inputs / oracle_name).read_bytes(), w, h)
    receipt = dict(model=args.model, width=w, height=h, source_revision="979aefaa5f2f4bd30efe035ca5a39444cc24ab9f",
                   input_hashes=inputs, worker_sha256=sha(args.worker.read_bytes()),
                   module_sha256=[sha(m.read_bytes()) for m in modules], comparison=metrics, gpu=gpu,
                   median_group_mean_ms=statistics.median(gpu["gpu_ms_per_draw"]))
    (args.out / "result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
