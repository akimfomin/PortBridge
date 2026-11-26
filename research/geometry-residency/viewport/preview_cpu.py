"""Strong fused CPU comparator for the exact point preview."""

import ctypes as C

import numpy as np


class CpuPreview:
    def __init__(self, library, source, workers):
        if source.dtype != np.float32 or not source.flags.c_contiguous or source.shape[1:] != (4,):
            raise ValueError("Expected contiguous float32 xy z class rows")
        self.lib = C.CDLL(str(library))
        self.lib.pb_view_create.argtypes = [C.c_uint32, C.c_uint32]
        self.lib.pb_view_create.restype = C.c_void_p
        self.lib.pb_view_destroy.argtypes = [C.c_void_p]
        self.lib.pb_view_destroy.restype = None
        self.lib.pb_view_edit.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_float]
        self.lib.pb_view_edit.restype = C.c_int
        self.lib.pb_view_mask.argtypes = [C.c_void_p] * 5 + [C.c_float]
        self.lib.pb_view_mask.restype = C.c_int
        self.source = source
        words = (len(source) + 31) // 32
        self.x = np.zeros(words * 32, dtype=np.float32)
        self.x[:len(source)] = source[:, 0]
        active = np.zeros(words * 32, dtype=np.bool_)
        active[:len(source)] = source[:, 3] == 1.0
        self.eligible = np.packbits(active, bitorder="little").view("<u4")
        self.limits = np.empty((words, 2), dtype=np.float32)
        self.limits[:, 0] = np.where(active, self.x, np.inf).reshape(words, 32).min(axis=1)
        self.limits[:, 1] = np.where(active, self.x, -np.inf).reshape(words, 32).max(axis=1)
        self.bits = np.empty(words, dtype=np.uint32)
        self.output = np.empty_like(source)
        self.state = self.lib.pb_view_create(len(source), workers)
        if not self.state:
            raise RuntimeError("Could not create reusable preview workers")

    def edit(self, threshold):
        if not self.lib.pb_view_edit(self.state, self.source.ctypes.data,
                                     self.output.ctypes.data, threshold):
            raise RuntimeError("Native preview edit failed")
        return self.output

    def mask(self, threshold):
        if not self.lib.pb_view_mask(self.state, self.x.ctypes.data, self.limits.ctypes.data,
                                     self.eligible.ctypes.data, self.bits.ctypes.data, threshold):
            raise RuntimeError("Native preview mask failed")
        return self.bits

    def close(self):
        if self.state:
            self.lib.pb_view_destroy(self.state)
            self.state = None
