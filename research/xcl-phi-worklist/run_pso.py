"""Compare time to a real D3D12 pipeline and verify synthetic shader readback."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
READY = re.compile(r"PSO ready in ([0-9.]+) ms")
TEST = "console_wave64_compute_through_the_pso_hook_dispatch_and_read_back"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--dxc-dir", type=Path,
                        default=ROOT.parent / "portbridge-xcl-925-evidence/dxc-v1.9.2602/bin/x64")
    parser.add_argument("--adapter", default="RTX 4070")
    args = parser.parse_args()
    binaries = {"base": args.base.resolve(strict=True), "candidate": args.candidate.resolve(strict=True)}
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in binaries.items()}
    assert hashes["base"] != hashes["candidate"]
    env = {key: value for key, value in os.environ.items() if not key.startswith("XCL_")}
    env.update(
        XCL_ADAPTER=args.adapter, XCL_DXC_DIR=str(args.dxc_dir.resolve(strict=True)),
        XCL_NETWORK="0", XCL_DIRECT_DXIL="all", XCL_DIRECT_DXIL_STATS="1",
        XCL_PSO_DISK_CACHE="0", XCL_TRANSLATED_CACHE="0", XCL_PER_LANE="0",
    )
    cache = Path(tempfile.mkdtemp(prefix="pso-cold-", dir=ROOT))
    logs = ROOT / "pso-logs"
    logs.mkdir(exist_ok=True)
    results = {}
    for loops in (8, 32, 128):
        samples = {name: [] for name in binaries}
        for pair in range(9):
            order = ("base", "candidate") if pair % 2 == 0 else ("candidate", "base")
            for name in order:
                log = logs / f"{loops}-{name}-{pair}.log"
                isolated = cache / log.stem
                proc = subprocess.run(
                    [str(binaries[name]), "--exact", TEST, "--nocapture", "--test-threads=1"],
                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                    env=env | {"PORTBRIDGE_RND_PSO_LOOPS": str(loops),
                               "XCL_DXIL_CACHE": str(isolated / "dxil"), "XCL_PSO_CACHE": str(isolated / "pso")},
                    timeout=30,
                )
                output = proc.stdout + proc.stderr
                log.write_text(output, encoding="utf-8", newline="\n")
                match = READY.search(output)
                verified = (f"verified readback: 1536 dwords (loops={loops})" in output
                            and "CS direct 1 / HLSL fallback 0;" in output
                            and args.adapter.lower() in output.lower())
                if proc.returncode or match is None or not verified:
                    raise SystemExit(f"GPU readback or direct translation failed, see {log}")
                samples[name].append(float(match.group(1)))
        medians = {name: statistics.median(values) for name, values in samples.items()}
        deltas = [n - b for b, n in zip(samples["base"], samples["candidate"])]
        results[loops] = dict(samples_ms=samples, median_ms=medians, paired_delta_ms=statistics.median(deltas))
        print(f'{loops} loops: {medians["base"]:.4f} -> {medians["candidate"]:.4f} ms, '
              f'paired difference {statistics.median(deltas):+.4f} ms', flush=True)
    (ROOT / "pso-results.json").write_text(
        json.dumps(dict(adapter=args.adapter, binary_sha256=hashes, results=results), indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )


if __name__ == "__main__":
    main()
