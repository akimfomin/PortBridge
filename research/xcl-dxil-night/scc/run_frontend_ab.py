"""Compile and validate synthetic scalar rings in the exact XCL CLI, without GPU work."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess


ROOT = Path(__file__).resolve().parent
BUILD = runpy.run_path(str(ROOT / "build_proof.py"))
SCALAR = runpy.run_path(str(ROOT / "check_scalar.py"))
COMPUTE_RECORD = runpy.run_path(str(ROOT / "wrap_scalar_ring.py"))["compute_record"]
CASES = {f"{prefix}{width}": (width, seeds)
         for prefix, seeds in [("one-seed", 1), ("two-seeds", 2)]
         for width in [2, 16, 64]}
FLAGS = ["--direct", "--sample", "0", "--threads", "1", "--windows", "1", "--split", "0",
         "--max-bytes", "2048", "--timeout", "2", "--validate", "--trace"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(args, cwd, log, *, env=None, timeout=8):
    try:
        result = subprocess.run(args, cwd=cwd, env=env, timeout=timeout, capture_output=True)
    except subprocess.TimeoutExpired as error:
        log.write_bytes((error.stdout or b"") + (error.stderr or b""))
        raise RuntimeError(f"Timed out after {timeout}s: {args[0]}. See {log}") from error
    output = result.stdout.decode("utf-8", errors="replace")
    errors = result.stderr.decode("utf-8", errors="replace")
    log.write_text(output + errors, encoding="utf-8")
    require(result.returncode == 0, f"Exit {result.returncode} from {args[0]}. See {log}")
    return output + errors


def build_records(output):
    raw = output / "raw"
    records = output / "records"
    raw.mkdir()
    records.mkdir()
    exe = output / "scalar_ring.exe"
    rustc = BUILD["RUSTC"]
    linker = BUILD["LINKER"]
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(linker.parent), str(rustc.parent), env["PATH"]])
    args = [str(rustc), "--edition", "2024", "-D", "warnings", "-C", f"linker={linker}",
            "-o", str(exe), str(ROOT / "scalar_ring.rs")]
    run(args, output, output / "scalar-build.log", env=env, timeout=20)
    run([str(exe), str(raw)], output, output / "scalar-generate.log", timeout=10)
    fixtures = {}
    for name in CASES:
        code = (raw / f"{name}.rdna2").read_bytes()
        require(len(code) <= 2048, f"Fixture too large: {name}")
        record = COMPUTE_RECORD(code)
        old = ROOT / "scalar-records" / f"{name}.bin"
        if old.exists():
            require(record == old.read_bytes(), f"Earlier record changed: {name}")
        (records / f"{name}.bin").write_bytes(record)
        record_hash = SCALAR["fnv64"](record)
        fixtures[name] = {"code_sha256": sha(code), "record_sha256": sha(record),
                          "code_bytes": len(code), "dump": f"{record_hash:016x}_f0_308"}
    return fixtures


def inspect_arm(arm, records, raw, fixtures):
    dxv = str(BUILD["DXV"])
    dxc = str(SCALAR["DXC"])
    expected = {f"{f['dump']}.direct.dxil" for f in fixtures.values()}
    require({p.name for p in arm.glob("*.direct.dxil")} == expected, f"Missing or extra DXIL in {arm}")
    require(len(list(records.glob("*.bin"))) == len(fixtures), "Record count changed")
    rows = {}
    for name, fixture in fixtures.items():
        stem = fixture["dump"]
        blob = arm / f"{stem}.direct.dxil"
        guest = arm / f"{stem}.guest.bin"
        require(guest.read_bytes() == (raw / f"{name}.rdna2").read_bytes(), f"Guest mismatch: {guest}")
        validation = run([dxv, str(blob)], arm, arm / f"{name}.dxv.log")
        require("validation succeeded" in validation.lower(), f"DXV did not confirm {blob}")
        asm = run([dxc, "-dumpbin", str(blob)], arm, arm / f"{name}.ll")
        phis = SCALAR["phi_graph"](asm)
        seeds = SCALAR["ring_seeds"](phis, CASES[name][0])
        payload = blob.read_bytes()
        rows[name] = {"dxil_bytes": len(payload), "dxil_sha256": sha(payload), "phi_count": len(phis),
                      "ring_seeds": sorted(seeds) if seeds is not None else None}
    return rows


def compare(output, control, candidate):
    checks = {}
    for name, (width, seeds) in CASES.items():
        base = control[name]
        trial = candidate[name]
        before = base["ring_seeds"]
        after = trial["ring_seeds"]
        phi_delta = base["phi_count"] - trial["phi_count"]
        byte_delta = base["dxil_bytes"] - trial["dxil_bytes"]
        unchanged = base["dxil_sha256"] == trial["dxil_sha256"]
        if seeds == 1:
            passes = before is not None and len(before) == 1 and after is None and phi_delta == width and byte_delta > 0
        else:
            passes = before is not None and len(before) == 2 and before == after and unchanged
        checks[name] = {"passes": passes, "phi_removed": phi_delta, "bytes_removed": byte_delta,
                        "byte_identical": unchanged, "control": base, "candidate": trial}
    (output / "results.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(checks, indent=2))
    require(all(case["passes"] for case in checks.values()), "Unexpected ring or size result. See results.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True, help="Fresh SCC candidate xcl.exe")
    parser.add_argument("--output", type=Path, required=True, help="New directory for results")
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    output = args.output.resolve()
    image = binary.read_bytes()
    require(b"phi-scc" in image, "Use the SCC candidate binary, which contains the phi-scc option")
    checkout = BUILD["CHECKOUT"]
    head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True, timeout=8).strip()
    require(head == BUILD["REV"], f"Unexpected checkout HEAD: {head}")
    output.mkdir()
    fixtures = build_records(output)
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("XCL_")}
    common = {"XCL_DXC_DIR": str(BUILD["DXV"].parent), "XCL_NETWORK": "0", "XCL_TRANSLATED_CACHE": "0"}
    records = output / "records"
    prefix = [str(binary), "shaders", str(records), *FLAGS]
    arms = {"control": {"XCL_DXIL_NO_OPT": "phi-scc"}, "candidate": {}}
    manifest = {"head": head, "binary_sha256": sha(image), "common_xcl_env": common, "fixtures": fixtures,
                "optimizer_sha256": sha((checkout / BUILD["DXIL"] / "module/opt.rs").read_bytes()),
                "dxv_sha256": sha(BUILD["DXV"].read_bytes()), "dxc_sha256": sha(SCALAR["DXC"].read_bytes()),
                "arms": {}}
    for arm, overrides in arms.items():
        manifest["arms"][arm] = {"args": [*prefix, "--dump", str(output / arm)], "env_overrides": overrides}
    (output / "reproduction.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    rows = {}
    for arm, run_info in manifest["arms"].items():
        destination = output / arm
        destination.mkdir()
        log = output / f"{arm}-xcl.log"
        run(run_info["args"], output, log, env={**env, **common, **run_info["env_overrides"]}, timeout=20)
        rows[arm] = inspect_arm(destination, records, output / "raw", fixtures)
    require(sha(binary.read_bytes()) == manifest["binary_sha256"], "CLI file changed between arms")
    compare(output, rows["control"], rows["candidate"])


if __name__ == "__main__":
    main()
