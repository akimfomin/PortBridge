"""Exercise AnyXboxX ShaderCache with a real Windows sharing violation."""
import ctypes
from ctypes import wintypes
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def run(source, *, patched):
    spec = spec_from_file_location("shader_cache_lock_probe", source)
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    open_file = kernel.CreateFileW
    open_file.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                          wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    open_file.restype = wintypes.HANDLE
    close_file = kernel.CloseHandle
    close_file.argtypes = (wintypes.HANDLE,)
    close_file.restype = wintypes.BOOL
    generic_read = 0x80000000
    share_read, share_write, open_existing = 1, 2, 3
    contents = b"synthetic incomplete shader cache entry"
    with TemporaryDirectory() as tmp:
        cache = module.ShaderCache(Path(tmp))
        key = module.cache_key("locked entry", "cs_6_0", None)
        path = cache._path(key)
        path.parent.mkdir(parents=True)
        path.write_bytes(contents)
        handle = open_file(str(path), generic_read, share_read | share_write, None, open_existing, 0, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            assert path.read_bytes() == contents
            if patched:
                assert cache.get(key) is None
                assert cache.stats.misses == 1 and cache.stats.hits == 0
                assert key not in cache.memory and path.read_bytes() == contents
                print("Patched: cache miss, locked synthetic bytes unchanged, no memory entry")
            else:
                try:
                    cache.get(key)
                except PermissionError as exc:
                    assert exc.winerror == 32, exc
                    print("Baseline: WinError 32 during deletion")
                else:
                    raise AssertionError("baseline unexpectedly returned from get")
        finally:
            if not close_file(handle):
                raise ctypes.WinError(ctypes.get_last_error())
        assert cache.get(key) is None and not path.exists()
        print("After closing the handle: corrupt entry removed on both paths")


if __name__ == "__main__":
    run(Path(sys.argv[1]), patched=False)
    run(Path(sys.argv[2]), patched=True)
