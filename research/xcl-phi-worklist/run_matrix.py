"""Pair and repeat the XCL production-module CPU benchmark."""

import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess


SIZES = (128, 512, 2048, 8192, 16384)
SHAPES = ("reverse", "after-cse", "forward", "persistent")
TIMINGS = re.compile(r"times=(\[.*\])")


def main():
    root = Path(__file__).resolve().parent
    summaries = []
    for shape in SHAPES:
        for count in SIZES:
            samples = {"base": [], "candidate": []}
            outputs = {}
            for round_number in range(3):
                order = ("base", "candidate") if round_number % 2 == 0 else ("candidate", "base")
                for build in order:
                    binary = root / build / "phi_bench.exe"
                    output = root / build / f"{shape}-{count}.bc"
                    run = subprocess.run(
                        [str(binary), shape, str(count), "3", str(output)],
                        check=True, capture_output=True, text=True, timeout=25,
                    )
                    match = TIMINGS.search(run.stdout)
                    if match is None:
                        raise ValueError(run.stdout)
                    samples[build].extend(json.loads(match.group(1)))
                    content = output.read_bytes()
                    if build in outputs:
                        assert outputs[build] == content
                    else:
                        outputs[build] = content
            assert outputs["base"] == outputs["candidate"], (shape, count)
            summary = {
                "shape": shape,
                "phi_count": count,
                "base_ms": statistics.median(samples["base"]),
                "candidate_ms": statistics.median(samples["candidate"]),
                "samples_ms": samples,
                "output_sha256": hashlib.sha256(outputs["base"]).hexdigest(),
            }
            print(f"{shape:>10} {count:5}: {summary['base_ms']:.4f} -> {summary['candidate_ms']:.4f} ms", flush=True)
            summaries.append(summary)
    (root / "results.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
