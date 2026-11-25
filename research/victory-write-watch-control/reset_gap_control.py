"""Verify that a resetting union query consumes observations inside skipped gaps."""

import ctypes as c
from ctypes import wintypes as w
from mmap import PAGESIZE


WINDOW = 4 * 1024 * 1024
CAPACITY = 16 * WINDOW
WRITE_WATCH_FLAG_RESET = 1
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
MEM_WRITE_WATCH = 0x200000
PAGE_READWRITE = 4
kernel32 = c.WinDLL("kernel32", use_last_error=True)
kernel32.VirtualAlloc.argtypes = (c.c_void_p, c.c_size_t, w.DWORD, w.DWORD)
kernel32.VirtualAlloc.restype = c.c_void_p
kernel32.VirtualFree.argtypes = (c.c_void_p, c.c_size_t, w.DWORD)
kernel32.VirtualFree.restype = w.BOOL
kernel32.GetWriteWatch.argtypes = (
    w.DWORD, c.c_void_p, c.c_size_t, c.POINTER(c.c_void_p),
    c.POINTER(c.c_size_t), c.POINTER(w.DWORD),
)
kernel32.GetWriteWatch.restype = w.UINT
kernel32.ResetWriteWatch.argtypes = (c.c_void_p, c.c_size_t)
kernel32.ResetWriteWatch.restype = w.UINT


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check_status(status):
    if status != 0:
        raise OSError(f"Write-watch call failed with status {status}")


def queried_pages(base, first_window, windows, flags):
    size = windows * WINDOW
    pages = (c.c_void_p * (size // PAGESIZE))()
    count = c.c_size_t(len(pages))
    granularity = w.DWORD()
    check_status(kernel32.GetWriteWatch(
        flags, base + first_window * WINDOW, size, pages,
        c.byref(count), c.byref(granularity),
    ))
    require(granularity.value == PAGESIZE, 'Unexpected kernel page granularity')
    return {(address - base) // PAGESIZE for address in pages[:count.value]}


def seed_pages(base, expected):
    check_status(kernel32.ResetWriteWatch(base, CAPACITY))
    for page in expected:
        c.c_ubyte.from_address(base + page * PAGESIZE).value = 1


def main():
    base = kernel32.VirtualAlloc(
        None, CAPACITY, MEM_RESERVE | MEM_COMMIT | MEM_WRITE_WATCH, PAGE_READWRITE,
    )
    if not base:
        raise c.WinError(c.get_last_error())
    try:
        all_pages = frozenset(range(3, CAPACITY // PAGESIZE, 53))
        gap_windows = range(1, 15, 2)
        expected_gap = {
            page for page in all_pages if page * PAGESIZE // WINDOW in gap_windows
        }
        expected_selected = {
            page for page in all_pages if page * PAGESIZE // WINDOW % 2 == 0
        }
        seed_pages(base, all_pages)
        baseline = set().union(*(
            queried_pages(base, index, 1, WRITE_WATCH_FLAG_RESET) for index in range(0, 16, 2)
        ))
        later_gaps = set().union(*(
            queried_pages(base, index, 1, 0) for index in gap_windows
        ))
        require(baseline == expected_selected, 'Selected pages differ in separate queries')
        require(later_gaps == expected_gap, 'Separate reset queries consumed gap pages')

        seed_pages(base, all_pages)
        union = queried_pages(base, 0, 15, WRITE_WATCH_FLAG_RESET)
        later_union_gaps = set().union(*(
            queried_pages(base, index, 1, 0) for index in gap_windows
        ))
        require(union == expected_selected | expected_gap, 'Enclosing query returned the wrong pages')
        require(not later_union_gaps, 'Enclosing reset left gap pages visible')

        print(f"Separate reset calls returned {len(baseline)} requested pages.")
        print(f"A later query still found {len(later_gaps)} dirty pages in the gaps.")
        print(f"The union reset returned {len(union)} pages, including {len(expected_gap)} in gaps.")
        print(f"Later gap queries after union reset found {len(later_union_gaps)} pages.")
    finally:
        if not kernel32.VirtualFree(base, 0, MEM_RELEASE):
            raise c.WinError(c.get_last_error())


if __name__ == "__main__":
    main()
