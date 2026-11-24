"""Compare full direct-translation outputs in alternating fresh processes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess


ROOT = Path(__file__).resolve().parent
ROW = re.compile(r"(\w+) n=(\d+) mode=(\w+) dxil_bytes=(\d+) translation_ms=([0-9.]+)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--dxc-dir", type=Path,
                        default=ROOT.parent / "portbridge-xcl-925-evidence/dxc-v1.9.2602/bin/x64")
    args = parser.parse_args()
    binaries = {"base": args.base.resolve(strict=True), "candidate": args.candidate.resolve(strict=True)}
    binary_hashes = {}
    for label, binary in binaries.items():
        code = binary.read_bytes()
        assert b"phi-profile" not in code, f"Rebuild the uninstrumented {label} binary"
        binary_hashes[label] = hashlib.sha256(code).hexdigest()
    assert binary_hashes["base"] != binary_hashes["candidate"], "Build targets must remain separate"
    env = {key: value for key, value in os.environ.items() if not key.startswith("XCL_SAMPLE_")}
    env.update(
        XCL_DXC_DIR=str(args.dxc_dir.resolve(strict=True)),
        XCL_TRANSLATED_CACHE="0", XCL_NETWORK="0",
    )
    results = {"base": {}, "candidate": {}}
    identical = None
    for round_number in range(1, 8):
        order = ("base", "candidate") if round_number % 2 else ("candidate", "base")
        for label in order:
            output = ROOT / f"native-{label}.bin"
            process = subprocess.run(
                [str(binaries[label]), "--exact", "synthetic_shader_corpus", "--nocapture", "--test-threads=1"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", env=env | {"PORTBRIDGE_RND_CORPUS_OUTPUT": str(output)},
                cwd=ROOT, timeout=30,
            )
            log = ROOT / f"native-{label}-{round_number}.log"
            log.write_text(process.stdout, encoding="utf-8", newline="\n")
            if process.returncode:
                raise SystemExit(f"Translation failed, see {log}")
            rows = ROW.findall(process.stdout)
            assert len(rows) == 24, (log, rows)
            buf = output.read_bytes()
            if identical is None:
                identical = buf
            assert buf == identical, (label, round_number)
            for family, count, mode, size, elapsed in rows:
                key = (family, int(count), mode, int(size))
                results[label].setdefault(key, []).append(float(elapsed))
    rows = []
    for key, base in results["base"].items():
        other = results["candidate"][key]
        mean_before, mean_after = statistics.median(base), statistics.median(other)
        rows.append(dict(family=key[0], count=key[1], mode=key[2], dxil_bytes=key[3],
                         base_ms=mean_before, candidate_ms=mean_after, samples=[base, other]))
        print(f"{key[0]} {key[1]} {key[2]}: {mean_before:.4f} -> {mean_after:.4f} ms")
    result = dict(shader_outputs=24, paired_processes=7, binary_sha256=binary_hashes,
                  output_sha256=hashlib.sha256(identical).hexdigest(), results=rows)
    (ROOT / "native-results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
