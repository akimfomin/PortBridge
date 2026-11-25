# SPDX-License-Identifier: MIT
"""Produce the measured report from the isolated XCL fixture capture."""

import argparse
import hashlib
import json
from pathlib import Path
import re

from dxil_transport import Listing, SHUFFLE, inspect_dxil


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def detect_controls(native, split):
    native_ir = Listing(native)
    native_call = next(re.fullmatch(SHUFFLE, expr) for expr, _, _ in native_ir.defs.values()
                       if re.fullmatch(SHUFFLE, expr))
    native_or = native_call.group(2)
    native_half = native_ir.defs[native_or][0].split()[2].rstrip(",")
    base_pattern = rf"(?m)^\s*{re.escape(native_half)} = and i32 (%\d+), 32$"
    dropped, count = re.subn(base_pattern, rf"  {native_half} = and i32 \g<1>, 0", native)
    if count != 1:
        raise ValueError("native negative control did not bind exactly one shared half base")

    split_ir = Listing(split)
    split_call = next(re.fullmatch(SHUFFLE, expr) for expr, _, _ in split_ir.defs.values()
                      if re.fullmatch(SHUFFLE, expr))
    physical = split_call.group(2)
    logical = split_ir.defs[physical][0].split()[2].rstrip(",")
    bank_pattern = rf"(?m)^(\s*%\d+ = icmp uge i32 ){re.escape(logical)}(, 32)$"
    wrong, count = re.subn(bank_pattern, rf"\g<1>{physical}\g<2>", split)
    if count != 1:
        raise ValueError("split negative control did not bind exactly one source EXEC bank")

    native_results = inspect_dxil(dropped, 64)
    split_results = inspect_dxil(wrong, 32)
    if len(native_results) != 4 or any(row["checks"]["superset"]["status"] != "refuted" for row in native_results):
        raise ValueError("native wrong-half control must refute all four reads")
    if sum(row["status"] == "unmodeled" for row in split_results) != 1:
        raise ValueError("split wrong-EXEC-bank control must be outside the model")
    return {"native_half_base_removed": native_results, "split_exec_bank_uses_physical_index": split_results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--validator-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive_hash = digest(args.archive)
    if archive_hash != "9e4184f43d41338b04c3981f16f7b0242adb8dea84af449ad0eb0b7b6bac6dd0":
        raise ValueError("expected the pinned GitHub source archive")
    validator_log = args.validator_log.read_text(encoding="utf-8")
    validator = re.search(r"(?m)^PortBridge fixture DXIL validator (\d+)\.(\d+)\s*$", validator_log)
    dxc = re.search(r"(?m)^xcl: DXC: (.+?), from ", validator_log)
    if not validator or tuple(map(int, validator.groups())) < (1, 8) or "SKIPPED" in validator_log:
        raise ValueError("expected captured test log showing a supported DXIL validator")
    if dxc is None or "1 passed; 0 failed" not in validator_log:
        raise ValueError("expected successful capture test")

    report = {
        "xcl_commit": "7e1b659cfcd95c37d8710c85adb3753847455575",
        "source_archive_sha256": archive_hash,
        "dxc_version": dxc.group(1),
        "validator_version": ".".join(validator.groups()),
        "gpu_executed": False,
        "capture_hook_sha256": digest(Path(__file__).with_name("capture-hook.rs")),
        "captures": {},
    }
    listings = []
    for mode, physical in (("native64", 64), ("split32", 32)):
        disassembly_path = args.capture / f"{mode}.ll"
        binary_path = args.capture / f"{mode}.dxil"
        listing = disassembly_path.read_text(encoding="utf-8")
        rows = inspect_dxil(listing, physical)
        expected = [(1, 0, 10, 0), (2, 0, 11, 4), (1, 0, 12, 128), (4, 0, 16, 0)]
        fields = ("address_vgpr", "data_vgpr", "destination_vgpr", "offset")
        if [tuple(row.get(field) for field in fields) for row in rows] != expected:
            raise ValueError(f"unexpected output fixture for {mode}")
        if [row["guest_exec"]["kind"] for row in rows] != ["input-u0"] * 3 + ["literal"]:
            raise ValueError(f"unexpected guest EXEC bindings for {mode}")
        if any(row["checks"]["superset"]["status"] != "passes modeled domain" or
               row["checks"]["independent"]["status"] != "refuted" for row in rows):
            raise ValueError(f"unexpected translation contract for {mode}")
        listings.append(listing)
        report["captures"][mode] = {
            "binary_sha256": digest(binary_path),
            "disassembly_sha256": digest(disassembly_path),
            "validated_in_capture_test": True,
            "transports": rows,
        }
    report["in_memory_disassembly_controls"] = detect_controls(*listings)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("8 supported emitted transports, 4 refuted native mutation slices, 1 rejected split mutation slice")


if __name__ == "__main__":
    main()
