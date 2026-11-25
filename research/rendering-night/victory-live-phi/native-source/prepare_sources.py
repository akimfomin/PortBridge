# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare the pinned VIctory compute harness and embed the eight verified DXIL files."""

import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
PROOF = HERE.parent
REPO = PROOF.parent
REV = "758bf7fbc6a35403028c4410ec94a5738b96bc29"
RESULT_SHA = "d2a795d00085aaef9c32a02012dbab3d41072fba8db09ef548625afd5b71129e"


def part(source, start, end):
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


def prepare_host():
    raw = subprocess.check_output(["git", "-C", str(REPO), "show",
                                   f"{REV}:crates/victory-shader/src/emit/host.rs"], timeout=5)
    source = raw.decode("utf-8")
    init = part(source, "fn err(e:", "    /// The root signature translated shaders expect:")
    pipe = part(source, "    /// The root signature for these stages:", "    /// A graphics pipeline from")
    root = part(source, "pub enum Root {", "/// Bindings for [`Host::draw`]")
    dispatch = source[source.index("fn transition("):].replace("#[cfg(test)]\n", "")
    wait = "            while fence.GetCompletedValue() < 1 {\n"
    assert dispatch.count(wait) == 1
    dispatch = dispatch.replace(wait, """            // Abort the worker without releasing in-flight resources if this wait stalls.
            let deadline = std::time::Instant::now() + std::time::Duration::from_secs(3);
            while fence.GetCompletedValue() < 1 {
                if std::time::Instant::now() >= deadline {
                    eprintln!("VIctory readback fence did not complete in 3 seconds");
                    std::process::exit(124);
                }
""")
    dispatch = dispatch.replace("            let mut out = Vec::new();\n", """            dev.GetDeviceRemovedReason().map_err(err)?;
            let mut out = Vec::new();
""")
    header = """// SPDX-License-Identifier: GPL-3.0-or-later
// Generated from VIctory #1716 (758bf7f). This extracts its compute-only test harness.
use super::HostShader;
use windows::Win32::Graphics::Direct3D::*;
use windows::Win32::Graphics::Direct3D12::*;
use windows::Win32::Graphics::Dxgi::Common::*;
use windows::Win32::Graphics::Dxgi::*;
use windows::core::Interface;

pub struct Host { pub device: ID3D12Device }

"""
    (HERE / "host_slice.rs").write_text(header + init + pipe + "}\n\n" + root + dispatch, encoding="utf-8")


def prepare_cases():
    result = (PROOF / "paired2/results.json").read_bytes()
    assert hashlib.sha256(result).hexdigest() == RESULT_SHA, "Unexpected CPU evidence manifest"
    metadata = json.loads(result)
    lines = ["const CASES: [Case; 8] = ["]
    for width in (2, 16):
        for seeds in (1, 2):
            name = f"{width}-regs-{seeds}-seeds"
            for arm in ("control", "candidate"):
                relative = f"../paired2/{arm}/{name}.dxil"
                data = (HERE / relative).read_bytes()
                row = metadata[name][arm]
                assert len(data) == row["bytes"] <= 2650 and hashlib.sha256(data).hexdigest() == row["sha256"]
                lines.append(f'    Case {{ arm: "{arm}", width: {width}, seeds: {seeds}, '
                             f'dxil: include_bytes!("{relative}") }},')
    lines.append("];")
    (HERE / "case_table.rs").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    prepare_cases()
    prepare_host()
