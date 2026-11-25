"""Matching Halide CPU SIMD baselines for the Hubble LoG preview."""
import argparse
import halide as h

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--threads', action='store_true')
args = parser.parse_args()

width, height, radius = 1000, 872, 16
x, y, xo, yo, xi, yi = (h.Var(name) for name in ('x', 'y', 'xo', 'yo', 'xi', 'yi'))
src = h.ImageParam(h.Float(32), 2, 'input')
src.dim(0).set_bounds(0, width).set_stride(1)
src.dim(1).set_bounds(0, height).set_stride(width)
sigma = h.Param(h.Float(32), 'sigma')
values = [h.exp(-i*i / (2*sigma*sigma)) for i in range(-radius, radius+1)]
total = sum(values)
weights = [h.Func(f'weight_{i}') for i in range(len(values))]
for weight, value in zip(weights, values):
    weight[()] = value/total
    weight.compute_root()
sample = h.BoundaryConditions.repeat_edge(src)
vertical = h.Func('vertical')
vertical[x, y] = sum(sample[x, y + i-radius]*weight[()] for i, weight in enumerate(weights))
smooth = h.Func('smooth')
smooth[x, y] = sum(vertical[h.clamp(x + i-radius, 0, width-1), y]*weight[()] for i, weight in enumerate(weights))
left, right = h.max(x-1, 0), h.min(x+1, width-1)
up, down = h.max(y-1, 0), h.min(y+1, height-1)
out = h.Func('cpu_gaussian_preview')
out[x, y] = (4*smooth[x, y]-smooth[left, y]-smooth[right, y]-smooth[x, up]-smooth[x, down])*sigma*sigma
out.tile(x, y, xo, yo, xi, yi, 200, 16, h.TailStrategy.GuardWithIf).vectorize(xi, 8)
if args.threads:
    out.parallel(yo)
for stage in (vertical, smooth):
    stage.compute_at(out, xo).vectorize(x, 8, h.TailStrategy.GuardWithIf)
out.bound(x, 0, width).bound(y, 0, height)
out.output_buffer().dim(0).set_bounds(0, width).set_stride(1)
out.output_buffer().dim(1).set_bounds(0, height).set_stride(width)
features = '-wasm_threads' if args.threads else ''
out.compile_to_static_library('cpu-gaussian-preview', [src, sigma], 'cpu_gaussian_preview',
                              h.Target('wasm-32-wasmrt-wasm_simd128' + features))
