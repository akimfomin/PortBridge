# SPDX-License-Identifier: MIT
"""Bind the original raylib controls and compare XCL pixels against unmodified OpenGL GLSL."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time

from prepare_raylib import CASES, PIN


def controls(name, width, height, time, other_view):
    if name == "raymarching":
        return {"viewEye": (3.0, 1.8, 3.5) if other_view else (2.5, 2.5, 3.0),
                "viewCenter": (0.0, 0.0, 0.7), "runTime": time, "resolution": (float(width), float(height))}
    if name == "julia_set":
        return {"c": (-0.348827, 0.607167), "offset": (0.0, 0.0), "zoom": 0.75}
    if name == "mandelbrot_set":
        return {"offset": (-0.5, 0.0), "zoom": 0.6, "maxIterations": 333}
    raise ValueError(name)


def register_image(name, values, pal):
    push = bytearray(64)
    for field, ty, offset in CASES[name]:
        val = values[field]
        if not isinstance(val, tuple):
            val = (val,)
        struct.pack_into("<" + ("I" if ty == "int" else "f") * len(val), push, offset, *val)
    match = re.search(r"(?m)^\s*\.user_data_reg_map:\n((?:\s+- \d+\n)+)", pal)
    if not match:
        raise ValueError("PAL .user_data_reg_map is missing")
    mapping = [int(value) for value in re.findall(r"- (\d+)", match.group(1))]
    if (len(mapping) != 32 or mapping[0] != 0x10000000 or ".scratch_memory_size: 0" not in pal
            or not re.search(r"\.spill_threshold:\s+65535\b", pal)):
        raise ValueError("Unexpected PAL binding or spilling. Validate its ABI before rendering")
    sgprs = [0] * 128
    for reg, code in enumerate(mapping[1:], 1):
        if code == 0xffffffff:
            continue
        if code >= len(push) // 4:
            raise ValueError(f"Unsupported additional PAL binding: {code:#x}")
        sgprs[reg] = struct.unpack_from("<I", push, code * 4)[0]
    sgprs[112] = 4  # pinned XCL IO_UMA_BASE_HI
    return struct.pack("<128I", *sgprs)


def gl_reference(path, width, height, draws, controls):
    import moderngl
    import numpy as np
    vs = """#version 330
    out vec2 fragTexCoord;
    out vec4 fragColor;
    void main() {
        const vec2 positions[3] = vec2[3](vec2(-1,-1),vec2(-1,3),vec2(3,-1));
        vec2 p = positions[gl_VertexID];
        gl_Position = vec4(p, 0, 1);
        fragTexCoord = p * vec2(0.5, -0.5) + 0.5;
        fragColor = vec4(1);
    }"""
    ctx = moderngl.create_standalone_context(require=330)
    try:
        started = time.perf_counter()
        program = ctx.program(vertex_shader=vs, fragment_shader=path.read_text(encoding="utf-8"))
        for k, v in controls.items():
            program[k].value = v
        texture = ctx.texture((width, height), 4, dtype="f4")
        fb = ctx.framebuffer(color_attachments=[texture])
        fb.use()
        fb.clear(-3.0, -3.0, -3.0, -3.0)
        vao = ctx.vertex_array(program, [])
        vao.render(vertices=3)
        buf = fb.read(components=4, dtype="f4", alignment=1)
        first_image_ms = 1000 * (time.perf_counter() - started)
        timings = []
        for _ in range(5 if draws else 0):
            with ctx.query(time=True) as query:
                for _ in range(draws):
                    vao.render(vertices=3)
            elapsed = query.elapsed
            if not 0 < elapsed < 0xFFFFFFFF:
                raise ValueError(f"Invalid GL_TIME_ELAPSED: {elapsed}")
            timings.append(elapsed / 1e6 / draws)
        pixels = np.frombuffer(buf, dtype="<f4").reshape(height, width, 4)[::-1].copy()
        if ((pixels == -3.0).all(axis=2)).any():
            raise ValueError("Incomplete OpenGL coverage")
        info = {k: ctx.info[k] for k in ("GL_VENDOR", "GL_RENDERER", "GL_VERSION")}
        info.update(first_draw_setup_link_readback_ms=first_image_ms, gpu_ms_per_draw=timings)
        return pixels.tobytes(), info
    finally:
        ctx.release()


def summarize(raw):
    import numpy as np
    pixels = np.frombuffer(raw, dtype="<f4").reshape(-1, 4)
    valid = np.isfinite(pixels).all(axis=1)
    return {"sha256": sha256(raw).hexdigest(), "pixels": len(pixels),
            "nonfinite_pixels": int((~valid).sum()), "unique_finite_colors": len(np.unique(pixels[valid], axis=0)),
            "rgb_mean": pixels[valid, :3].mean(axis=0).tolist() if valid.any() else None}


def save_preview(path, raw, width, height):
    import numpy as np
    from PIL import Image
    rgb = np.frombuffer(raw, dtype="<f4").reshape(height, width, 4)[:, :, :3]
    # The shader applies its own display gamma. Quantize only this viewing copy.
    rgb8 = np.rint(np.clip(np.nan_to_num(rgb), 0, 1) * 255).astype("uint8")
    Image.fromarray(rgb8).save(path)


def compare(raw_a, raw_b):
    import numpy as np
    a, b = [np.frombuffer(raw, dtype="<f4").reshape(-1, 4) for raw in (raw_a, raw_b)]
    if a.shape != b.shape:
        raise ValueError("Image extents differ")
    finite = np.isfinite(a).all(axis=1) & np.isfinite(b).all(axis=1)
    diff = a[finite].astype("f8") - b[finite].astype("f8")
    delta = np.abs(diff).max(axis=1)
    return {"bit_equal_pixels": int((a.view("<u4") == b.view("<u4")).all(axis=1).sum()),
            "both_finite_pixels": int(finite.sum()),
            "p50_max_channel_abs": float(np.median(delta)) if len(delta) else None,
            "p99_max_channel_abs": float(np.quantile(delta, 0.99)) if len(delta) else None,
            "max_channel_abs": float(delta.max()) if len(delta) else None,
            "mean_abs_rgb": float(np.abs(diff[:, :3]).mean()) if len(delta) else None,
            "rms_rgb": float(np.sqrt(np.square(diff[:, :3]).mean())) if len(delta) else None,
            "pixels_over_one_8bit_code": int((delta > 1/255).sum()),
            "pixels_over_two_8bit_codes": int((delta > 2/255).sum())}


def guarded_draw(command, log, env):
    # A busy workstation can temporarily decline admission. Retry only if the
    # original guard confirms that no child began. Never rerun a failed draw.
    attempts = []
    deadline = time.monotonic() + 180
    while True:
        child = subprocess.run(command, capture_output=True, text=True, env=env, timeout=150)
        attempts.append(child.stdout + child.stderr)
        if (log.exists() or child.returncode != 2 or "Insufficient system commit or RAM headroom" not in child.stderr
                or time.monotonic() >= deadline):
            return child, attempts
        time.sleep(3)


def trial_order(modes, trial):
    # Balanced Latin square. Across four trials each of four pipeline modes
    # occupies every ordinal slot once, with balanced immediate predecessors.
    count = len(modes)
    indices = [0]
    for position in range(1, count):
        indices.append((position + 1) // 2 if position % 2 else count - position // 2)
    if count % 2 and (trial // count) % 2:
        indices.reverse()
    return [modes[(index + trial) % count] for index in indices]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for option in ("repo", "prepared", "masks", "guard", "tests", "dxc", "out"):
        p.add_argument("--" + option, type=lambda s: Path(s).resolve(), required=True)
    p.add_argument("--scene", choices=CASES, required=True)
    p.add_argument("--size", type=int, required=True)
    p.add_argument("--height", type=int, help="Defaults to --size for the square probe")
    p.add_argument("--draws", type=int, default=3)
    p.add_argument("--small-job", action="store_true", help="Use the guard revision with a 512 MiB hard limit")
    p.add_argument("--pairs", type=int, default=1)
    p.add_argument("--time", type=float, default=1.0)
    p.add_argument("--other-view", action="store_true")
    p.add_argument("--modes", nargs="+", default=["whole", "local"])
    args = p.parse_args()
    height = args.height if args.height is not None else args.size
    if not 4 <= args.size <= 1280 or not 4 <= height <= 720 or not 0 <= args.draws <= 32 or not 1 <= args.pairs <= 15:
        p.error("Invalid scene size or repetition count")
    if (len(args.modes) < 2 or len(args.modes) != len(set(args.modes)) or args.modes[0] != "whole"
            or any(not re.fullmatch(r"[a-z-]+", x) for x in args.modes)):
        p.error("Use whole followed by candidate mode(s)")
    args.out.mkdir(parents=True, exist_ok=False)
    index = list(CASES).index(args.scene)
    case = args.prepared / f"{index:03d}"
    manifest = json.loads((args.prepared / "raylib-pixels.json").read_text(encoding="utf-8"))
    entry = manifest["observations"][index]
    if manifest["source"]["commit"] != PIN:
        raise ValueError("Unexpected source pin")
    ps_original = args.repo / entry["source"]
    if sha256(ps_original.read_bytes()).hexdigest() != entry["source_sha256"]:
        raise ValueError("OpenGL source digest mismatch")
    params = controls(args.scene, args.size, height, args.time, args.other_view)
    sgpr_file = args.out / "sgprs.bin"
    sgpr_file.write_bytes(register_image(args.scene, params, (case / "pal.txt").read_text(encoding="utf-8")))
    # Exit the OpenGL process before any timed D3D12 trial. Releasing just the
    # context can leave driver modules and allocations live in the Python host.
    subprocess.run([sys.executable, __file__, "gl-worker", str(ps_original), str(args.size), str(height), str(args.draws),
                    json.dumps(params), str(args.out)], check=True, timeout=45)
    gl_raw = (args.out / "gl.rgba32f").read_bytes()
    save_preview(args.out / "gl.png", gl_raw, args.size, height)
    gl_info = json.loads((args.out / "gl-adapter.json").read_text(encoding="utf-8"))
    result = {"scene": args.scene, "width": args.size, "height": height, "controls": params, "gl": gl_info,
              "gl_image": summarize(gl_raw), "draws_per_interval": args.draws, "pairs": [],
              "request_cached_blob": bool(args.draws), "guard_job_mib": 512 if args.small_job else 2048,
              "source_sha256": entry["source_sha256"], "rdna_sha256": entry["rdna"]["sha256"],
              "sgprs_sha256": sha256(sgpr_file.read_bytes()).hexdigest()}
    (args.out / "scene.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    mask_manifest = json.loads((args.masks / "census.json").read_text(encoding="utf-8"))
    mask_entry, = [row for row in mask_manifest["rows"] if row["source"] == entry["source"]]
    for pair in range(args.pairs):
        variants = {}
        variant_bytes = {}
        for mode in trial_order(args.modes, pair):
            folder = args.out / f"{pair:02d}-{mode}"
            folder.mkdir()
            image = folder / "draw.rgba32f"
            log = folder / "guard.log"
            ps = args.masks / "raylib-procedural" / f"{index:03d}" / f"{mode}.dxil"
            if sha256(ps.read_bytes()).hexdigest() != mask_entry["variants"][mode]["dxil_sha256"]:
                raise ValueError("DXIL digest mismatch")
            env = {k: v for k, v in os.environ.items() if not k.startswith(("XCL_", "PB_SCENE_"))}
            env.update(XCL_DXC_DIR=str(args.dxc.parent), PB_SCENE_PS=str(ps),
                       PB_SCENE_IMAGE=str(image), PB_SCENE_SGPRS=str(sgpr_file), PB_SCENE_SIZE=str(args.size),
                       PB_SCENE_HEIGHT=str(height), XCL_READ_GUARD_TEST_ROOT_WINDOWS="1")
            if args.draws:
                env["XCL_READ_GUARD_TEST_GPU_DRAWS"] = str(args.draws)
                env["XCL_READ_GUARD_TEST_PSO_BLOB"] = "1"
            before = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            test_command = [args.guard, args.tests, log, "gpu::dxil::aperture_tests::open_procedural_pixel_draw"]
            if args.small_job:
                test_command.append("--512-mib")
            guarded, attempts = guarded_draw(test_command, log, env)
            after = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            (folder / "guard-process.txt").write_text("".join(attempts), encoding="utf-8")
            if not log.is_file():
                raise RuntimeError(f"Guard declined before startup: {guarded.stderr.strip() or guarded.stdout.strip()}")
            text = log.read_text(encoding="utf-8", errors="replace")
            if guarded.returncode or "1 passed; 0 failed" not in text or "SKIPPED" in text:
                raise RuntimeError(f"XCL draw failed for {mode}. Inspect {log}")
            data = image.read_bytes()
            if len(data) != args.size * height * 16:
                raise ValueError("Incorrect readback length")
            if pair == 0:
                save_preview(args.out / (mode + ".png"), data, args.size, height)
            variant_bytes[mode] = data
            stats = {}
            fields = ["native_create_ms", "scene_native_setup_submit_readback_ms"]
            if args.draws:
                fields.extend(["gpu_ms_per_draw", "ticks", "frequency_hz", "pso_cache_blob_bytes"])
            for field in fields:
                match = re.search(rf"\b{field}=([\d.]+)", text)
                if not match:
                    raise ValueError(f"No {field} in draw log")
                stats[field] = float(match.group(1)) if "." in match.group(1) else int(match.group(1))
            peak = re.search(r"\bpeak_process_bytes=(\d+)", guarded.stdout)
            if peak:
                stats["peak_process_bytes"] = int(peak.group(1))
            variants[mode] = {"dxil_sha256": mask_entry["variants"][mode]["dxil_sha256"],
                              "admission_start_utc": before, "readback_complete_utc": after,
                              "admission_attempts": len(attempts),
                              "stats": stats, "image": summarize(data), "vs_gl": compare(data, gl_raw)}
        result["pairs"].append({"order": list(variants), "variants": variants,
                                "vs_whole": {m: compare(variant_bytes["whole"], v)
                                             for m, v in variant_bytes.items() if m != "whole"}})
        (args.out / "scene.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if sys.argv[1:2] == ["gl-worker"]:
        path, width, height, draws, params, destination = sys.argv[2:]
        raw, info = gl_reference(Path(path), int(width), int(height), int(draws), json.loads(params))
        (Path(destination) / "gl.rgba32f").write_bytes(raw)
        (Path(destination) / "gl-adapter.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    else:
        main()
