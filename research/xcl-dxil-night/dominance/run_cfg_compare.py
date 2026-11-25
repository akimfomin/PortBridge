"""Run native XCL paired compilation with identical generated inputs."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
SAMPLE = re.compile(r"\b(\w+/\d+): (\d+) source instructions, (\d+) DXIL bytes, median_ms=(\d+\.\d+)$", re.M)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "portbridge-night-xcl-control.exe")
    parser.add_argument("--candidate", type=Path, default=ROOT / "portbridge-night-xcl.exe")
    parser.add_argument("--result", type=Path, default=ROOT / "cfg-native-results.json")
    parser.add_argument("--dxc", type=Path,
                        default=ROOT.parent / "portbridge-xcl-925-evidence/dxc-v1.9.2602/bin/x64")
    parser.add_argument("--pairs", type=int, default=9)
    args = parser.parse_args()
    assert args.pairs >= 3
    bins = {name: getattr(args, name).resolve(strict=True) for name in ("baseline", "candidate")}
    hashes = {label: hashlib.sha256(binary.read_bytes()).hexdigest() for label, binary in bins.items()}
    assert len(set(hashes.values())) == 2
    env = {k: v for k, v in os.environ.items() if not k.startswith(("XCL_", "PB_CFG_"))}
    env.update(XCL_DXC_DIR=str(args.dxc.resolve(strict=True)), XCL_NETWORK="0")
    logs = args.result.resolve().with_name(args.result.stem + "-logs")
    logs.mkdir(exist_ok=True)
    expected = None
    runs = {}
    for pair in range(1, args.pairs + 1):
        for label in (list(bins) if pair % 2 else list(reversed(bins))):
            result_path = logs / f"{label}.bin"
            command = [str(bins[label]), "--exact", "cfg_compile_corpus", "--nocapture", "--test-threads=1"]
            proc = subprocess.run(command, cwd=ROOT, timeout=45, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  env=env | {"PB_CFG_OUTPUT": str(result_path)})
            out = proc.stdout + proc.stderr
            log = logs / f"{label}-{pair}.log"
            log.write_text(out, encoding="utf-8", newline="\n")
            found = SAMPLE.findall(out)
            assert proc.returncode == 0 and len(found) == 9, log
            blob = result_path.read_bytes()
            if expected is None:
                expected = blob
            assert blob == expected, (label, pair)
            for name, inst, size, timing in found:
                key = (name, int(inst), int(size))
                runs.setdefault(key, {k: [] for k in bins})[label].append(float(timing))

    cases = []
    for (name, inst, size), samples in runs.items():
        base, candidate = (samples[k] for k in bins)
        cases.append(dict(case=name, instructions=inst, dxil_bytes=size, samples_ms=samples,
                          baseline_ms=statistics.median(base), candidate_ms=statistics.median(candidate),
                          paired_delta_ms=statistics.median(n - b for n, b in zip(candidate, base))))
    with args.result.open("w", encoding="utf-8", newline="\n") as out:
        json.dump(dict(binary_sha256=hashes, dxil_sha256=hashlib.sha256(expected).hexdigest(),
                       process_pairs=args.pairs, cases=cases), out, indent=2)
        out.write("\n")
    fields = ["case", "instructions", "dxil_bytes", "baseline_ms", "candidate_ms", "paired_delta_ms"]
    writer = csv.DictWriter(sys.stdout, fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(cases)


if __name__ == "__main__":
    main()
