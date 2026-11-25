"""Compare XCL compiler variants on a pinned public synthetic generator."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess


ROOT = Path(__file__).resolve().parent
CASES = re.compile(r"\b(\w+/\d+/\w+): (\d+) source bytes, (\d+) DXIL bytes, median_ms=(\d+\.\d+)$", re.M)
DEFAULT_VARIANTS = ("baseline", "dominators", "phi", "combined")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--variants", nargs="+", default=DEFAULT_VARIANTS,
                        choices=(*DEFAULT_VARIANTS, "compact"))
    parser.add_argument("--result", type=Path, default=ROOT / "campaign-results.json")
    parser.add_argument("--dxc", type=Path,
                        default=ROOT.parent / "portbridge-xcl-925-evidence/dxc-v1.9.2602/bin/x64")
    args = parser.parse_args()
    variants = tuple(args.variants)
    assert args.rounds >= len(variants)
    assert len(set(variants)) == len(variants) >= 2
    binaries = {label: (ROOT / f"campaign-{label}.exe").resolve(strict=True) for label in variants}
    hashes = {label: hashlib.sha256(path.read_bytes()).hexdigest() for label, path in binaries.items()}
    assert len(set(hashes.values())) == len(variants)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("XCL_", "PB_CFG_"))}
    env.update(XCL_DXC_DIR=str(args.dxc.resolve(strict=True)), XCL_NETWORK="0")
    logs = args.result.resolve().with_name(args.result.stem + "-logs")
    logs.mkdir(exist_ok=True)
    expected = None
    cases = {}
    for round_index in range(-1, args.rounds):
        rotate = round_index % len(variants)
        names = variants[rotate:] + variants[:rotate]
        if (round_index // len(variants)) % 2:
            names = tuple(reversed(names))
        for name in names:
            result = logs / f"{name}.bin"
            run_env = env | {"PB_CFG_OUTPUT": str(result)}
            if round_index == -1:
                run_env["PB_CFG_VALIDATE"] = "1"
            command = [str(binaries[name]), "--exact", "campaign_compile_corpus", "--nocapture", "--test-threads=1"]
            proc = subprocess.run(command, cwd=ROOT, timeout=90, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", env=run_env)
            log = logs / f"{name}-{round_index + 1}.log"
            stdout = proc.stdout + proc.stderr
            log.write_text(stdout, encoding="utf-8", newline="\n")
            matches = CASES.findall(stdout)
            assert proc.returncode == 0 and len(matches) == 24, log
            contents = result.read_bytes()
            if expected is None:
                expected = contents
            assert expected == contents, (name, round_index, log)
            if round_index != -1:
                for shape, input_bytes, output_bytes, duration in matches:
                    key = (shape, int(input_bytes), int(output_bytes))
                    cases.setdefault(key, {label: [] for label in variants})[name].append(float(duration))

    rows = []
    for (shape, inp, out), values in cases.items():
        assert all(len(times) == args.rounds for times in values.values())
        medians = {name: statistics.median(times) for name, times in values.items()}
        print(shape, " ".join(f"{name}={value:.4f}ms" for name, value in medians.items()))
        rows.append(dict(shape=shape, input_bytes=inp, dxil_bytes=out, medians_ms=medians, samples_ms=values))
    data = dict(generator_sha="e3806688e4d9e4fb4be9f49369fe8f5b184f8b6c",
                binary_sha256=hashes, output_sha256=hashlib.sha256(expected).hexdigest(),
                rounds=args.rounds, cases=rows)
    args.result.write_text(json.dumps(data, indent=2)+"\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
