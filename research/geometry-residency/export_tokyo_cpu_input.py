"""Export the pinned LAS point columns for the standalone CPU comparator."""

from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).parent))
from tokyo_stock_point_edit import load_las, POINT_COUNT

archive, target = map(Path, sys.argv[sys.argv.index("--")+1:])
positions, classes, intensity, _ = load_las(archive)
with target.open("xb") as out:
    out.write(b"PBPC")
    out.write(struct.pack("<I", POINT_COUNT))
    for array in (positions, classes, intensity):
        if not array.flags.c_contiguous:
            raise ValueError("Input layout must be contiguous")
        out.write(memoryview(array))
