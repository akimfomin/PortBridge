# SPDX-License-Identifier: MIT
"""Create complete and evenly sampled trace sets from public-workload captures."""

from pathlib import Path
import sys


def cases(path):
    with path.open(encoding="ascii") as stream:
        if next(stream).strip() != "PBTRACE1 64":
            raise ValueError("unexpected trace header")
        for line in stream:
            tag, name, extent, cap = line.split()
            if tag != "case" or extent != cap:
                raise ValueError("expected a natural uncapped capture")
            groups = []
            prefix = []
            chunk = None
            for row in stream:
                row = row.rstrip("\r\n")
                if row.startswith("allow "):
                    prefix.append(row)
                elif row.startswith("frame ") and chunk is None:
                    chunk = [row]
                elif row.startswith("dirty ") and chunk is not None:
                    chunk.append(row)
                elif row == "endframe" and chunk is not None:
                    groups.append([*chunk, row])
                    chunk = None
                elif row == "endcase" and chunk is None and groups:
                    break
                else:
                    raise ValueError("malformed capture")
            else:
                raise ValueError("missing case end")
            yield name, int(extent), prefix, groups


def write(destination, collection):
    with destination.open("w", encoding="ascii", newline="\n") as f:
        f.write("PBTRACE1 64\n")
        for name, extent, cap, prefix, groups in collection:
            f.write(f"case {name} {extent} {cap}\n")
            f.write("\n".join(prefix) + "\n")
            for group in groups:
                f.write("\n".join(group) + "\n")
            f.write("endcase\n")


def main():
    imgui, fox, output = (Path(arg) for arg in sys.argv[1:])
    collection = []
    for path in (imgui, fox):
        for name, extent, prefix, groups in cases(path):
            collection.append((name + "_native", extent, extent, prefix, groups))
            for label, cap in (("64k", 1024), ("4k", 64)):
                if extent > cap:
                    collection.append((name + "_" + label, extent, cap, prefix, groups))
    write(output / "open-all.pbtrace", collection)
    print("\n".join(f"{name} extent={extent} cap={cap} frames={len(groups)}"
                    for name, extent, cap, _, groups in collection))


if __name__ == "__main__":
    main()
