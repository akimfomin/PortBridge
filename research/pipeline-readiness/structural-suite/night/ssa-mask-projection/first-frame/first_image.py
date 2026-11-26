# SPDX-License-Identifier: MIT
"""Time one streamed XCL pixel program through a checked, single-draw D3D12 frame."""
import argparse
import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import time


MODES = ("whole", "project")
TEST = "gpu::dxil::aperture_tests::open_procedural_pixel_draw"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache_files(root):
    return {
        path.relative_to(root).as_posix(): [path.stat().st_size, path.stat().st_mtime_ns]
        for path in root.rglob("*.bin")
    }


def fresh_environment(dxc_dir):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("XCL_", "PB_SCENE_"))}
    env["XCL_DXC_DIR"] = str(dxc_dir)
    return env


def run_process(command, env, log):
    start = time.perf_counter_ns()
    child = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=45)
    wall_ms = (time.perf_counter_ns() - start) / 1e6
    log.write_bytes(child.stdout)
    txt = child.stdout.decode(errors="replace")
    if child.returncode:
        raise RuntimeError(f"{log.name} exit {child.returncode}: {txt[-700:]}")
    return txt, wall_ms


def quantity(text, name):
    match = re.search(r"\b" + re.escape(name) + r"=([\d.]+)", text)
    if not match:
        raise ValueError(f"missing {name}")
    return float(match[1])


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class Experiment:
    def __init__(self, args):
        self.args = args
        self.scene = json.loads(args.scene.read_bytes())
        self.sgprs = args.scene.parent / "sgprs.bin"
        if self.scene["scene"] != "raymarching" or digest(self.sgprs) != self.scene["sgprs_sha256"]:
            raise ValueError("expected the pinned raymarching scene and matching PAL scalar values")
        payload = args.census.read_bytes()
        census = json.loads(gzip.decompress(payload) if payload[:2] == b"\x1f\x8b" else payload)
        case, = [row for row in census["rows"] if row["group"] == "raylib-procedural" and row["id"] == 0]
        if self.scene["source_sha256"] != case["source_sha256"] or self.scene["rdna_sha256"] != case["rdna"]["sha256"]:
            raise ValueError("scene shader or guest machine code differs from the accepted corpus case")
        self.dxil_sha = {m: case["variants"][m]["dxil_sha256"] for m in MODES}
        if len(set(self.dxil_sha.values())) != 2:
            raise ValueError("expected distinct whole and projected outputs")
        self.width, self.height = self.scene["width"], self.scene["height"]
        if (self.width, self.height) != (800, 450):
            raise ValueError("expected the canonical 800 by 450 scene")
        if "reference_rgba32f_sha256" in self.scene:
            self.rgba_sha = self.scene["reference_rgba32f_sha256"]
        else:
            self.rgba_sha = self.scene["pairs"][0]["variants"]["whole"]["image"]["sha256"]
        expected = args.scene.parent / "00-whole" / "draw.rgba32f"
        if expected.exists() and (digest(expected) != self.rgba_sha or
                                  expected.stat().st_size != self.width * self.height * 16):
            raise ValueError("baseline readback disagrees with the source receipt")
        if digest(args.fixture) != args.fixture_sha256:
            raise ValueError("unexpected synthetic shader container")
        args.out.mkdir(parents=True, exist_ok=False)
        tools = {"translator": args.runtime, "dxc": args.dxc_dir / "dxc.exe"}
        if not args.cpu_only:
            tools.update(renderer=args.renderer, guard=args.guard)
        self.report = {
            "xcl_revision_reported": args.xcl_revision, "synthetic_fixture_sha256": args.fixture_sha256,
            "source_sha256": case["source_sha256"], "guest_isa_sha256": case["rdna"]["sha256"],
            "scene_sha256": digest(args.scene), "sgpr_sha256": digest(self.sgprs),
            "reference_rgba32f_sha256": self.rgba_sha,
            "expected_dxil_sha256": self.dxil_sha, "controls": self.scene["controls"],
            "tool_sha256": {k: digest(p) for k, p in tools.items()}, "cpu_only": args.cpu_only,
            "shader_cache": "isolated XCL translated cache per trial, fresh process per arm",
            "native_cache": "renderer requires device-local D3D12 implicit driver and D3D cache disable",
            "render_count": 0 if args.cpu_only else 1, "collect_pso_blob": False, "rows": [],
        }
        self.record()

    def record(self):
        write_json(self.args.out / "trials.json", self.report)

    def run_one(self, index, mode, warm, cache, draw):
        args = self.args
        phase = "warm" if warm else "cold"
        tag = f"{index:02}-{phase}-{mode}"
        folder = args.out / tag
        folder.mkdir()
        dxil = folder / "runtime.dxil"
        rgba = folder / "frame.rgba32f"
        env = fresh_environment(args.dxc_dir)
        env.update(XCL_DIRECT_DXIL="all", XCL_DIRECT_PIXEL_MASK_PROJECTION=str(int(mode == "project")),
                   XCL_DXIL_CACHE=str(cache))
        previous = cache_files(cache)
        row = {"id": tag, "mode": mode, "cache": phase, "draw_requested": draw, "qualified": False}
        self.report["rows"].append(row)
        start = time.perf_counter_ns()
        api_output, api_wall = run_process([args.runtime, args.fixture, dxil], env, folder / "runtime.log")
        actual_dxil = digest(dxil)
        if actual_dxil != self.dxil_sha[mode]:
            raise ValueError("normal runtime and offline DXIL hashes differ")
        row.update(dxil_sha256=actual_dxil, runtime_process_wall_ms=api_wall,
                   runtime_api_ms=quantity(api_output, "runtime_api_ms"),
                   translated_cache_hits=int(quantity(api_output, "cache_hits")))
        if draw:
            render_env = fresh_environment(args.dxc_dir)
            render_env.update(PB_SCENE_PS=str(dxil), PB_SCENE_IMAGE=str(rgba), PB_SCENE_SGPRS=str(self.sgprs),
                              PB_SCENE_SIZE=str(self.width), PB_SCENE_HEIGHT=str(self.height),
                              XCL_READ_GUARD_TEST_ROOT_WINDOWS="1", XCL_DXIL_CACHE=str(folder / "renderer-cache"))
            renderer_log = folder / "renderer.log"
            guard_out, external_ms = run_process([args.guard, args.renderer, renderer_log, TEST, "--512-mib"],
                                                 render_env, folder / "guard.log")
            # After the guard exits a valid image is fully serialized. Check every float byte.
            if rgba.stat().st_size != self.width * self.height * 16 or digest(rgba) != self.rgba_sha:
                raise ValueError("rendered pixels differ from the canonical draw")
            verified_ms = (time.perf_counter_ns() - start) / 1e6
            output = renderer_log.read_text(encoding="utf-8", errors="replace")
            if ("1 passed; 0 failed" not in output or "SKIPPED" in output or
                    "pso_cache_blob" in output or "gpu_ms_per_draw" in output):
                raise ValueError("renderer must execute one draw without blob extraction or repeated timings")
            size = re.search(r"scene adapter=(.*?) size=(\d+) full_target_pixels=(\d+)", output)
            if not size or int(size[2]) != self.width or int(size[3]) != self.width * self.height:
                raise ValueError("unexpected adapter or target dimensions")
            row.update(renderer_adapter=size[1], rgba32f_sha256=self.rgba_sha,
                       guest_input_to_verified_image_wall_ms=verified_ms, render_guard_wall_ms=external_ms,
                       native_create_ms=quantity(output, "native_create_ms"),
                       setup_submit_readback_ms=quantity(output, "scene_native_setup_submit_readback_ms"),
                       peak_render_process_bytes=int(quantity(guard_out, "peak_process_bytes")))
            if row["native_create_ms"] > row["setup_submit_readback_ms"] + 0.1:
                raise ValueError("native PSO timer exceeds its enclosing render interval")
        after = cache_files(cache)
        added = set(after) - set(previous)
        if warm:
            if after != previous or row["translated_cache_hits"] < 1:
                raise ValueError("warm normal route did not use the previous entry")
        elif row["translated_cache_hits"] or len(added) != 1 or any(after.get(k) != v for k, v in previous.items()):
            raise ValueError("cold normal route should create precisely one new entry")
        row.update(qualified=True, new_cache_entries=sorted(added))
        write_json(folder / "receipt.json", row)
        self.record()
        elapsed = f", verified frame {row['guest_input_to_verified_image_wall_ms']:.3f} ms" if draw else ""
        print(f"{tag}: API {row['runtime_api_ms']:.3f} ms{elapsed}", flush=True)

    def run(self):
        try:
            for index in range(self.args.pairs):
                order = MODES if index % 2 == int(self.args.first_mode == "project") else tuple(reversed(MODES))
                cache = self.args.out / f"cache-{index:02}"
                cache.mkdir()
                for warm in ([False] if self.args.cache == "cold" else [False, True]):
                    for mode in (tuple(reversed(order)) if warm else order):
                        draw = not self.args.cpu_only and (warm or self.args.cache != "warm")
                        self.run_one(index, mode, warm, cache, draw)
        except Exception as error:
            self.report["error"] = str(error)
            self.record()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("runtime", "fixture", "census", "scene", "dxc-dir", "out"):
        parser.add_argument("--" + key, type=lambda p: Path(p).resolve(), required=True)
    for key in ("guard", "renderer"):
        parser.add_argument("--" + key, type=lambda p: Path(p).resolve())
    parser.add_argument("--fixture-sha256", required=True)
    parser.add_argument("--xcl-revision", required=True)
    parser.add_argument("--first-mode", choices=MODES, default="whole")
    parser.add_argument("--pairs", type=int, choices=range(1, 9), default=1)
    parser.add_argument("--cache", choices=["cold", "warm", "both"], default="both")
    parser.add_argument("--cpu-only", action="store_true")
    args = parser.parse_args()
    if not args.cpu_only and (not args.renderer or not args.guard):
        parser.error("a hardware run requires both --renderer and --guard")
    Experiment(args).run()


if __name__ == "__main__":
    main()
