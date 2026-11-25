# SPDX-License-Identifier: MIT
"""Compare synthetic source execution and two #2080 transport layouts."""

import argparse
from collections import Counter
import json
from pathlib import Path
from runpy import run_path
import sys
import unittest


proof = run_path(str(Path(__file__).with_name("proof.py")))
run_unsplit = proof["run_unsplit"]
run_split = proof["run_split"]
layout_fields = proof["layout_fields"]
stable_values = proof["stable_values"]
mixed_program = proof["mixed_program"]
linear_program = proof["linear_program"]
incompatible_program = proof["incompatible_program"]
LANES = 96


CASES = (
    ("mixed_5_pieces", mixed_program(), (9644, 7448, 7)),
    ("linear_3_pieces", linear_program(3), (7680, 5376, 5)),
    ("linear_4_pieces", linear_program(4), (11520, 6912, 5)),
    ("linear_5_pieces", linear_program(5), (15360, 8448, 5)),
    ("linear_5_all_transient", linear_program(5, anchors=False), (6144, 6144, 2)),
    ("different_definitions", incompatible_program(), (2880, 2880, 3)),
)


def check_program(test, program):
    accumulators = (Counter(), Counter())
    stability = stable_values(program)
    visits = Counter()
    for lane in range(LANES):
        expected = run_unsplit(program, lane)
        baseline, original_trace, original_stride = run_split(program, lane, False)
        candidate, new_trace, new_stride = run_split(program, lane, True)
        test.assertEqual(expected, baseline, (lane, "old"))
        test.assertEqual(expected, candidate, (lane, "new"))
        test.assertEqual(original_stride, new_stride, lane)
        visited = {stage for stage, _ in expected}
        visits.update(visited)
        for stage, piece in enumerate(program.pieces):
            for action in ("read", "write"):
                test.assertEqual(original_trace[stage, action, "tag"], new_trace[stage, action, "tag"])
            test.assertEqual(new_trace[stage, "read", "tag"], int(stage > 0))
            if stage not in visited:
                test.assertTrue(all(name == "tag" for part, _, name in new_trace if stage == part))
            for name in stability:
                width = program.specs[name].words
                test.assertEqual(new_trace[stage, "write", name], width if stage == 0 and len(visited) > 1 else 0)
                test.assertEqual(new_trace[stage, "read", name],
                                 width if stage > 0 and stage in visited and name in piece.original_operands else 0)
        for accum, trace in zip(accumulators, (original_trace, new_trace)):
            for (_, action, name), words in trace.items():
                accum[action] += words
                if name == "tag":
                    accum[f"{action}_tag"] += words
                if name in stability:
                    accum[f"{action}_eligible"] += words
    return original_stride, stability, visits, accumulators


class TransportTest(unittest.TestCase):
    def test_compares_unsplit_stock_and_prefix_and_counts_words(self):
        for name, program, (old, new, expected_stride) in CASES:
            with self.subTest(name=name):
                stride, stable, visits, (stock, patched) = check_program(self, program)
                self.assertEqual(expected_stride, stride)
                self.assertEqual((old, new), tuple(4 * (a["read"] + a["write"]) for a in (stock, patched)))
                self.assertEqual(not stable, old == new)
                self.assertEqual(len(program.pieces), len(visits))

    def test_stable_slots_cannot_alias_tag_or_variable_edge_layouts(self):
        program = mixed_program()
        old_stride, old = layout_fields(program)
        new_stride, new = layout_fields(program, stable_values(program))
        self.assertEqual(new_stride, old_stride)
        self.assertNotEqual(old[1]["anchor64"], old[2]["anchor64"])
        self.assertNotEqual(new[1]["seed32"], new[2]["seed32"])
        for tag, fields in new.items():
            with self.subTest(tag=tag):
                self.assertEqual(fields["anchor32"], (1,))
                self.assertEqual(fields["anchor64"], (2, 3))
                used = [word for words in fields.values() for word in words]
                self.assertEqual(len(used), len(set(used)))
                self.assertTrue(all(0 < word < new_stride for word in used))
        with self.assertRaisesRegex(ValueError, "changed the original edge size"):
            layout_fields(program, ("seed64",))

    def test_skip_exit_and_both_i64_words(self):
        program = mixed_program()
        terminal, terminal_trace, _ = run_split(program, 0, True)
        self.assertEqual((0,), tuple(piece for piece, _ in terminal))
        self.assertEqual([(0, "write", "tag")] + [(p, "read", "tag") for p in range(1, 5)], list(terminal_trace))

        forward_skip, skip_trace, _ = run_split(program, 2, True)
        self.assertEqual((0, 4), tuple(piece for piece, _ in forward_skip))
        a64 = 0xFFFF_00FD_0102_0304 + 2 * 0x1_0000_0001
        seed = 0x9000_1AB3_AAC2_1234 + 2 * 0x20200_0319
        self.assertEqual(forward_skip[-1][1][0], a64 ^ seed)
        self.assertEqual(skip_trace[0, "write", "anchor64"], 2)
        self.assertEqual(skip_trace[4, "read", "anchor64"], 2)
        self.assertEqual(skip_trace[4, "write", "anchor64"], 0)
        active = {tuple(stage for stage, _ in run_unsplit(program, lane)) for lane in range(LANES)}
        self.assertTrue({(0,), (0, 4), (0, 1), (0, 2, 3), (0, 1, 2, 3, 4)}.issubset(active), active)

    def test_late_defs_changed_types_and_rematerialized_values_stay_dynamic(self):
        program = incompatible_program()
        self.assertEqual(set.intersection(*(set(edge.live) for edge in program.edges)), {"remat"})
        self.assertEqual(stable_values(program), ())
        for lane in (0, 1, 4, 5):
            observed, trace, _ = run_split(program, lane, True)
            bits = (0x7FC0_0000 if lane % 4 == 0 else 0x8000_0000) | lane
            if lane % 2 == 0:
                self.assertEqual(trace[1, "write", "new_bits"], 2)
                self.assertEqual(observed[-1][1][0] >> 32, bits)
            else:
                self.assertEqual(observed[-1][1][0], bits)
            self.assertFalse(any(name == "remat" for _, _, name in trace))


def collect():
    results = []
    test = unittest.TestCase()
    for name, program, _ in CASES:
        stride, stable, visits, (stock, patched) = check_program(test, program)
        old_bytes = 4 * (stock["read"] + stock["write"])
        new_bytes = 4 * (patched["read"] + patched["write"])
        results.append({"case": name, "pieces": len(program.pieces), "crossing_edges": len(program.edges),
                        "lanes": LANES, "visits_per_piece": dict(sorted(visits.items())),
                        "stable_values": list(stable), "stable_dwords": sum(program.specs[v].words for v in stable),
                        "stride_dwords_each": stride, "baseline_dwords": dict(stock), "candidate_dwords": dict(patched),
                        "baseline_bytes": old_bytes, "candidate_bytes": new_bytes,
                        "saved_bytes": old_bytes - new_bytes,
                        "saved_percent": round(100 * (old_bytes - new_bytes) / old_bytes, 4)})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write transport counts to this file")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TransportTest)
    if not unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite).wasSuccessful():
        return 1
    results = collect()
    if args.json:
        args.json.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    for row in results:
        print(f"{row['case']:25} {row['baseline_bytes']:6} -> {row['candidate_bytes']:6} bytes; "
              f"{row['saved_percent']:7.3f}%; stride {row['stride_dwords_each']} DWORD/lane")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
