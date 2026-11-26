"""A stable GPU two-way partition for the pinned Tokyo point edit in Blender 5.3."""

import numpy as np


THREADS = 128
ROWS_PER_LANE = 4
TILE_ROWS = THREADS * ROWS_PER_LANE
WORDS_PER_TILE = TILE_ROWS // 32
MAX_POINT_COUNT = TILE_ROWS * THREADS ** 2
EDITED = np.uint32(1 << 31)
SOURCE_ID_MASK = EDITED - np.uint32(1)

COUNT_BUFFERS = (
    ("float", "pointX", "READ"),
    ("int", "pointClass", "READ"),
    ("uint", "tileMaskRank", "WRITE"),
    ("uint", "tileTotal", "WRITE"),
)
COUNT_PACKED_BUFFERS = (COUNT_BUFFERS[0], *COUNT_BUFFERS[2:])
COUNT_CONSTANTS = (("UINT", "pointCount"), ("UINT", "xStride"), ("FLOAT", "cutX"))
COUNT_SOURCE = """
shared uint laneMask[THREADS];
shared uint wordMask[WORDS_PER_TILE];

void main()
{
    uint lane = gl_LocalInvocationID.x;
    uint first = gl_GlobalInvocationID.x * 4u;
    uint bits = 0u;
    for (uint k = 0u; k < 4u; ++k) {
        uint id = first + k;
        if (id < pointCount) {
            uint offset = id * xStride;
#ifdef PACKED_ROWS
            bool editable = pointX[offset + 3u] == 1.0;
#else
            bool editable = pointClass[id] == 1;
#endif
            if (editable && pointX[offset] < cutX) {
                bits |= 1u << k;
            }
        }
    }
    laneMask[lane] = bits;
    barrier();
    if (lane < uint(WORDS_PER_TILE)) {
        uint packed = 0u;
        for (uint k = 0u; k < 8u; ++k) {
            packed |= laneMask[lane * 8u + k] << (k * 4u);
        }
        wordMask[lane] = packed;
    }
    barrier();
    if (lane == 0u) {
        uint base = gl_WorkGroupID.x * uint(WORDS_PER_TILE) * 2u;
        uint count = 0u;
        for (uint k = 0u; k < uint(WORDS_PER_TILE); ++k) {
            uint packed = wordMask[k];
            tileMaskRank[base + 2u * k] = packed;
            tileMaskRank[base + 2u * k + 1u] = count;
            count += uint(bitCount(packed));
        }
        tileTotal[gl_WorkGroupID.x] = count;
    }
}
"""

SCAN_BUFFERS = (
    ("uint", "counts", "READ"),
    ("uint", "offsets", "WRITE"),
    ("uint", "groupTotal", "WRITE"),
)
SCAN_CONSTANTS = (("UINT", "itemCount"),)
SCAN_SOURCE = """
shared uint work[THREADS];

void main()
{
    uint lane = gl_LocalInvocationID.x;
    uint i = gl_GlobalInvocationID.x;
    work[lane] = i < itemCount ? counts[i] : 0u;
    barrier();
    for (uint span = 1u; span < uint(THREADS); span <<= 1u) {
        uint j = (lane + 1u) * (span << 1u) - 1u;
        if (j < uint(THREADS)) {
            work[j] += work[j - span];
        }
        barrier();
    }
    if (lane == 0u) {
        groupTotal[gl_WorkGroupID.x] = work[THREADS - 1];
        work[THREADS - 1] = 0u;
    }
    barrier();
    for (uint span = uint(THREADS) >> 1u; span > 0u; span >>= 1u) {
        uint j = (lane + 1u) * (span << 1u) - 1u;
        if (j < uint(THREADS)) {
            uint left = work[j - span];
            work[j - span] = work[j];
            work[j] += left;
        }
        barrier();
    }
    if (i < itemCount) {
        offsets[i] = work[lane];
    }
}
"""

SCATTER_BUFFERS = (
    ("uint", "tileMaskRank", "READ"),
    ("uint", "tileOffset", "READ"),
    ("uint", "slabOffset", "READ"),
    ("uint", "selectedTotal", "READ"),
    ("uint", "packedIndices", "WRITE"),
)
SCATTER_CONSTANTS = (("UINT", "pointCount"),)
SCATTER_SOURCE = """
void main()
{
    uint first = gl_GlobalInvocationID.x * 4u;
    if (first >= pointCount) {
        return;
    }
    uint group = gl_WorkGroupID.x;
    uint word = 2u * (first >> 5u);
    uint bits = tileMaskRank[word];
    uint lane = first & 31u;
    uint selected = slabOffset[group / uint(THREADS)] + tileOffset[group] +
                    tileMaskRank[word + 1u] + uint(bitCount(bits & ((1u << lane) - 1u)));
    uint retainedTotal = pointCount - selectedTotal[0];
    for (uint k = 0u; k < 4u && first + k < pointCount; ++k) {
        uint id = first + k;
        bool edit = (bits & (1u << (lane + k))) != 0u;
        uint dst = edit ? retainedTotal + selected : id - selected;
        packedIndices[dst] = edit ? id | 0x80000000u : id;
        selected += uint(edit);
    }
}
"""

KERNELS = (
    ("classify", COUNT_BUFFERS, COUNT_CONSTANTS, COUNT_SOURCE),
    ("classify-packed", COUNT_PACKED_BUFFERS, COUNT_CONSTANTS, "#define PACKED_ROWS\n" + COUNT_SOURCE),
    ("scan", SCAN_BUFFERS, SCAN_CONSTANTS, SCAN_SOURCE),
    ("scatter", SCATTER_BUFFERS, SCATTER_CONSTANTS, SCATTER_SOURCE),
)


def cpu_partition(x, point_class, threshold):
    """Return retained IDs then edited IDs, stable within both partitions."""
    edited = (x < np.float32(threshold)) & (point_class == 1)
    return np.concatenate((
        np.flatnonzero(~edited).astype(np.uint32),
        np.flatnonzero(edited).astype(np.uint32) | EDITED,
    ))


def _shader(gpu, buffers, constants, source):
    info = gpu.types.GPUShaderCreateInfo()
    info.local_group_size(THREADS)
    info.define("THREADS", str(THREADS))
    info.define("WORDS_PER_TILE", str(WORDS_PER_TILE))
    for binding, (dtype, name, access) in enumerate(buffers):
        info.storage_buf(binding, dtype, name + "[]", qualifiers={access})
    for dtype, name in constants:
        info.push_constant(dtype, name)
    # PyGPU's stage preprocessor in Blender 5.3 drops workgroup declarations.
    # The Vulkan compiler consumes the generated typedef source verbatim.
    workgroup = [line for line in source.splitlines() if line.startswith("shared ")]
    if workgroup:
        info.typedef_source("\n".join(workgroup) + "\n")
        source = source.replace("\n".join(workgroup), "")
    info.compute_source(source)
    return gpu.shader.create_from_info(info)


def _dispatch(gpu, shader, buffers, constants, groups):
    shader.bind()
    for name, buffer in buffers:
        shader.storage_block(name, buffer)
    for name, value in constants:
        if isinstance(value, int):
            shader.uniform_int(name, value)
        else:
            shader.uniform_float(name, value)
    gpu.compute.dispatch(shader, groups, 1, 1)


def _ceil_div(numerator, divisor):
    return (numerator + divisor - 1) // divisor


class StablePartition:
    """Reusable source and scratch buffers, valid within the active Blender GPU context."""

    def __init__(self, x, point_class):
        """Upload immutable float32 x and int32 class columns."""
        import gpu

        x = np.ascontiguousarray(x, dtype=np.float32)
        point_class = np.ascontiguousarray(point_class, dtype=np.int32)
        if x.ndim != 1 or point_class.shape != x.shape:
            raise ValueError("expected x and class vectors with matching lengths")
        self._validate_shape(x.size, 1)
        self._initialize(gpu, gpu.types.GPUStorageBuf(x), gpu.types.GPUStorageBuf(point_class),
                         x.size, 1)
        self.source_bytes = _ceil_div(x.nbytes, 16) * 16 + _ceil_div(point_class.nbytes, 16) * 16

    @classmethod
    def from_gpu(cls, position_storage, class_storage, count, stride=3):
        """Borrow existing SSBOs with scalar float32 coordinates and int32 classes."""
        import gpu

        cls._validate_shape(count, stride)
        partition = cls.__new__(cls)
        partition._initialize(gpu, position_storage, class_storage, count, stride)
        partition.source_bytes = 0
        return partition

    @classmethod
    def from_packed_rows(cls, storage, count):
        """Borrow a read-only packed SSBO of x, y, z, float32(class) rows."""
        import gpu

        cls._validate_shape(count, 4)
        partition = cls.__new__(cls)
        partition._initialize(gpu, storage, None, count, 4)
        partition.source_bytes = 0
        return partition

    @staticmethod
    def _validate_shape(count, stride):
        if not 0 < count <= MAX_POINT_COUNT:
            raise ValueError(f"point count must be in [1, {MAX_POINT_COUNT}]")
        if not 0 < stride <= 4:
            raise ValueError("coordinate stride must be 1–4 float32 scalars")

    def _initialize(self, gpu, point_x, point_class, count, stride):
        self._gpu = gpu
        self._point_x = point_x
        self._point_class = point_class
        self.count = count
        self.stride = stride
        self.tiles = _ceil_div(count, TILE_ROWS)
        self.slabs = _ceil_div(self.tiles, THREADS)
        self.scratch_bytes = 0
        self.mask_rank = self._allocate(self.tiles * WORDS_PER_TILE * 2)
        self.tile_total = self._allocate(self.tiles)
        self.tile_offset = self._allocate(self.tiles)
        self.slab_total = self._allocate(self.slabs)
        self.slab_offset = self._allocate(self.slabs)
        self.total = self._allocate(1)
        self.indices = self._allocate(count)
        kernels = (KERNELS[1] if point_class is None else KERNELS[0], *KERNELS[2:])
        self._classify, self._scan, self._scatter = (
            _shader(gpu, buffers, constants, source) for _, buffers, constants, source in kernels
        )

    def _allocate(self, words):
        self.scratch_bytes += _ceil_div(words * 4, 16) * 16
        return self._gpu.types.GPUStorageBuf(np.zeros(words, dtype=np.uint32))

    def classify(self, threshold):
        """Build current masks and local ranks without the compact index stream."""
        buffers = [("pointX", self._point_x)]
        if self._point_class is not None:
            buffers.append(("pointClass", self._point_class))
        buffers.extend((("tileMaskRank", self.mask_rank), ("tileTotal", self.tile_total)))
        constants = (("pointCount", self.count), ("xStride", self.stride),
                     ("cutX", float(threshold)))
        _dispatch(self._gpu, self._classify, buffers, constants, self.tiles)
        return self.mask_rank

    def build_indices(self):
        """Compact the current masks to a stable device index stream."""
        for source, offsets, total, size, groups in (
            (self.tile_total, self.tile_offset, self.slab_total, self.tiles, self.slabs),
            (self.slab_total, self.slab_offset, self.total, self.slabs, 1),
        ):
            _dispatch(self._gpu, self._scan,
                      (("counts", source), ("offsets", offsets), ("groupTotal", total)),
                      (("itemCount", size),), groups)
        buffers = (("tileMaskRank", self.mask_rank), ("tileOffset", self.tile_offset),
                   ("slabOffset", self.slab_offset), ("selectedTotal", self.total),
                   ("packedIndices", self.indices))
        _dispatch(self._gpu, self._scatter, buffers, (("pointCount", self.count),), self.tiles)
        return self.indices

    def edit(self, threshold):
        self.classify(threshold)
        return self.build_indices()

    def read_indices(self):
        """Observe the exact source IDs and edit flags, synchronizing with the device."""
        return np.frombuffer(memoryview(self.indices.read()), dtype=np.uint32, count=self.count)
