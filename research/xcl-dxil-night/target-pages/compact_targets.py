"""Prototype a constant-data target lookup for a compact shader dispatcher."""

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import argparse
import json
import random
import re
import struct
import subprocess


MAX_TABLE_WORDS = 8192
MAX_SELECTS = 32
MASK32 = (1 << 32) - 1
SHADER_SEED = 2166136261
ROWS_PER_GROUP = 64
NATIVE_SIZE_LIMIT = 4096


@dataclass(frozen=True)
class Branch:
    offset: int
    overrides: tuple


def classify(blocks):
    """Group by branch body and preserve each absolute branch target."""
    cases = {}
    for block, (case, target) in enumerate(blocks):
        if target is not None:
            cases.setdefault(case, []).append((block, target))
    result = {}
    for case, entries in cases.items():
        counts = Counter(target - block for block, target in entries)
        offset = max(counts, key=lambda delta: (counts[delta], -abs(delta), delta))
        result[case] = Branch(
            offset, tuple((block, target) for block, target in entries if target - block != offset)
        )
    return result


@dataclass(frozen=True)
class Pages:
    classes: frozenset
    page_words: tuple
    target_words: tuple
    width: int

    def target(self, block, default):
        page, bit = divmod(block, 32)
        mask, base = self.page_words[2 * page:2 * page + 2]
        if not mask & (1 << bit):
            return default
        rank = base + (mask & ((1 << bit) - 1)).bit_count()
        position = rank * self.width
        word, shift = divmod(position, 32)
        value = self.target_words[word] >> shift
        if shift + self.width > 32:
            value |= self.target_words[word + 1] << (32 - shift)
        return value & ((1 << self.width) - 1)


def pack_pages(branches, block_count, existing_words, limit=MAX_TABLE_WORDS):
    """Use a single table for selected classes. All other classes keep inline selects."""
    if not 1 <= block_count <= MASK32 or existing_words < 0 or limit < existing_words:
        raise ValueError("invalid class-table budget")
    if any(not 0 <= block < block_count or not 0 <= target < block_count
           for branch in branches.values() for block, target in branch.overrides):
        raise ValueError("branch target must be a known block")
    width = max(1, (block_count - 1).bit_length())
    page_count = (block_count + 31) // 32
    room = limit - existing_words - 2 * page_count
    if room <= 0:
        return None
    capacity = room * 32 // width
    selected = set()
    entries = []
    for case, branch in sorted(branches.items(), key=lambda pair: (-len(pair[1].overrides), pair[0])):
        if not MAX_SELECTS < len(branch.overrides) <= capacity - len(entries):
            continue
        selected.add(case)
        entries.extend(branch.overrides)
    if not entries:
        return None

    entries.sort()
    words = [0] * (2 * page_count)
    values = [0] * ((len(entries) * width + 31) // 32)
    next_entry = 0
    for page in range(page_count):
        words[2 * page + 1] = next_entry
        while next_entry < len(entries) and entries[next_entry][0] // 32 == page:
            block, target = entries[next_entry]
            bit = block % 32
            if words[2 * page] & (1 << bit):
                raise ValueError("duplicate override for one block")
            words[2 * page] |= 1 << bit
            word, shift = divmod(next_entry * width, 32)
            values[word] |= (target << shift) & MASK32
            if shift + width > 32:
                values[word + 1] |= target >> (32 - shift)
            next_entry += 1
    assert existing_words + len(words) + len(values) <= limit
    return Pages(frozenset(selected), tuple(words), tuple(values), width)


def old_target(branch, block):
    """Evaluate the existing bounded-select strategy with an ordered binary partition."""
    entries = branch.overrides
    while len(entries) > MAX_SELECTS:
        middle = (((len(entries) + MAX_SELECTS - 1) // MAX_SELECTS) // 2) * MAX_SELECTS
        entries = entries[:middle] if block < entries[middle][0] else entries[middle:]
    picked = block + branch.offset
    for source, target in entries:
        if block == source:
            picked = target
    return picked


def array(name, words):
    return f"static const uint {name}[{len(words)}] = {{\n    " + ",\n    ".join(
        ", ".join(f"0x{v:08x}u" for v in words[base:base + 8])
        for base in range(0, len(words), 8)
    ) + "\n};"


def inline_tree(entries, indent):
    if len(entries) <= MAX_SELECTS:
        return [
            f"{indent}next = block == {block}u ? {target}u : next;"
            for block, target in entries
        ]
    leaves = (len(entries) + MAX_SELECTS - 1) // MAX_SELECTS
    middle = leaves // 2 * MAX_SELECTS
    return [
        f"{indent}[branch] if (block < {entries[middle][0]}u) {{",
        *inline_tree(entries[:middle], indent + "    "),
        f"{indent}}} else {{",
        *inline_tree(entries[middle:], indent + "    "),
        f"{indent}}}",
    ]


def shader(block_count, case_count, branches, pages, salt):
    lines = [
        "RWByteAddressBuffer output : register(u0);",
        '[RootSignature("UAV(u0)")]',
        "[numthreads(64, 1, 1)]",
        "void main(uint3 tid : SV_DispatchThreadID, uint3 group : SV_GroupID) {",
        f"    uint block = group.x % {block_count}u;",
        f"    uint result = tid.x ^ {salt}u;",
        f"    [loop] for (uint steps = 0; steps < {block_count}u; ++steps) {{",
        f"        if (block >= {block_count}u) break;",
        "        uint next = block + 1u;",
        "        bool lookup = false;",
        f"        switch (block % {case_count}u) {{",
    ]
    if pages:
        lines[:0] = [array("page_map", pages.page_words), array("target_map", pages.target_words)]
    for case, branch in sorted(branches.items()):
        lines.extend([
            f"        case {case}u:",
            f"            result = (result ^ block) * {1664525 + 2 * case}u;",
            f"            next = block {'+' if branch.offset >= 0 else '-'} {abs(branch.offset)}u;",
        ])
        if pages and case in pages.classes:
            lines.append("            lookup = true;")
        else:
            lines.extend(inline_tree(branch.overrides, "            "))
        lines.append("            break;")
    lines.append("        default: result += block; break;")
    lines.append("        }")
    if pages:
        lines.extend([
            "        if (lookup) {",
            "            uint page = (block >> 5) * 2u;",
            "            uint bit = 1u << (block & 31u);",
            "            uint mask = page_map[page];",
            "            if ((mask & bit) != 0u) {",
            "                uint rank = page_map[page + 1u] + countbits(mask & (bit - 1u));",
            f"                uint position = rank * {pages.width}u;",
            "                uint word = position >> 5;",
            "                uint shift = position & 31u;",
            "                uint value = target_map[word] >> shift;",
            f"                if (shift + {pages.width}u > 32u)",
            "                    value |= target_map[word + 1u] << (32u - shift);",
            f"                next = value & 0x{(1 << pages.width) - 1:x}u;",
            "            }",
            "        }",
        ])
    lines.extend([
        "        block = next;",
        "    }",
        "    output.Store(4u * tid.x, result);",
        "}",
    ])
    return "\n".join(lines) + "\n"


def fixture(block_count, case_count, mode, seed):
    rng = random.Random(seed)
    rows = []
    for block in range(block_count):
        case = block % case_count
        if mode == "uniform":
            jump = 1 + case % 3
        elif mode == "clustered" and case >= 3:
            jump = 1
        else:
            jump = rng.randrange(1, 13) if rng.random() < 0.72 else 1
        target = block + jump
        rows.append((case, min(target, block_count - 1) if block != block_count - 1 else None))
    return rows


def validate(blocks, branches, pages):
    for block, (case, target) in enumerate(blocks):
        if target is None:
            continue
        branch = branches[case]
        original = old_target(branch, block)
        planned = (
            pages.target(block, block + branch.offset)
            if pages and case in pages.classes else original
        )
        if target != original or target != planned:
            raise AssertionError((block, case, target, original, planned))
    return len(blocks)


def expected_buffer(rows, groups):
    """Interpret the explicit target list independently of both dispatch encodings."""
    reference = bytearray()
    for group in range(groups):
        walk = []
        block = group % len(rows)
        while block is not None:
            case, target = rows[block]
            if len(walk) == len(rows):
                raise AssertionError("native fixture must be acyclic and bounded")
            walk.append((block, 1664525 + 2 * case))
            block = target
        for lane in range(ROWS_PER_GROUP):
            value = (group * ROWS_PER_GROUP + lane) ^ SHADER_SEED
            for block, multiplier in walk:
                value = ((value ^ block) * multiplier) & MASK32
            reference.extend(struct.pack("<I", value))
    return bytes(reference)


def self_test():
    checks = 0
    for seed in range(48):
        rng = random.Random(seed)
        for size in (31, 32, 33, 65, 127, 129, 511, 1024):
            blocks = [(0, rng.randrange(size)) for _ in range(size)]
            branches = classify(blocks)
            for room in (0, 31, 256, 8192):
                pages = pack_pages(branches, size, 0, room)
                checks += validate(blocks, branches, pages)
                if pages:
                    assert len(pages.page_words) + len(pages.target_words) <= room
    exception = {0: Branch(0, tuple((i, 0) for i in range(33)))}
    assert pack_pages(exception, 65, 0, 6) is None
    pages = pack_pages(exception, 65, 0, 14)
    assert pages and pages.target(31, 99) == 0 and pages.target(33, 99) == 99
    return checks


def run_shader_tool(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, check=False, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def emit(output, dxc, dxc_validator):
    output.mkdir(exist_ok=False)
    results = []
    for blocks, cases, mode, mandatory_words in (
        (96, 1, "clustered", 3),
        (2048, 8, "uniform", 192),
        (512, 4, "clustered", 36),
        (2048, 8, "clustered", 192),
        (4096, 16, "spread", 512),
        (4096, 16, "spread", 7776),
    ):
        rows = fixture(blocks, cases, mode, seed=921)
        branches = classify(rows)
        pages = pack_pages(branches, blocks, mandatory_words)
        validate(rows, branches, pages)
        pair = {}
        for name, table in (("inline", None), ("pages", pages)):
            stem = output / f"{blocks}-{cases}-{mode}-{mandatory_words}-{name}"
            source = stem.with_suffix(".hlsl")
            dxil = stem.with_suffix(".dxil")
            source.write_text(shader(blocks, cases, branches, table, SHADER_SEED), encoding="ascii")
            run_shader_tool([
                dxc, "-T", "cs_6_6", "-E", "main", "-O3", "-Qstrip_reflect", "-Fo", str(dxil), str(source)
            ])
            ir = run_shader_tool([dxc, "-dumpbin", str(dxil)])
            run_shader_tool([dxc_validator, str(dxil)])
            pair[name] = {
                "source_bytes": source.stat().st_size,
                "container_bytes": dxil.stat().st_size,
                "container_sha256": sha256(dxil.read_bytes()).hexdigest(),
                "compare_instructions": len(re.findall(r"^\s*%\d+ = icmp ", ir, re.MULTILINE)),
                "select_instructions": len(re.findall(r"^\s*%\d+ = select ", ir, re.MULTILINE)),
            }
        if not pages:
            assert pair["inline"] == pair["pages"]
        if blocks == 96:
            assert pages and all(data["container_bytes"] <= NATIVE_SIZE_LIMIT for data in pair.values())
            expected = expected_buffer(rows, blocks)
            (output / "readback-initial.bin").write_bytes(bytes([0xA5]) * len(expected))
            (output / "readback-reference.bin").write_bytes(expected)
            (output / "readback-meta.json").write_text(json.dumps({
                "groups": blocks, "words": blocks * ROWS_PER_GROUP,
                "bytes": len(expected), "expected_hash": sha256(expected).hexdigest(),
            }, indent=2) + "\n", encoding="utf-8")
        results.append({
            "blocks": blocks, "case_count": cases, "shape": mode, "existing_words": mandatory_words,
            "overrides": sum(len(branch.overrides) for branch in branches.values()),
            "encoded_cases": sorted(pages.classes) if pages else [],
            "extra_words": len(pages.page_words) + len(pages.target_words) if pages else 0,
            "variants": pair,
        })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dxc", type=Path)
    parser.add_argument("--dxv", type=Path)
    args = parser.parse_args()
    checks = self_test()
    if not args.output:
        print(f"{checks} exact target checks passed")
        return
    if not args.dxc or not args.dxv:
        parser.error("--dxc and --dxv are required when emitting shaders")
    result = {"target_checks": checks, "fixtures": emit(args.output, args.dxc, args.dxv)}
    (args.output / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
