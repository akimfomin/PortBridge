"""Build a vectorized Halide CPU baseline for the same preview and pixel semantics."""
import halide as h

size = 512
radius = 4
x, y, xo, yo, xi, yi = (h.Var(name) for name in ('x', 'y', 'xo', 'yo', 'xi', 'yi'))
src = h.ImageParam(h.Float(32), 2, 'input')
src.dim(0).set_bounds(0, size).set_stride(1)
src.dim(1).set_bounds(0, size).set_stride(size)
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
out = h.Func('cpu_gaussian_preview')
out[x, y] = sum(vertical[h.clamp(x + i-radius, 0, size-1), y]*weight[()] for i, weight in enumerate(weights))
out.tile(x, y, xo, yo, xi, yi, 128, 32).vectorize(xi, 8)
vertical.compute_at(out, xo).vectorize(x, 8, h.TailStrategy.GuardWithIf)
out.bound(x, 0, size).bound(y, 0, size)
out.output_buffer().dim(0).set_bounds(0, size).set_stride(1)
out.output_buffer().dim(1).set_bounds(0, size).set_stride(size)
out.compile_to_static_library('cpu-gaussian-preview', [src, sigma], 'cpu_gaussian_preview',
                              h.Target('wasm-32-wasmrt-wasm_simd128'))
