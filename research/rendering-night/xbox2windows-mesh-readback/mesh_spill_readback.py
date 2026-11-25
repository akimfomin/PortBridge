"""Independent synthetic build and readback control for Xbox2Windows #2127."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile


SETUP = """
v_mbcnt_lo_u32_b32 v7, -1, 0
v_mbcnt_hi_u32_b32 v7, -1, v7
v_mov_b32_e32 v30, 0
s_mov_b32 s40, 1
s_mov_b32 s41, 0x100
s_mov_b64 exec, s[40:41]
s_mov_b64 s[40:41], exec
s_mov_b64 exec, 1
s_mov_b32 s47, 0
v_writelane_b32 v30, s40, 8
v_writelane_b32 v30, s41, 40
s_mov_b32 s40, 0
s_mov_b32 s41, 0
v_readlane_b32 s40, v30, 8
v_readlane_b32 s41, v30, 40
s_cmp_eq_u32 s40, 1
s_cbranch_scc0 1
s_mov_b64 exec, s[40:41]
v_cmpx_eq_u32_e32 40, v7
s_mov_b32 s46, -0.5
s_cbranch_execz 1
s_mov_b32 s46, 0.5
s_mov_b64 exec, s[22:23]
""".strip().splitlines()


def make_program(triangle, clear_lane):
    setup = list(SETUP)
    if clear_lane is not None:
        word = 40 if clear_lane == 8 else 41
        setup[setup.index(f"v_writelane_b32 v30, s{word}, {clear_lane}")] = f"v_writelane_b32 v30, s47, {clear_lane}"
    splice = triangle.index("s_mov_b64 s[22:23], exec") + 1
    return [
        "v_mov_b32_e32 v3, s46" if line == "v_mov_b32_e32 v3, s30" else line
        for line in [*triangle[:splice], *setup, *triangle[splice:]]
        if line != "v_add_f32_e32 v3, s31, v3"
    ]


def prepare_draws(dxc, output, cases, fixture, pixel_source):
    output.mkdir(parents=True, exist_ok=True)
    pixel_hlsl, pixel_dxil = output / "color.hlsl", output / "color.dxil"
    pixel_hlsl.write_text(pixel_source + "\n", encoding="ascii")
    subprocess.run([dxc, "-T", "ps_6_0", "-E", "main", "-Fo", pixel_dxil, pixel_hlsl], check=True, timeout=8)
    draws = []
    for label, source, inputs, positions, visible in cases:
        hlsl, dxil = output / f"{label}.hlsl", output / f"{label}-trace.dxil"
        hlsl.write_text(source, encoding="ascii")
        subprocess.run(
            [dxc, "-T", "ms_6_5", "-E", "main", "-DTRACE_EXPORTS", "-Fo", dxil, hlsl],
            check=True, timeout=8,
        )
        reference = output / f"{label}-trace-reference.bin"
        reference.write_bytes(fixture(inputs, positions, visible, True))
        draws.append((label, dxil, reference, 0))
    _, _, inputs, positions, _ = cases[0]
    stale = output / "stale-pixels-only-reference.bin"
    stale.write_bytes(fixture(inputs, positions, False, True))
    draws.append(("stale-pixels-only", draws[0][1], stale, 1024))
    return pixel_dxil, draws


def run_draws(renderer, backend, pixel, draws):
    for label, mesh, reference, expected_mismatches in draws:
        print(f"=== {label} ===", flush=True)
        result = subprocess.run(
            [renderer, backend, "--mesh-entry", mesh, pixel, reference],
            capture_output=True, text=True, errors="replace", timeout=8,
        )
        print(f"exit={result.returncode}\n{result.stdout}{result.stderr}", flush=True)
        if result.returncode == 77:
            return 77
        assert result.returncode == int(bool(expected_mismatches)), label
        assert f"pixels=1024 mismatches={expected_mismatches}" in result.stdout.splitlines(), label
        if expected_mismatches:
            assert "Draw reference mismatch" in result.stderr.splitlines(), label
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path, help="clean Xbox2Windows #2127 checkout")
    parser.add_argument("--binary", nargs=3, metavar=("LLVM_MC", "LLVM_OBJCOPY", "LLVM_LIB"))
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare", nargs=2, metavar=("DXC", "OUTPUT"), help="compile without drawing")
    modes.add_argument("--draw", nargs=3, metavar=("DXC", "OFFSCREEN_CHECK", "BACKEND"))
    args = parser.parse_args()
    sys.path.insert(0, str(args.repo.resolve() / "tests"))
    from mesh_entry_check import PIXEL, PROGRAM, TRIANGLE, binary, enumerate_pcs, evaluate_depth, fixture, lower, triangle_inputs
    from mesh_entry_aot import Wave

    # The two different words start at inactive lanes 8 and 40 while only
    # lane 0 is active. The restored bit 40 decides whether the triangle clips.
    cases = (
        ("positive", None, (1, 0x100), 0.5),
        ("drop-low", 8, (0, 0x100), -0.5),
        ("drop-high", 40, (1, 0), -0.5),
    )
    with tempfile.TemporaryDirectory() as scratch:
        draws = []
        for label, lane, expected_words, depth in cases:
            program = make_program(PROGRAM, lane)
            decoded = enumerate_pcs(program)
            wave = Wave(0, [4099])
            wave.run(decoded, {})
            assert (wave.scalar("s40"), wave.scalar("s41")) == expected_words, label
            source = lower(decoded, [4099], (3, 1))
            if args.binary:
                assert binary(Path(scratch), *args.binary, program=program, words=[4099]) == source, label
            inputs = triangle_inputs()
            assert evaluate_depth(source, inputs) == depth, label
            print(f"{label}: words={expected_words} CPU-triangle-depth={depth}", flush=True)
            positions = [(x, y, depth, w) for x, y, _, w in TRIANGLE]
            draws.append((label, source, inputs, positions, depth >= 0))
        if args.prepare:
            dxc, output = args.prepare
            prepare_draws(dxc, Path(output), draws, fixture, PIXEL)
        if args.draw:
            dxc, renderer, backend = args.draw
            if backend not in ("hardware", "warp"):
                parser.error("BACKEND must be hardware or warp")
            return run_draws(renderer, backend, *prepare_draws(dxc, Path(scratch), draws, fixture, PIXEL))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
