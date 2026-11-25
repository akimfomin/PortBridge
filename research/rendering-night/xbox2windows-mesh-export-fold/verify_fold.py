"""Assemble and compare one synthetic bounded mesh. No GPU device is opened."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys


def assemble(source, output, mc, objcopy):
    gfx1013 = [mc, "-triple=amdgcn--amdpal", "-mcpu=gfx1013", "-mattr=+wavefrontsize64,-wavefrontsize32"]
    obj, binary = output / "shader.o", output / "shader.bin"
    subprocess.run([*gfx1013, "-filetype=obj", source, "-o", obj], check=True, timeout=8)
    subprocess.run([objcopy, "-O", "binary", "--only-section=.text", obj, binary], check=True, timeout=8)
    raw = binary.read_bytes()
    dump = subprocess.run(
        [*gfx1013, "--disassemble", "--show-encoding"],
        input=" ".join(f"0x{value:02x}" for value in raw),
        capture_output=True, encoding="ascii", check=True, timeout=8,
    ).stdout
    decoded, offset = [], 0
    for line in dump.splitlines():
        instruction, marker, encoding = line.partition("; encoding:")
        if marker:
            data = bytes(int(value, 16) for value in re.findall(r"0x[\da-f]{2}", encoding))
            assert data == raw[offset:offset + len(data)], line
            decoded.append((offset, instruction.strip()))
            offset += len(data)
    assert offset == len(raw)
    print(f"guest shader: {len(raw)} bytes, sha256 {hashlib.sha256(raw).hexdigest()}")
    return decoded


def compare_dispatch(hlsl, inputs, oracle, mode):
    condition = re.compile(r"^\s+(?:else )?if \((.*?)\) \{ variant = (\d+); vertexCount = (\d+); primitiveCount = (\d+); \}$")
    fallback = re.compile(r"^\s+else \{ variant = (\d+); vertexCount = (\d+); primitiveCount = (\d+); \}$")
    predicate = re.compile(r"word(\d+) (!=|==) 0x([0-9a-f]+)u")
    cases = []
    for line in hlsl.splitlines():
        if match := condition.match(line):
            terms = [(int(i), op, int(value, 16)) for i, op, value in predicate.findall(match[1])]
            assert len(terms) == len(match[1].split(" && "))
            cases.append((terms, tuple(map(int, match.groups()[1:]))))
        elif match := fallback.match(line):
            cases.append(([], tuple(map(int, match.groups()))))
    assert len(cases) == 32
    bodies = {
        int(index): body
        for index, body in re.findall(r"^  if \(variant == (\d+)\) \{\n(.*?)^  \}$", hlsl, re.M | re.S)
    }
    observations = []
    for word in inputs:
        geometry = (0, word)
        index, vertices, primitives = next(
            value for terms, value in cases
            if all((geometry[i] == expected) == (op == "==") for i, op, expected in terms)
        )
        observations.append((word, vertices, primitives, bodies[index]))
    if mode == "baseline":
        with oracle.open("x", encoding="ascii") as file:
            file.write(repr(observations))
    else:
        assert oracle.read_text(encoding="ascii") == repr(observations)
    print(f"compared dispatch counts, vertices, attributes and indices over {len(observations)} inputs")
    return len(bodies)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("baseline", "candidate"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--llvm-mc", default="llvm-mc-15")
    parser.add_argument("--llvm-objcopy", default="llvm-objcopy-15")
    parser.add_argument("--dxc", default="dxc")
    args = parser.parse_args()
    sys.path[:0] = [str(args.repo.resolve() / "tests"), str(args.repo.resolve() / "tools")]
    from mesh_dynamic_aot import enumerate_variants, lower
    from mesh_dynamic_aot_check import select
    from mesh_dynamic_aot_draw_check import fixture

    args.output.mkdir(parents=True, exist_ok=True)
    decoded = assemble(Path(__file__).with_name("converging-mesh.s"), args.output, args.llvm_mc, args.llvm_objcopy)
    variants = enumerate_variants(decoded, 2, (4, 2))
    assert len(variants) == 32
    inputs = [*range(64), 0xFFFFFFFF]
    for word in inputs:
        variant = select(variants, (0, word))
        assert variant.counts == (4, 2)
        assert variant.indices == {0: [0, 1, 2], 1: [2, 1, 0 if 1 <= word <= 31 and word % 2 else 3]}, word
        assert len(variant.positions) == len(variant.attributes) == 4, word
    hlsl = lower(decoded, 2, (4, 2))
    blocks = compare_dispatch(hlsl, inputs, args.oracle, args.mode)
    target, mesh = (args.output / f"{args.mode}.{suffix}" for suffix in ("hlsl", "dxil"))
    target.write_text(hlsl, encoding="ascii", newline="\n")
    subprocess.run([args.dxc, "-T", "ms_6_5", "-E", "main", "-Fo", mesh, target], check=True, timeout=8)
    dump = subprocess.check_output([args.dxc, "-dumpbin", mesh], encoding="ascii", timeout=8)
    (args.output / f"{args.mode}.dxil.txt").write_text(dump, encoding="ascii")
    print(f"{args.mode}: export blocks={blocks}, hlsl bytes={len(hlsl)}, dxil bytes={mesh.stat().st_size}")
    print(f"DXIL storeVertexOutput calls={dump.count('call void @dx.op.storeVertexOutput')}, emitIndices calls={dump.count('call void @dx.op.emitIndices')}")

    pixel, ps = (args.output / f"solid-magenta.{name}" for name in ("hlsl", "dxil"))
    pixel.write_text("float4 main() : SV_Target { return float4(1,0,1,1); }", encoding="ascii")
    subprocess.run([args.dxc, "-WX", "-T", "ps_6_0", "-E", "main", "-Fo", ps, pixel], check=True, timeout=8)
    tri = fixture(0x2004, 1, ((0, 1, 2), (2, 1, 0)))
    full = fixture(0x2004, 2, ((0, 1, 2), (2, 1, 3)))
    (args.output / "geometry-1-triangle.bin").write_bytes(tri)
    (args.output / "geometry-2-quad.bin").write_bytes(full)
    (args.output / "geometry-1-stale-quad-pixels.bin").write_bytes(tri[:-4096] + full[-4096:])


if __name__ == "__main__":
    main()
