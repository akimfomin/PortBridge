"""Check that XCL's normal translation created each synthetic scalar ring."""

from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parent
DXC = ROOT.parent / "portbridge-xcl-925-evidence/dxc-v1.9.2602/bin/x64/dxc.exe"


def fnv64(data):
    h = 0xCBF29CE484222325
    for byte in data:
        h = ((h ^ byte) * 0x100000001B3) & ((1 << 64) - 1)
    return h


def phi_graph(asm):
    return {name: re.findall(r"\[ (%\d+|-?\d+|undef|poison), %\d+ \]", args)
            for name, args in re.findall(r"^\s*(%\d+) = phi i32 (.+)$", asm, re.MULTILINE)}


def ring_seeds(phis, width):
    for first in phis:
        node, visited = first, set()
        while node not in visited:
            visited.add(node)
            links = [operand for operand in phis[node] if operand in phis]
            if len(links) != 1:
                break
            node = links[0]
        else:
            if node == first and len(visited) == width:
                return {arg for v in visited for arg in phis[v] if arg not in visited}
    return None


def inspect(stem, width, distinct_seeds):
    blob = ROOT / "scalar-records" / f"{stem}.bin"
    hash_value = fnv64(blob.read_bytes())
    translated = ROOT / "scalar-dxil" / f"{hash_value:016x}_f0_308.direct.dxil"
    asm = subprocess.check_output([str(DXC), "-dumpbin", str(translated)], text=True, timeout=8)
    phis = phi_graph(asm)
    seeds = ring_seeds(phis, width)
    assert seeds is not None and len(seeds) == distinct_seeds, (stem, seeds)
    print(f"{stem} {translated.stat().st_size} bytes, {len(phis)} PHIs, live ring={width}, outside={sorted(seeds)}")


if __name__ == "__main__":
    for name, width, outside in (("one-seed2", 2, 1), ("one-seed16", 16, 1), ("one-seed64", 64, 1),
                                 ("two-seeds16", 16, 2)):
        inspect(name, width, outside)
