"""Exercise the pinned DSP source pair on Windows using generated samples."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from urllib.request import urlopen

BASE = "https://raw.githubusercontent.com/LooperSalty/AnyXboxX/bebcfb104aebbcb081a2b2f2233d5c3c009a4250/third_party/victory/crates/victory-hle/src/modules/"
DONOR = "https://raw.githubusercontent.com/TaynanGT/Vice-Tay/e45051afa41b76bba1bcd0c439384b3660f93255/crates/victory-hle/src/modules/"
SOURCES = {
    "baseline": (BASE + "dsp.rs", "924b6d0acce19b9cd8c52d6416fb8cd2159e83b038af6ceed0a2d2fd7b589b37"),
    "candidate": (DONOR + "dsp.rs", "71b2f9a25b400e38c6d142fb07e603496c4d666474af41896d8ea49ad4bfe5d8"),
    "arithmetic": (DONOR + "dsp_convolve.rs", "ce8d39fa6eac8ab7142125db8159ce288f2e05413453b581fb59e449d0ae982e"),
}
TEST = "modules::dsp::portbridge_gate::host_convolution_switch_controls_in_place_submit"
TRIALS = (
    ("baseline", "1", False, 0, True),
    ("baseline", "1", True, 101, True),
    ("candidate", None, False, 0, True),
    ("candidate", "0", False, 0, True),
    ("candidate", "1", True, 0, False),
)


def pinned(group):
    url, sha = SOURCES[group]
    with urlopen(url, timeout=20) as response:
        content = response.read(32_769)
    if hashlib.sha256(content).hexdigest() != sha:
        raise ValueError(f"Wrong source bytes for {group}")
    return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rustc", type=Path, required=True, help="rustc.exe from official Windows GNU distribution")
    args = parser.parse_args()
    rustc = args.rustc.resolve(strict=True)
    linker = rustc.parent.parent / "lib/rustlib/x86_64-pc-windows-gnu/bin/rust-lld.exe"
    fixture = Path(__file__).resolve().parent
    arithmetic = pinned("arithmetic")
    rows = []
    with TemporaryDirectory(prefix="portbridge-dsp-") as scratch:
        root = Path(scratch)
        for name in ("baseline", "candidate"):
            folder = root / name
            modules = folder / "modules"
            (modules / "dsp").mkdir(parents=True)
            (folder / "harness.rs").write_bytes((fixture / "harness.rs").read_bytes())
            (modules / "dsp" / "portbridge_gate.rs").write_bytes((fixture / "portbridge_gate.rs").read_bytes())
            (modules / "dsp.rs").write_bytes(pinned(name) + b"\n#[cfg(test)]\nmod portbridge_gate;\n")
            (modules / "dsp_convolve.rs").write_bytes(arithmetic)
            subprocess.run([rustc, "--edition=2024", "--test", "-C", "opt-level=2",
                            "-A", "unused_imports", "-A", "unused_variables",
                            "-C", f"linker={linker}", "-C", "link-self-contained=yes",
                            folder / "harness.rs", "-o", root / f"{name}.exe"],
                           check=True, timeout=60)
        for name, switch, expect_wet, expected_code, targeted in TRIALS:
            env = os.environ.copy()
            if switch is None:
                env.pop("VICTORY_DSP_CONVOLUTION", None)
            else:
                env["VICTORY_DSP_CONVOLUTION"] = switch
            env["PORTBRIDGE_EXPECT_WET"] = "1" if expect_wet else "0"
            cmd = [str(root / f"{name}.exe"), "--test-threads=1", "--nocapture"]
            if targeted:
                cmd.extend(("--exact", TEST))
            run = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=15)
            observed = [line.strip() for line in run.stdout.splitlines()
                        if "test result:" in line or "first sample =" in line]
            count = "1 passed" if targeted else "10 passed"
            valid = ("sample 0: 0 vs 0.24975586" in run.stderr if expected_code else
                     any(f"ok. {count};" in line for line in observed))
            if run.returncode != expected_code or not valid:
                raise RuntimeError(f"Unexpected {name} / {switch!r}: {run.stdout}\n{run.stderr}")
            rows.append(dict(tree=name, switch=switch, expected_wet=expect_wet,
                             exit_code=run.returncode, observed=observed,
                             deliberate_negative_control=bool(expected_code)))
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
