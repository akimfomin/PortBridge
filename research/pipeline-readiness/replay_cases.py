"""Generate reproducible, synthetic counterexamples for pipeline admission policies."""

from dataclasses import asdict
import json

from readiness import Limits, Pipeline, Request, replay


CASES = {
    "worker-contention": (
        tuple(Pipeline(f"warmup-{i}", 80_000 + i * 5_000, 256) for i in range(4))
        + (Pipeline("first-draw", 8_000, 1024),),
        tuple(Request(0, f"warmup-{i}") for i in range(4)) + (Request(5_000, "first-draw", True),),
        0,
    ),
    "combined-memory-pressure": (
        (Pipeline("warmup-long", 95_000, 3200), Pipeline("warmup-short", 80_000, 3100),
         Pipeline("warmup-small", 45_000, 900), Pipeline("first-draw", 12_000, 4096)),
        (Request(0, "warmup-long"), Request(0, "warmup-short"), Request(0, "warmup-small"),
         Request(8_000, "first-draw", True)),
        0,
    ),
    "accurate-early-warmup": (
        (Pipeline("first-draw", 24_000, 5000), Pipeline("later-draw", 15_000, 1000)),
        (Request(0, "first-draw"), Request(0, "later-draw"), Request(100_000, "first-draw", True)),
        80_000,
    ),
    "late-phase-signal": (
        (Pipeline("long-warmup", 120_000, 5000), Pipeline("first-draw", 12_000, 4096)),
        (Request(0, "long-warmup"), Request(40_000, "first-draw", True)),
        20_000,
    ),
}


def report():
    cases = {}
    for name, (pipelines, requests, signal) in CASES.items():
        policies = {
            "demand-first": Limits(4, 8192),
            "reserved-worker": Limits(4, 8192, protected_workers=1),
            "reserved-worker-and-memory": Limits(4, 8192, protected_workers=1, protected_mib=4096),
            "phase-armed-reservation": Limits(4, 8192, 1, 4096, protect_from_us=signal),
        }
        cases[name] = {
            "pipelines": [asdict(pipeline) for pipeline in pipelines],
            "requests": [asdict(request) for request in requests],
            "policies": {policy: {"limits": asdict(limits), "result": asdict(replay(pipelines, requests, limits))}
                         for policy, limits in policies.items()},
        }
    return {"source": "synthetic fixed costs and memory estimates", "cases": cases}


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, sort_keys=True))
