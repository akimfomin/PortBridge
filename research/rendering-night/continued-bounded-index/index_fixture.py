"""Generate only synthetic shader-catalog metadata for the native loader checks."""

import argparse
import hashlib
import json
from pathlib import Path


STAGES = ("cs", "vs", "ps", "ms")


def key(i):
    return f"{i + 1:064x}"


def name(i):
    return f"Synthetic_{STAGES[i % len(STAGES)]}_{i:06d}"


def metadata(i, richness):
    stage = STAGES[i % len(STAGES)]
    result = {
        "stage": stage, "fssm_sha256": key(i), "spv": name(i) + ".spv",
        "push_constant_bytes": 16 * (i % 10), "lds_bytes": 32 * (i % 17),
        "local_size": [32 if i % 2 else 64, 1, 1], "uses_code_base": i % 11 == 0,
        "wave64": i % 2 == 0, "subgroup_size": 32 if i % 2 else 64,
        "wave64_exchange": "workgroup" if i % 7 == 0 else "",
        "descriptor_hash": "fnv1a_fmix32" if i % 3 == 0 else "fnv1a",
        "bindings": [
            {"set": 0, "binding": binding, "kind": "storage_buffer", "readonly": binding % 2 == 1}
            for binding in range(richness + i % 4)
        ],
        "literal_samplers": [[i, i + 1, i + 2, i + 3]]
        if i % 3 == 0 and richness > 1 else [],
    }
    if stage in ("vs", "ps", "ms"):
        result["input_signature"] = [
            {"semantic": "TEXCOORD", "semantic_index": j, "register": j + 1,
             "system_value": 0, "component_type": "float"}
            for j in range((richness + 1) // 2)
        ]
        result["inputs"] = list(range(richness))
        result["outputs"] = [0, 2, 5]
        result["f16_halves"] = {"1": [1, 3], "2": [2, 4]}
    if stage == "ms":
        result["max_vertices"], result["max_primitives"] = 128, 64
    return result


def create_catalog(path, count, richness, pretty):
    path.mkdir(parents=True)
    file = path / "index.json"
    with file.open("w", encoding="utf-8", newline="\n") as out:
        out.write("{\n")
        for i in range(count):
            if i:
                out.write(",\n")
            out.write(json.dumps(name(i)) + ":")
            out.write(json.dumps(metadata(i, richness), separators=None if pretty else (",", ":"),
                                 indent=2 if pretty else None))
        out.write("\n}\n")
    return {"name": path.name, "entries": count, "bytes": file.stat().st_size,
            "richness": richness, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}


def create_controls(directory):
    def write(rel, text):
        path = directory / rel / "index.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    family = '{"stage":"cs","fssm_sha256":"repeat","fspx_code_sha256":"same-code"}'
    write("control", '\ufeff{"a":' + family + ',"a":' + family + ',"c":35,"d":{"stage":"cs"}}')
    write("control/fspx", '{"b":' + family + "}")
    write("control/bvh", '{"never":' + family + ',"bad":[')
    write("bad-main", '{"never":' + family + '} {')
    write("non-object", "[" + family + "]")
    write("empty", "{}")
    write("replacement", '{"new":{"stage":"vs","fssm_sha256":"new-key"}}')
    write("reversed", '{"first":' + family + ',"second":' + family + "}")
    write("reversed/library", '{"third":' + family + "}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    args.directory.mkdir()
    controls = args.directory / "controls"
    create_controls(controls)
    manifests = [create_catalog(args.directory / case, count, richness, pretty)
                 for case, count, richness, pretty in (
                     ("small", 64, 1, False), ("medium", 8000, 3, True),
                     ("large", 29187, 7, True),
                 )]
    (args.directory / "manifest.json").write_text(
        json.dumps(manifests, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    for item in manifests:
        print(item["name"], item["entries"], item["bytes"], item["sha256"])


if __name__ == "__main__":
    main()
