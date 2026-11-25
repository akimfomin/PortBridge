"""Check the matching scope, consent precedence, and unique hardware proposals."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from portbridge.volunteer_plan import build_plan


NOW = datetime(2026, 11, 25, 6, tzinfo=timezone.utc)
PROFILE = "d3d12-wave32"
TARGET = "xcl-2126-scratch-coverage"


def at(*, minutes=0, days=0):
    return (NOW - timedelta(minutes=minutes, days=days)).isoformat()


def task(task_id=TARGET, *, profile=PROFILE, state="fresh", reports=()):
    return {"id": task_id, "equipment": ["amd", "intel"], "os": ["Windows"], "status": "needs_run",
            "report_profile": profile, "coverage_policy": "all", "result_url": "https://github.com/akimfomin/PortBridge/issues/54",
            "coverage": [{"equipment": vendor, "state": "missing"} for vendor in ("amd", "intel")],
            "report_sync": {"state": state, "checked_at": at(minutes=3), "reports": list(reports)}}


def report(author, equipment, index, **changes):
    base = {"author": author, "equipment": equipment, "os_family": "Windows", "os": "Windows 11",
            "opt_in": True, "outcome": "pass", "authority": "approved", "hardware": "Synthetic GPU",
            "url": f"https://github.com/example/lab/issues/37#issuecomment-{index}", "reported_at": at(minutes=index)}
    return {**base, **changes}


class VolunteerPlanTest(unittest.TestCase):
    def plan(self, *tasks):
        return build_plan({"tasks": tasks}, TARGET, now=NOW)

    def test_maximizes_independent_proposals_when_one_volunteer_covers_both_vendors(self):
        target = task()
        previous = task("previous-check", reports=[
            report("Both", "amd", 16), report("Both", "intel", 17), report("AMD-Only", "amd", 18),
        ])
        plan = self.plan(target, previous)
        self.assertEqual([(item["equipment"], item["volunteer"], item["state"]) for item in plan["proposals"]],
                         [("amd", "AMD-Only", "proposed"), ("intel", "Both", "proposed")])
        self.assertEqual([cell["eligible_volunteers"] for cell in plan["cells"]], [2, 1])
        self.assertEqual(plan, self.plan(previous, target))
        previous["report_sync"]["reports"].reverse()
        self.assertEqual(plan, self.plan(target, previous))

    def test_latest_refusal_and_ineligible_report_scopes_are_excluded(self):
        eligible = [
            report("Revoked", "amd", 16), report("Other-OS", "amd", 19, os_family="Linux", os="Linux 6"),
            report("Old", "intel", 53, reported_at=at(days=91)), report("Failed", "amd", 42, outcome="fail"),
            report("Community", "intel", 63, authority="community"),
        ]
        refusal = report("revoked", "amd", 73, updated_at=at(minutes=4), opt_in=False, authority="community")
        other_profile = task("other", profile="vulkan", reports=[report("Vulkan", "amd", 15)])
        stale = task("stale", state="stale", reports=[report("Old-Source", "intel", 48)])
        plan = self.plan(task(), task("previous", reports=eligible), task("new", reports=[refusal]),
                         other_profile, stale)
        self.assertTrue(plan["can_plan"])
        self.assertEqual(plan["proposals"], [])
        self.assertEqual([cell["eligible_volunteers"] for cell in plan["cells"]], [0, 0])

    def test_no_assignment_for_covered_or_unobserved_cell_and_any_caps_at_one(self):
        historical = task("previous", reports=[report("A", "amd", 5), report("B", "intel", 6)])
        target = task()
        target["coverage"][0]["state"] = "covered"
        self.assertEqual([item["equipment"] for item in self.plan(target, historical)["proposals"]], ["intel"])
        held = deepcopy(target)
        held["report_sync"]["checked_at"] = at(minutes=121)
        self.assertFalse(self.plan(held, historical)["can_plan"])
        self.assertFalse(self.plan(held, historical)["proposals"])
        target["coverage"][0]["state"] = "missing"
        target["coverage_policy"] = "any"
        self.assertEqual(len(self.plan(target, historical)["proposals"]), 1)
