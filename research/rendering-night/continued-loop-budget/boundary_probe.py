#!/usr/bin/env python3
"""Exercise only terminating synthetic programs in Continued's CPU interpreter."""

from pathlib import Path
import argparse
import sys
from unittest.mock import patch


def run(tree):
    sys.path.insert(0, str(tree / "tests" / "semantic"))
    import test_loop_iteration_guard as upstream

    body_store = ("v_mov_b32_e32 v1, s8", "buffer_store_dword v1, v2, s[0:3], 0 offen")
    exit_store = ("v_mov_b32_e32 v1, 42", "buffer_store_dword v1, v2, s[0:3], 0 offen offset:4", "s_endpgm")

    def translate(name, items, lanes, limit, emulate=False):
        exec_init = "s_mov_b64 exec, -1" if lanes == 64 else "s_mov_b32 exec_lo, -1"
        with patch.object(upstream.rdna2spirv, "LOOP_LIMIT", limit):
            text, gen = upstream._translate_cs("cs_" + name, [exec_init, "v_lshlrev_b32_e32 v2, 3, v0", *items],
                                               threads=lanes, emulate=emulate)
        if gen.wave64 != (lanes == 64) or gen.emulate != emulate:
            raise AssertionError("unexpected translator wave mode")
        return text

    def memory(text, lanes, subgroup):
        constants = [0, 0, lanes * 8, 0x31016FAC]
        if hasattr(upstream, "run_compute_workgroup"):
            return upstream.run_compute_workgroup(text, lanes, subgroup, push_constants=constants + [0] * 28,
                                                  max_steps=10000)
        return upstream.run_workgroup(
            text, lanes, subgroup,
            inputs_for=lambda i: {"%wg_id": (0, 0, 0), "%local_id": (i, 0, 0),
                                  "%sg_lane": i % subgroup, "%local_index": i},
            push_constants=constants + [0] * 28, memory={})

    for lanes, subgroup, emulate in ((32, 32, False), (64, 64, False), (64, 32, True)):
        for limit, natural in ((0, 5), (1, 1), (1, 3), (4, 3), (4, 4), (4, 5)):
            items = ("s_mov_b32 s8, 0", "repeat:", "s_add_u32 s8, s8, 1", *body_store,
                     f"s_cmp_eq_u32 s8, {natural}", "s_cbranch_scc0 repeat", *exit_store)
            text = translate("finite_boundary", items, lanes, limit, emulate)
            if ("%loop_guard_" in text) != bool(limit):
                raise AssertionError("guard presence did not match finite boundary settings")
            output = memory(text, lanes, subgroup)
            actual = [(output.get(i * 8), output.get(i * 8 + 4)) for i in range(lanes)]
            expected = min(limit, natural) if limit else natural
            marker = 42 if emulate or expected == natural else None
            if actual != [(expected, marker)] * lanes:
                raise AssertionError(f"expected {(expected, marker)}, got {set(actual)}")
            print(f"finite: wave={lanes} subgroup={subgroup} emulate={emulate} budget={limit} "
                  f"natural={natural} counter={expected} marker={marker}", flush=True)

    acyclic = ("s_mov_b32 s8, 0", "s_branch high", "low:", "s_add_u32 s8, s8, 11",
               "s_branch finish", "high:", "s_add_u32 s8, s8, 6", "s_branch low", "finish:",
               *body_store, "s_endpgm")
    for limit in (0, 1):
        text = translate("acyclic_backward_address", acyclic, 32, limit)
        output = memory(text, 32, 32)
        if "OpLoopMerge" in text or "%loop_guard_" in text or [output.get(i * 8) for i in range(32)] != [17] * 32:
            raise AssertionError("the backwards-layout acyclic edge was charged as a loop")
        print(f"acyclic negative offset: lanes=32 budget={limit} counter=17 loop_header=none")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tree", type=Path)
    run(parser.parse_args().tree.resolve(strict=True))
