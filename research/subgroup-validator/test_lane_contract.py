# SPDX-License-Identifier: MIT
"""Cross-check the mask projection against a direct exhaustive oracle."""

from itertools import product
import unittest

from lane_contract import Addressing, Domain, Exchange, Guest, Inactive, LaneBase, Lowering, Participation, Probe, active
from lane_contract import check, compare, project
from run_cases import cases


def failure_signatures(guest, lowering, domain, probes):
    result = set()
    for probe in probes:
        if failure := compare(guest, lowering, domain, probe):
            result.add((probe.destination, probe.selector, failure.reason))
    return result


def every_mask(domain):
    mask_limit = 1 << domain.wave
    for dst, index in product(range(domain.wave), repeat=2):
        for guest in range(mask_limit):
            if domain.participation == Participation.EXEC:
                yield Probe(dst, index, guest, guest)
            elif domain.participation == Participation.FULL:
                yield Probe(dst, index, guest, mask_limit - 1)
            else:
                for host in range(mask_limit):
                    if (not active(host, dst)
                        or domain.participation == Participation.SUPERSET and host & guest != guest):
                        continue
                    yield Probe(dst, index, guest, host)


class ProjectionTest(unittest.TestCase):
    def test_known_outcomes(self):
        for name, guest, lowering, domain, expected in cases():
            with self.subTest(name=name):
                result = check(guest, lowering, domain)
                self.assertEqual(expected, result["failing_projected_probes"] == 0)
                self.assertEqual(expected, not result["witnesses"])

    def test_projection_matches_every_mask_at_four_lanes(self):
        for physical, guest_scope, target_scope, participation in product((2, 4), (2, 4), (2, 4), Participation):
            domain = Domain(4, physical, participation)
            for addressing, inactive in product(Addressing, Inactive):
                guest = Guest(guest_scope, addressing, inactive)
                lowerings = [
                    Lowering(target_scope, addressing),
                    Lowering(target_scope, addressing, guest_guard=False),
                    Lowering(target_scope, addressing, host_guard=True),
                    Lowering(target_scope, addressing, preserve_inactive=False),
                    Lowering(target_scope, addressing, exchange=Exchange.CURRENT),
                    Lowering(target_scope, addressing, exchange=Exchange.STALE),
                    Lowering(target_scope, Addressing.XOR if addressing == Addressing.INDEX else Addressing.INDEX),
                ]
                if target_scope <= physical:
                    lowerings.append(Lowering(target_scope, addressing, lane_base=LaneBase.HOST))
                for lower in lowerings:
                    projected = (
                        probe
                        for lane, selector in product(range(4), repeat=2)
                        for probe in project(guest, lower, domain, lane, selector)
                    )
                    self.assertEqual(
                        failure_signatures(guest, lower, domain, every_mask(domain)),
                        failure_signatures(guest, lower, domain, projected),
                    )

    def test_non_power_of_two_and_oob_scope_rejected(self):
        with self.assertRaises(ValueError):
            check(Guest(16), Lowering(24), Domain(32, 32, Participation.FULL))
        with self.assertRaises(ValueError):
            check(Guest(64), Lowering(16), Domain(32, 32, Participation.FULL))
        with self.assertRaises(ValueError):
            check(Guest(32), Lowering(64, lane_base=LaneBase.HOST), Domain(64, 32, Participation.FULL))

    def test_hand_computed_upper_half_and_inactive_boundary(self):
        guest = Guest(32)
        domain = Domain(64, 64, Participation.FULL)
        # Index 63 names upper-half lane 63 for destination 32, but
        # low-half lane 31 for destination 0.
        mask = (1 << 32) | (1 << 63) | 1
        self.assertIsNone(compare(guest, Lowering(32), domain, Probe(32, 63, mask, (1 << 64) - 1)))
        incorrect = compare(guest, Lowering(64, guest_guard=False), domain, Probe(0, 63, mask, (1 << 64) - 1))
        self.assertEqual(("zero", -1), incorrect.expected)
        self.assertEqual(("source", 63), incorrect.actual)


if __name__ == "__main__":
    unittest.main()
