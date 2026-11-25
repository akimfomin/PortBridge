"""Attribute one observed presenter wait to phases on its graphics release path."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


PHASES = ("build_queue", "translation", "driver_admission", "native_driver")


def object_value(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def list_value(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def identifier(record, field):
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def interval(record):
    begin, end = record.get("begin_us"), record.get("end_us")
    if type(begin) is not int or type(end) is not int or not 0 <= begin < end:
        raise ValueError("interval must have integer microseconds with 0 <= begin < end")
    return begin, end


def audit_wait(trace):
    trace = object_value(trace, "trace")
    wait = object_value(trace.get("wait"), "wait")
    wait_begin, wait_end = interval(wait)
    release_path = identifier(wait, "producer"), identifier(wait, "command_list")
    events = defaultdict(list, {wait_begin: [], wait_end: []})
    pipeline_keys = set()
    matched_resolutions = 0

    def add_interval(begin, end, index, phase=None):
        begin, end = max(begin, wait_begin), min(end, wait_end)
        if begin < end:
            events[begin].append((index, phase, 1))
            events[end].append((index, phase, -1))

    for index, record in enumerate(list_value(trace.get("resolutions"), "resolutions")):
        resolution = object_value(record, "resolution")
        path = identifier(resolution, "producer"), identifier(resolution, "command_list")
        pipeline = identifier(resolution, "pipeline")
        begin, end = interval(resolution)
        on_path = path == release_path and begin < wait_end and end > wait_begin
        if on_path:
            matched_resolutions += 1
            pipeline_keys.add(pipeline)
            add_interval(begin, end, index)
        for entry in list_value(resolution.get("phases", []), "phases"):
            phase = object_value(entry, "phase")
            kind = identifier(phase, "kind")
            phase_begin, phase_end = interval(phase)
            if kind not in PHASES:
                raise ValueError(f"unknown phase {kind!r}")
            if not begin <= phase_begin < phase_end <= end:
                raise ValueError("phase interval must be inside its resolution")
            if on_path:
                add_interval(phase_begin, phase_end, index, kind)

    phase_us = dict.fromkeys(PHASES, 0)
    outside_us = unattributed_us = overlapping_us = 0
    active_resolutions = set()
    active_phases = Counter()
    covered_resolutions = Counter()
    previous = wait_begin
    for at, changes in sorted(events.items()):
        elapsed = at - previous
        if not active_resolutions:
            outside_us += elapsed
        elif len(active_phases) > 1:
            overlapping_us += elapsed
        elif len(covered_resolutions) < len(active_resolutions):
            unattributed_us += elapsed
        else:
            phase_us[next(iter(active_phases))] += elapsed

        for index, phase, delta in changes:
            if phase is None:
                if delta > 0:
                    active_resolutions.add(index)
                else:
                    active_resolutions.remove(index)
                continue
            active_phases[phase] += delta
            if not active_phases[phase]:
                del active_phases[phase]
            covered_resolutions[index] += delta
            if not covered_resolutions[index]:
                del covered_resolutions[index]
        previous = at

    wait_us = wait_end - wait_begin
    return {
        "wait_us": wait_us,
        "resolution_us": wait_us - outside_us,
        "outside_resolution_us": outside_us,
        "unattributed_resolution_us": unattributed_us,
        "overlapping_phases_us": overlapping_us,
        "phase_us": phase_us,
        "matched_resolutions": matched_resolutions,
        "distinct_pipeline_keys": len(pipeline_keys),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    try:
        result = audit_wait(json.loads(args.trace.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
