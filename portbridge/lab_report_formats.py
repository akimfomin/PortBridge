"""Structured report contracts for the curated Test Lab and legacy FrameLab evidence."""

import re

from .tester_discovery import report_lines


FRAMELAB_TASK = "framelab-12-vulkan-handoff"
FRAMELAB_TESTER_ID = 71070620
FRAMELAB_REVISION = "82f069e82197e61b97f60bbcbcb7a3af7d3f8e77"
FRAMELAB_DISCUSSION = "https://github.com/5headsmartbtw/leonida-framelab/issues/15"
GPU_VENDORS = {"amd": "1002", "nvidia": "10de", "intel": "8086"}
# The case IDs are part of the report interface. Keep them stable when editing card wording.
REPORT_POLICIES = {
    "pb-9-continued-first-frame": ("vulkan", ("eager-pixels", "deferred-pixels")),
    "pb-5-xcl-wave64": ("d3d12-wave64", ("native-adapter", "byte-carry-low", "byte-carry-high")),
    "pb-9-reforge-present": ("vulkan", ("six-scenarios", "eight-frames-drained", "ninth-present-refused")),
    "xcl-1100-fma": ("d3d12-wave64", ("native-adapter", "fma-values")),
    "pb-4-d16": ("cpu", ("baseline-13", "seven-negative-controls", "fixed-15")),
    "anyxboxx-133-native-carry": ("hip-wave32", ("initial-exec", "e32-carry-mask", "e64-carry-mask")),
    "anyxboxx-133-native-fma": ("hip-wave32", ("positive-down", "positive-up", "negative", "exact-tie")),
    "continued-511-repeated-draw": ("vulkan", ("eager-32-frames", "deferred-32-frames", "omission-control")),
    "scarlett-commons-continued-add-basic": ("cpu", ("case-validation", "addition-0x40700000", "subtraction-control")),
    "anyxboxx-147-native-wave64-gather": ("hip-wave64", ("lane-exec-controls", "both-addresses")),
    "xcl-87-wave32-carry": ("d3d12", ("native-adapter", "triangle-edge-count")),
    "xcl-87-ssa-projection": ("d3d12", ("native-adapter", "matched-images", "paired-measurement")),
    "anyxboxx-84-gfx103x-pack": ("hip-wave32", ("physical-gfx103x-wave32", "a1", "a2", "a3", "a4")),
    FRAMELAB_TASK: ("vulkan", ("same-binary", "same-timeline", "cross-binary", "cross-timeline")),
    "xcl-2126-scratch-coverage": ("d3d12-wave32", ("skip-middle-piece", "overlapping-edges")),
    "portbridge-subgroup-wave64": ("vulkan-wave64", ("cross-half", "partial-workgroup")),
}
REPORT_HEADER = "portbridge test report v1"
FIELD_LINE = re.compile(r"(task|revisions|equipment|hardware|pci|os|driver|toolchain|subgroup-width|opt-in):\s*(.+)", re.I)
CASE_LINE = re.compile(r"case:\s*([a-z0-9-]{1,50})\s*=\s*(pass|fail|skip)", re.I)
SAFE_VALUE = re.compile(r"[\w][\w .,+()/_-]{0,99}")
PCI_ID = re.compile(r"([0-9a-f]{4}):([0-9a-f]{4})")
VIRTUAL_DEVICE = re.compile(r"\b(?:warp|llvmpipe|lavapipe|swiftshader|software renderer|virtual adapter)\b", re.I)


def structured_fields(lines):
    """Parse exactly one report envelope; explanatory text may follow a blank line."""
    lines = list(lines)
    starts = [i for i, line in enumerate(lines) if line.strip().casefold() == REPORT_HEADER]
    if len(starts) != 1:
        return None
    fields, cases = {}, {}
    for line in lines[starts[0] + 1:]:
        if not line.strip():
            break
        if match := FIELD_LINE.fullmatch(line):
            name, value = match[1].lower(), match[2]
            if name in fields:
                return None
            fields[name] = value
        elif match := CASE_LINE.fullmatch(line):
            name = match[1].lower()
            if name in cases:
                return None
            cases[name] = match[2].lower()
        else:
            return None
    return fields, cases


def case_outcome(cases, expected):
    """Classify observed cases for one setup, leaving incomplete runs open."""
    if not cases or cases.keys() - set(expected) or set(cases.values()) - {"pass", "fail", "skip"}:
        return None
    if "fail" in cases.values():
        return "fail"
    if cases.keys() == set(expected) and "skip" not in cases.values():
        return "pass"
    return "partial"


def structured_result(body, task):
    # Preserve a real blank boundary while applying the same visible-line rules as
    # volunteer discovery. Quoted, fenced and hidden templates do not count.
    parsed = structured_fields(report_lines(body, preserve_blank=True))
    if not parsed:
        return None
    fields, cases = parsed
    revisions = fields.get("revisions", "").lower().split()
    equipment = fields.get("equipment", "").lower()
    hardware = fields.get("hardware", "")
    platform = fields.get("os", "")
    os_name = next((name for name in task["os"]
                    if platform.casefold().startswith(name.casefold() + " ")), None)
    pci = PCI_ID.fullmatch(fields.get("pci", "").lower())
    driver = fields.get("driver", "")
    toolchain = fields.get("toolchain", "")
    opt_in = fields.get("opt-in", "no").lower()
    if (fields.get("task") != task["id"] or revisions != [row["sha"] for row in task["revisions"]]
            or equipment not in task["equipment"] or not os_name or opt_in not in {"yes", "no"}
            or not all(SAFE_VALUE.fullmatch(value) for value in (hardware, platform, toolchain))
            or not re.search(r"\d", toolchain)):
        return None
    if equipment == "cpu":
        if pci or fields.get("pci") or driver:
            return None
    elif (not pci or pci[1] != GPU_VENDORS.get(equipment) or VIRTUAL_DEVICE.search(hardware)
          or not SAFE_VALUE.fullmatch(driver) or not re.search(r"\d", driver)):
        return None
    outcome = case_outcome(cases, task["report_cases"])
    if outcome is None:
        return None
    subgroup = fields.get("subgroup-width")
    if task["report_profile"] == "vulkan-wave64":
        if subgroup != "64" and (subgroup != "32" or any(value != "skip" for value in cases.values())):
            return None
    elif subgroup is not None:
        return None
    result = {"revision": revisions[0], "revisions": revisions, "equipment": equipment, "hardware": hardware,
              "device_id": pci[0] if pci else hardware.casefold(), "os": platform, "os_family": os_name,
              "driver": driver or None, "toolchain": toolchain, "cases": cases, "outcome": outcome, "opt_in": opt_in == "yes"}
    if subgroup is not None:
        result["subgroup_width"] = int(subgroup)
    return result
