# SPDX-License-Identifier: MIT
"""List SPIR-V set/binding pairs shared across distinct MiniEngine globals at the original pins."""

import argparse
import json
import re
import subprocess
from collections import defaultdict
from hashlib import sha256
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "dis", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    observations = []
    for i, entry in enumerate(manifest["observations"]):
        if entry["group"] != "miniengine":
            continue
        inp = args.manifest.parent / f"{i:03d}" / "source.spv"
        if not inp.exists():
            observations.append(
                {"id": i, "source": entry["source"], "unavailable": True}
            )
            continue
        digest = sha256(inp.read_bytes()).hexdigest()
        if digest != entry["spirv"]["sha256"]:
            raise ValueError("Original SPIR-V does not match its export")
        asm = subprocess.check_output([args.dis, inp], text=True, encoding="utf-8")
        bindings = dict(re.findall(r"OpDecorate (%\w+) Binding (\d+)", asm))
        sets = dict(re.findall(r"OpDecorate (%\w+) DescriptorSet (\d+)", asm))
        slots = defaultdict(list)
        for var, b in bindings.items():
            slots[(sets[var], b)].append(var)
        collisions = [
            {"set": int(s), "binding": int(b), "variables": v}
            for (s, b), v in slots.items()
            if len(v) > 1
        ]
        observations.append(
            {
                "id": i,
                "source": entry["source"],
                "spirv_sha256": digest,
                "overlap": collisions,
            }
        )
    result = {
        "source": manifest["sources"]["miniengine"],
        "rows": observations,
        "entries_with_overlapping_decorations": sum(
            bool(r.get("overlap")) for r in observations
        ),
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(result["entries_with_overlapping_decorations"], len(observations))


if __name__ == "__main__":
    main()
