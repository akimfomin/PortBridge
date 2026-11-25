#!/usr/bin/env python3
"""Adapt the attributed #51 blend helper to AnyXboxX's pinned lot 9, then extract descriptor expressions."""

from pathlib import Path
import re
import subprocess

PIN = "130bf10e1c70278a50ea828954a0e52acde1730a"
HOST = "crates/victory-gpu/src/pipeline/host.rs"
PROOF = Path(__file__).resolve().parent
CHECKOUT = PROOF.parent


def only_replace(text: str, old: str, new: str, count: int) -> str:
    if text.count(old) != count:
        raise ValueError(f"expected {count} matches for {old!r}")
    return text.replace(old, new)


def between(text: str, start: str, end: str) -> str:
    first = text.index(start)
    return text[first : text.index(end, first + len(start))]


def helper(diff: str) -> str:
    raw = between(diff, "+/// Integer render target formats", "\n impl GraphicsState {")
    lines = raw.splitlines()
    if any(not line.startswith("+") for line in lines):
        raise ValueError("the helper must come entirely from added lines")
    return "\n".join(line[1:] for line in lines) + "\n"


def extract(host_source: str, candidate: bool) -> str:
    graphics = between(host_source, "impl HostPipeline {", "fn stream_pipeline<S>(")
    depth = between(host_source, "fn graphics_depth_bounds_pipeline(", "fn mesh_pipeline(")
    mesh = between(host_source, "fn mesh_pipeline(", "fn root_signature(")
    (ordinary,) = re.findall(r"^\s*BlendState: (.+),$", graphics, re.MULTILINE)
    legacy_mesh, depth_mesh = re.findall(r"blend: Sub\(D3D12_PIPELINE_STATE_SUBOBJECT_TYPE_BLEND, (.+)\),", mesh)
    (depth_input,) = re.findall(r"blend: Sub\(D3D12_PIPELINE_STATE_SUBOBJECT_TYPE_BLEND, (.+)\),", depth)
    if depth_input != "d.BlendState":
        raise ValueError("depth-bounds graphics no longer forwards the prepared descriptor")
    if candidate and len({ordinary, legacy_mesh, depth_mesh}) != 1:
        raise ValueError("graphics and both mesh streams must use the same normalizer")
    functions = {
        "graphics": ordinary,
        "mesh_legacy_depth": legacy_mesh,
        "mesh_depth_bounds": depth_mesh,
    }
    out = between(host_source, "/// Integer render target formats", "impl GraphicsState {") if candidate else ""
    for name, expression in functions.items():
        out += f"fn {name}(g: &GraphicsState) -> D3D12_BLEND_DESC {{ {expression} }}\n"
    out += (
        "fn graphics_depth_bounds(g: &GraphicsState) -> D3D12_BLEND_DESC {\n"
        "    let d = D3D12_GRAPHICS_PIPELINE_STATE_DESC { BlendState: graphics(g), ..Default::default() };\n"
        f"    {depth_input}\n"
        "}\n"
    )
    return out


def main() -> None:
    head = subprocess.check_output(["git", "-C", str(CHECKOUT), "rev-parse", "HEAD"], text=True, timeout=10).strip()
    if head != PIN:
        raise ValueError(f"expected {PIN}, got {head}")
    baseline = subprocess.check_output(
        ["git", "-C", str(CHECKOUT), "show", f"{PIN}:{HOST}"], text=True, encoding="utf-8", timeout=10
    )
    authored = helper((PROOF / "upstream-1152.diff").read_text(encoding="utf-8"))
    attributed_port = helper((PROOF / "fork-51.diff").read_text(encoding="utf-8"))
    if authored != attributed_port:
        raise ValueError("upstream and fork helper texts differ")
    prod, tail = baseline.split("#[cfg(test)]\nmod tests {", 1)
    prod = only_replace(prod, "\nimpl GraphicsState {", "\n" + attributed_port + "impl GraphicsState {", 1)
    prod = only_replace(prod, "BlendState: g.blend,", "BlendState: host_blend(&g.blend, &g.targets),", 1)
    prod = only_replace(
        prod,
        "blend: Sub(D3D12_PIPELINE_STATE_SUBOBJECT_TYPE_BLEND, g.blend),",
        "blend: Sub(D3D12_PIPELINE_STATE_SUBOBJECT_TYPE_BLEND, host_blend(&g.blend, &g.targets)),",
        2,
    )
    candidate = prod + "#[cfg(test)]\nmod tests {" + tail
    file = CHECKOUT / HOST
    if file.read_text(encoding="utf-8") not in (baseline, candidate):
        raise ValueError("refusing to overwrite an unexpected host.rs")
    file.write_text(candidate, encoding="utf-8", newline="\n")
    fixture = (PROOF / "fixture.rs").read_text(encoding="utf-8")
    for arm, source in (("baseline", baseline), ("candidate", candidate)):
        out = PROOF / "ab" / arm
        out.mkdir(parents=True, exist_ok=True)
        (out / "fixture.rs").write_text(fixture, encoding="utf-8")
        (out / "host_blend.rs").write_text(extract(source, arm == "candidate"), encoding="utf-8")


if __name__ == "__main__":
    main()
