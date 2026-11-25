"""Build a scale-normalized Laplacian-of-Gaussian image preview in Halide WebGPU."""
import halide as h

width, height, radius = 1000, 872, 16
x, y, ix, iy = (h.Var(name) for name in ('x', 'y', 'ix', 'iy'))
src = h.ImageParam(h.Float(32), 2, 'input')
src.dim(0).set_bounds(0, width).set_stride(1)
src.dim(1).set_bounds(0, height).set_stride(width)
sigma = h.Param(h.Float(32), 'sigma')
k = h.Func('kernel')
k[x] = h.exp(-h.cast(h.Float(32), x*x) / (2 * sigma*sigma))
r = h.RDom([(-radius, 2*radius + 1)], 'tap')
weights = h.Func('weights')
weights[x] = k[x] / h.sum(r, k[r.x])
weights.compute_root()
sample = h.BoundaryConditions.repeat_edge(src)
vertical = h.Func('vertical')
vertical[x, y] = h.sum(r, sample[x, y+r.x] * weights[r.x])
smooth = h.Func('smooth')
smooth[x, y] = h.sum(r, vertical[h.clamp(x+r.x, 0, width-1), y] * weights[r.x])
left, right = h.max(x-1, 0), h.min(x+1, width-1)
up, down = h.max(y-1, 0), h.min(y+1, height-1)
out = h.Func('log_preview')
out[x, y] = (4*smooth[x, y]-smooth[left, y]-smooth[right, y]-smooth[x, up]-smooth[x, down])*sigma*sigma
for stage in (vertical, smooth, out):
    stage.compute_root().never_partition([x, y]).gpu_tile(x, y, ix, iy, 20, 8)
out.bound(x, 0, width).bound(y, 0, height)
out.output_buffer().dim(0).set_bounds(0, width).set_stride(1)
out.output_buffer().dim(1).set_bounds(0, height).set_stride(width)
out.compile_to_static_library('log-preview', [src, sigma], 'log_preview', h.Target('wasm-32-wasmrt-webgpu'))
