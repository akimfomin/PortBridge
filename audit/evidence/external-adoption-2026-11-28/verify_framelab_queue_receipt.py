"""Validate the fence proof for a synthetic same-feature, same-queue test."""
import json
from pathlib import Path
import re
import sys


def valid(trace):
    if not isinstance(trace, dict):
        return False
    submitted = trace.get("submitted_before_gate_release")
    if submitted != [1, 2] or any(type(value) is not int for value in submitted):
        return False
    for field, expected in (("gate_completed_before_release", 0),
                            ("retired_before_release", 0), ("retired_after_release", 2)):
        value = trace.get(field)
        if type(value) is not int or value != expected:
            return False
    expected = trace.get("expected_readbacks")
    actual = trace.get("observed_readbacks")
    return (isinstance(expected, list) and len(expected) == 2
            and all(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) for value in expected)
            and expected[0] != expected[1] and actual == expected)


def self_test():
    base = {"submitted_before_gate_release": [1, 2], "gate_completed_before_release": 0,
            "retired_before_release": 0, "retired_after_release": 2,
            "expected_readbacks": ["a" * 64, "b" * 64], "observed_readbacks": ["a" * 64, "b" * 64]}
    assert valid(base)
    for changed in ({"retired_before_release": 1}, {"retired_after_release": (1 << 64) - 1},
                    {"observed_readbacks": ["b" * 64, "a" * 64]}, {"gate_completed_before_release": 1},
                    {"submitted_before_gate_release": [True, 2]}):
        assert not valid({**base, **changed}), changed
    print("PASS: two queued frames and five negative controls")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Provide a JSON trace path or --self-test")
    if sys.argv[1] == "--self-test":
        self_test()
    elif valid(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))):
        print("PASS: both submissions preceded retirement and both readbacks matched")
    else:
        raise SystemExit("FAIL: fence or readback evidence is missing or disagrees")
