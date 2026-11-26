# SPDX-License-Identifier: MIT
"""Replay independently compiled MiniEngine shaders with the published Present root signature."""

import argparse
import json
import math
import os
import re
import struct
from hashlib import sha256
from pathlib import Path

import numpy as np
from PIL import Image
from prepare_miniengine import STAGES
from render_raylib import compare, guarded_draw, save_preview, summarize, trial_order

KINDS = ("bicubic", "bicubic", "sharpen", "present", "bilinear")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def srgb(linear):
    return np.where(
        linear < 0.0031308,
        12.92 * linear,
        1.055 * np.power(np.maximum(0, linear), 1 / 2.4) - 0.055,
    )


def parameters(kind, tw, th):
    if kind == "bicubic":
        return struct.pack("<IIfIII", tw, th, -0.5, 0, 0, 0)
    if kind == "sharpen":
        x, y = math.cos(45 / 180 * 3.14159), math.sin(45 / 180 * 3.14159)
        return struct.pack("<6f", x / tw, y / th, y / tw, -x / th, 0.1, 1.4)
    return bytes(24)


def source_image(raw_path, target_w, target_h, receipt):
    raw = raw_path.read_bytes()
    if sha256(raw).hexdigest() != receipt["gl_image"]["sha256"]:
        raise ValueError("Input scene readback differs from its receipt")
    source = np.frombuffer(raw, dtype="<f4").reshape(
        receipt["height"], receipt["width"], 4
    )
    if not np.isfinite(source).all():
        raise ValueError("Scene contains non-finite colors")
    rgb = source[:, :, :3]
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    result = np.ones((target_h, target_w, 4), dtype="<f4")
    for i in range(3):
        image = Image.fromarray(linear[:, :, i])
        result[:, :, i] = np.asarray(
            image.resize((target_w, target_h), Image.Resampling.BOX)
        )
    return result


def check_bindings(case, entry):
    (pipeline,) = (case / "pipeline").glob("*.pipe")
    src = pipeline.read_text(encoding="utf-8")
    if "userDataNode[0].type = DescriptorTableVaPtr" not in src:
        raise ValueError("Unexpected PAL descriptor root")
    pal = (case / "pal.txt").read_text(encoding="utf-8")
    if not re.search(r"\.user_data_reg_map:\s+- 268435456\s+- 0\s+- 4294967295", pal):
        raise ValueError("Cannot bind PAL descriptor table to SGPR1")
    nodes = {}
    for idx, key, value in re.findall(
        r"userDataNode\[0\]\.next\[(\d+)\]\.(\w+) = (\w+)", src
    ):
        nodes.setdefault(idx, {})[key] = value
    active = {int(n["binding"]): n for n in nodes.values()}
    if set(active) != set(entry["bindings"].values()):
        raise ValueError("Resource counts differ between SPIR-V and PAL")
    ranges = set()
    for binding, n in active.items():
        start = int(n["offsetInDwords"])
        size = int(n["sizeInDwords"])
        if (
            int(n["set"], 0) != 0
            or start < 0
            or start + size > 52
            or ranges.intersection(range(start, start + size))
            or (n["type"], size)
            != {
                0: ("DescriptorResource", 8),
                16: ("DescriptorBuffer", 4),
                32: ("DescriptorSampler", 4),
            }[binding]
        ):
            raise ValueError("Invalid published display interface")
        ranges.update(range(start, start + size))
    if int(active[0]["offsetInDwords"]) != 0:
        raise ValueError("Cannot use test's known texture offset")
    return {k: int(n["offsetInDwords"]) for k, n in active.items()}


def cpu_reference(input_tex, width, height, kind, gamma):
    """RGB oracle; hardware bilinear precision, binned copies and math can differ by a few ULPs."""
    th, tw, _ = input_tex.shape
    v, u = np.meshgrid(
        (np.arange(height, dtype="f4") + 0.5) / height,
        (np.arange(width, dtype="f4") + 0.5) / width,
        indexing="ij",
    )
    tex = input_tex[:, :, :3]

    def load(x, y):
        return tex[np.clip(y, 0, th - 1), np.clip(x, 0, tw - 1)]

    def bilinear(u, v):
        xt, yt = u * tw - 0.5, v * th - 0.5
        ix, iy = np.floor(xt).astype(int), np.floor(yt).astype(int)
        dx, dy = (xt - ix)[:, :, None], (yt - iy)[:, :, None]
        return (1 - dy) * ((1 - dx) * load(ix, iy) + dx * load(ix + 1, iy)) + dy * (
            (1 - dx) * load(ix, iy + 1) + dx * load(ix + 1, iy + 1)
        )

    if kind == "present":
        if (tw, th) != (width, height):
            raise ValueError("PresentSDR requires a 1:1 texture")
        rgb = srgb(tex)
    elif kind == "bilinear":
        rgb = srgb(bilinear(u, v))
    elif kind == "bicubic":
        tex = srgb(tex) if gamma else tex
        xt, yt = u * tw + 0.5, v * th + 0.5
        ix, iy = np.floor(xt).astype(int), np.floor(yt).astype(int)

        def weights(t):
            a = -0.5
            w1 = lambda x: x * x * ((a + 2) * x - (a + 3)) + 1
            w2 = lambda x: a * (x * (x * (x - 5) + 8) - 4)
            return (w2(1 + t), w1(t), w1(1 - t), w2(2 - t))

        wx, wy = weights(xt - ix), weights(yt - iy)
        rgb = sum(
            (wx[x] * wy[y])[:, :, None] * load(ix + x - 2, iy + y - 2)
            for y in range(4)
            for x in range(4)
        )
        if not gamma:
            rgb = srgb(rgb)
    else:
        x0, y0, x1, y1, wa, wb = struct.unpack("<6f", parameters(kind, tw, th))

        def sample(x, y):
            c = bilinear(x, y)
            return srgb(c) if gamma else c

        rgb = wb * sample(u, v) - wa * (
            sample(u + x0, v + y0)
            + sample(u - x0, v - y0)
            + sample(u + x1, v + y1)
            + sample(u - x1, v - y1)
        )
        if not gamma:
            rgb = srgb(rgb)
    image = np.ones((height, width, 4), dtype="<f4")
    image[:, :, :3] = rgb
    return image.tobytes()


def rgb_only(raw):
    p = np.frombuffer(raw, dtype="<f4").reshape(-1, 4).copy()
    p[:, 3] = 1
    return p.tobytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("prepared", "masks", "scene-image", "guard", "tests", "dxc", "out"):
        parser.add_argument("--" + arg, type=lambda s: Path(s).resolve(), required=True)
    parser.add_argument("--filter", choices=STAGES, required=True)
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=450)
    parser.add_argument("--draws", type=int, default=16)
    parser.add_argument(
        "--small-job",
        action="store_true",
        help="Use the guard revision with a 512 MiB hard limit",
    )
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--modes", nargs="+", default=("native", "whole", "local"))
    args = parser.parse_args()
    if not (
        4 <= args.width <= 1280
        and 4 <= args.height <= 720
        and 1 <= args.draws <= 32
        and 1 <= args.trials <= 15
    ):
        parser.error("Invalid draw or repetition size")
    if (
        not {"native", "whole"} <= set(args.modes)
        or len(set(args.modes)) != len(args.modes)
        or any(not re.fullmatch("[a-z-]+", m) for m in args.modes)
    ):
        parser.error("Choose whole, native and candidate modes")
    i = STAGES.index(args.filter)
    kind = KINDS[i]
    case = args.prepared / f"{i:03d}"
    entry = json.loads(
        (args.prepared / "miniengine-display.json").read_text(encoding="utf-8")
    )["observations"][i]
    cen = json.loads((args.masks / "census.json").read_text(encoding="utf-8"))
    matches = [
        row
        for row in cen["rows"]
        if row["group"] == entry["group"]
        and row["source"] == entry["source"]
        and row.get("rdna", {}).get("sha256") == entry["rdna"]["sha256"]
    ]
    if len(matches) != 1:
        raise ValueError(
            "Expected one corrected PAL shader with the same source and digest"
        )
    row = matches[0]
    required_modes = set(args.modes) - {"native"}
    if any(
        "dxil_sha256" not in row["variants"].get(mode, {}) for mode in required_modes
    ):
        raise ValueError("Missing a validated shader for a requested mode")
    if entry["native_dxil_sha256"] != digest(case / "native.dxil") or entry[
        "rootsig_sha256"
    ] != digest(case / "present.rootsig"):
        raise ValueError("Native oracle digest mismatch")
    offsets = check_bindings(case, entry)
    args.out.mkdir(parents=True, exist_ok=False)
    tw, th = (
        (args.width, args.height)
        if kind == "present"
        else (args.width // 2, args.height // 2)
    )
    picture = json.loads(
        (args.scene_image.parent / "scene.json").read_text(encoding="utf-8")
    )
    texture = source_image(args.scene_image, tw, th, picture)
    input_file = args.out / "input-linear.rgba32f"
    input_file.write_bytes(texture.tobytes())
    constants = args.out / "constants.bin"
    constants.write_bytes(parameters(kind, tw, th))
    cpu = cpu_reference(texture, args.width, args.height, kind, "Gamma" in args.filter)
    (args.out / "cpu.rgba32f").write_bytes(cpu)
    output = {
        "stage": entry["source"],
        "translator_source_tree": cen["source_tree"],
        "translator_tools": cen["tool_hashes"],
        "guard_job_mib": 512 if args.small_job else 2048,
        "source_sha256": entry["source_sha256"],
        "rdna_sha256": entry["rdna"]["sha256"],
        "width": args.width,
        "height": args.height,
        "texture_width": tw,
        "texture_height": th,
        "draws": args.draws,
        "input_scene_sha256": picture["gl_image"]["sha256"],
        "input_texture_sha256": digest(input_file),
        "rootsig_sha256": entry["rootsig_sha256"],
        "cpu": summarize(cpu),
        "trials": [],
    }
    for t in range(args.trials):
        order = trial_order(args.modes, t)
        variants = {}
        raw = {}
        for m in order:
            run = args.out / f"{t:02d}-{m}"
            run.mkdir()
            shader = (
                (case / "native.dxil")
                if m == "native"
                else (args.masks / row["group"] / f"{row['id']:03d}" / f"{m}.dxil")
            )
            if m != "native" and digest(shader) != row["variants"][m]["dxil_sha256"]:
                raise ValueError("Wrong translated DXIL")
            env = {
                k: v for k, v in os.environ.items() if not k.startswith(("XCL_", "PB_"))
            }
            image = run / "draw.rgba32f"
            log = run / "guard.log"
            env.update(
                XCL_DXC_DIR=str(args.dxc.parent),
                XCL_READ_GUARD_TEST_ROOT_WINDOWS="1",
                XCL_READ_GUARD_TEST_GPU_DRAWS=str(args.draws),
                XCL_READ_GUARD_TEST_PSO_BLOB="1",
                PB_SCENE_PS=str(shader),
                PB_SCENE_IMAGE=str(image),
                PB_SCENE_SIZE=str(args.width),
                PB_SCENE_HEIGHT=str(args.height),
                PB_INPUT_RGBA32F=str(input_file),
                PB_TEXTURE_WIDTH=str(tw),
                PB_TEXTURE_HEIGHT=str(th),
                PB_PRESENT_CONSTANTS=str(constants),
                PB_MINI_KIND=kind,
                PB_SAMPLER_OFFSET=str(offsets.get(32, -1)),
                PB_CBV_OFFSET=str(offsets.get(16, -1)),
            )
            if m == "native":
                env["PB_MINI_NATIVE_ROOT"] = str(case / "present.rootsig")
            test_command = [
                args.guard,
                args.tests,
                log,
                "gpu::dxil::aperture_tests::open_miniengine_display_draw",
            ]
            if args.small_job:
                test_command.append("--512-mib")
            proc, attempts = guarded_draw(test_command, log, env)
            (run / "guard-process.txt").write_text("".join(attempts), encoding="utf-8")
            if proc.returncode or not log.exists():
                raise ValueError(f"Render failed for {m}: see {run}")
            text = log.read_text(encoding="utf-8")
            if "1 passed; 0 failed" not in text or "SKIPPED" in text:
                raise ValueError(f"Incomplete render in {run}")
            data = image.read_bytes()
            raw[m] = data
            if len(data) != args.width * args.height * 16:
                raise ValueError("Incomplete readback")
            if t == 0:
                save_preview(args.out / f"{m}.png", data, args.width, args.height)
            stats = {}
            for name in (
                "gpu_ms_per_draw",
                "native_create_ms",
                "pso_cache_blob_bytes",
                "ticks",
                "frequency_hz",
            ):
                v = re.search(rf"\b{name}=([0-9.]+)", text).group(1)
                stats[name] = float(v) if "." in v else int(v)
            variants[m] = {
                "dxil_sha256": digest(shader),
                "image": summarize(data),
                "vs_cpu_rgb": compare(rgb_only(data), cpu),
                "stats": stats,
            }
        item = {
            "order": order,
            "variants": variants,
            "vs_native_rgb": {
                m: compare(rgb_only(raw["native"]), rgb_only(v))
                for m, v in raw.items()
                if m != "native"
            },
            "vs_whole_rgba": {
                m: compare(raw["whole"], v)
                for m, v in raw.items()
                if m not in ("whole", "native")
            },
        }
        output["trials"].append(item)
        (args.out / "display.json").write_text(
            json.dumps(output, indent=2) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            [
                {m: v["stats"]["gpu_ms_per_draw"] for m, v in trial["variants"].items()}
                for trial in output["trials"]
            ]
        )
    )


if __name__ == "__main__":
    main()
