"""Check the generated numeric cases and benchmark balanced loader orders."""

import argparse
from hashlib import sha256
from itertools import permutations
import json
from pathlib import Path
from runpy import run_path
import subprocess


HERE = Path(__file__).resolve().parent
ARMS = ("stock", "bounded", "composed")


def numbers(output):
    tokens = list(run_path(str(HERE / "number_cases.py"))["tokens"]())
    fixture = ("\n".join(tokens) + "\n").encode("ascii")
    expected = json.loads((HERE / "verified-numbers.json").read_text(encoding="utf-8"))
    if len(tokens) != expected["parser_cases"] or sha256(fixture).hexdigest() != expected["input"]:
        raise ValueError("numeric fixture identity changed")
    reference = expected["result_by_variant"]["bounded"]
    for arm in ARMS:
        data = subprocess.run([output / arm / "number.exe"], input=fixture,
                              capture_output=True, check=True, timeout=15).stdout
        if len(data.splitlines()) != len(tokens) or sha256(data).hexdigest() != reference:
            raise ValueError(f"{arm} parsed at least one number differently")
    print(f"All {len(tokens)} number results agree in all three arms", flush=True)


def measure(output):
    module = run_path(str(HERE / "measure_index.py"))
    sample, headroom, comparison = (module[name] for name in ("sample", "headroom", "comparison"))
    fixtures = output / "fixtures"
    binaries = {arm: output / arm / "load.exe" for arm in ARMS}
    result = {"binaries": {arm: sha256(path.read_bytes()).hexdigest() for arm, path in binaries.items()},
              "fixtures": [], "status": "in_progress"}

    def run(arm, folder, fixture):
        commit, physical = headroom()
        if commit < 3 or physical < 6:
            raise ValueError(f"admission refused with {commit:.2f} GiB commit and {physical:.2f} GiB RAM")
        return {**sample(binaries[arm], folder, fixture), "admission_commit_gib": commit,
                "admission_physical_gib": physical}

    with (output / "three-arm-replay.json").open("x", encoding="utf-8", newline="\n") as log:
        def checkpoint():
            log.seek(0)
            json.dump(result, log, indent=2)
            log.write("\n")
            log.truncate()
            log.flush()

        try:
            for fixture in json.loads((fixtures / "manifest.json").read_text(encoding="utf-8")):
                folder = fixtures / fixture["name"]
                if sha256((folder / "index.json").read_bytes()).hexdigest() != fixture["sha256"]:
                    raise ValueError(f"unexpected fixture bytes: {fixture['name']}")
                row = {**fixture, "warmup": {}, "pairs": []}
                result["fixtures"].append(row)
                for arm in ARMS:
                    row["warmup"][arm] = run(arm, folder, fixture)
                for order in permutations(ARMS):
                    samples = {}
                    row["pairs"].append({"order": order, "samples": samples})
                    for arm in order:
                        samples[arm] = run(arm, folder, fixture)
                row["bounded_over_stock"] = comparison(row["pairs"], "stock", "bounded")
                row["composed_over_bounded"] = comparison(row["pairs"], "bounded", "composed")
                row["composed_over_stock"] = comparison(row["pairs"], "stock", "composed")
                checkpoint()
        except Exception as error:
            result.update(status="stopped", error=str(error))
            checkpoint()
            raise
        result["status"] = "complete"
        checkpoint()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--measure", action="store_true")
    args = parser.parse_args()
    root = args.output.resolve(strict=True)
    numbers(root)
    if args.measure:
        measure(root)
