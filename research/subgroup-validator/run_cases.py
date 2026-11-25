# SPDX-License-Identifier: MIT
"""Reproducible controls for the bounded subgroup contract validator."""

import json
from time import perf_counter

from lane_contract import Addressing, Domain, Exchange, Guest, Inactive, Lowering, Participation, check


def cases():
    half = Guest(32)
    full = Guest(64)
    exec32 = Domain(64, 32, Participation.EXEC)
    full64 = Domain(64, 64, Participation.FULL)
    superset64 = Domain(64, 64, Participation.SUPERSET)
    independent32 = Domain(64, 32, Participation.INDEPENDENT)
    return (
        ("rdna2_half_projected_to_native32", half, Lowering(32), exec32, True),
        ("rdna2_half_to_native64_with_exec_contract", half, Lowering(32), superset64, True),
        ("wrong_guest_partition", half, Lowering(64), full64, False),
        ("unguarded_with_exec_mask", half, Lowering(32, guest_guard=False), exec32, False),
        ("unguarded_with_host_full", half, Lowering(32, guest_guard=False), full64, False),
        ("guest_guard_without_host_participation", half, Lowering(32), independent32, False),
        ("host_guard_masks_missing_live_data", half, Lowering(32, host_guard=True), independent32, False),
        ("full_guest_wave_native32_without_exchange", full, Lowering(64), exec32, False),
        ("full_guest_wave_native32_with_snapshot_contract", full, Lowering(64, exchange=Exchange.CURRENT), exec32, True),
        ("full_guest_wave_native32_stale_exchange", full, Lowering(64, exchange=Exchange.STALE), exec32, False),
        ("clobber_inactive_destination", half, Lowering(32, preserve_inactive=False), full64, False),
        ("xor_transport", Guest(32, Addressing.XOR), Lowering(32, Addressing.XOR),
         Domain(32, 32, Participation.SUPERSET), True),
        ("confuse_xor_and_indexed_transport", Guest(32, Addressing.XOR), Lowering(32),
         Domain(32, 32, Participation.SUPERSET), False),
        ("guest_undefined_can_be_refined", Guest(32, inactive_source=Inactive.UNDEFINED),
         Lowering(32, guest_guard=False), exec32, True),
    )


def main() -> None:
    results = {}
    for name, guest, lowering, domain, passes in cases():
        start = perf_counter()
        outcome = check(guest, lowering, domain)
        if (outcome["status"] == "passes modeled domain") != passes:
            raise AssertionError(f"unexpected control result for {name}: {outcome}")
        results[name] = {**outcome, "elapsed_ms": round((perf_counter() - start) * 1000, 3)}
    print(json.dumps({"cases": results}, indent=2))


if __name__ == "__main__":
    main()
