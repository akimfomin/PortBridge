"""Focused checks for sources, revisions, and coverage in the research queue."""

from datetime import datetime, timedelta, timezone

from portbridge.activity import build_activity
from portbridge.lab import build_lab
from portbridge.radar import build_radar

from test_portbridge import CatalogFixture


NOW = datetime(2026, 11, 25, 6, tzinfo=timezone.utc)
FRESH = (NOW - timedelta(minutes=5)).isoformat()


class RadarTest(CatalogFixture):
    def row(self, project, number, *, signal=None, reference=None, revision=None,
            status="open", fetched_at=FRESH):
        repo = next(item["repo"] for item in self.catalog.projects() if item["slug"] == project)
        title = "Preserve cross-piece buffer values"
        return {
            **self.observation(project, "pr", number, title, f"https://github.com/{repo}/pull/{number}", {
                "head_sha": revision,
                "technical": {"signals": [signal] if signal else [], "references": [reference] if reference else []},
            }),
            "status": status, "updated_at": fetched_at, "fetched_at": fetched_at,
        }

    def queue(self, observations, tasks=(), changes=(), *, projects=None):
        return build_radar(projects if projects is not None else self.catalog.projects(), observations,
                           changes, {"tasks": tasks}, [], NOW)["actions"]

    def test_unknown_cross_project_candidate_needs_both_a_citation_and_a_symbol(self):
        source = self.row("xcl", 2126, signal="ds_read_b64", revision="c" * 40, status="merged")
        target = self.row("continued", 8123, signal="ds_read_b64", reference=source["url"], revision="b" * 40)
        same_revision = self.row("anyxboxx", 8124, signal="ds_read_b64", reference=source["url"], revision="c" * 40)
        same_symbol_only = self.row("continued", 8125, signal="ds_read_b64")
        unrelated_citation = self.row("continued", 8126, reference=source["url"], signal="ds_read_b32")
        closed = self.row("continued", 8127, signal="ds_read_b64", reference=source["url"], status="closed")
        observations = [source, target, same_revision, same_symbol_only, unrelated_citation, closed]
        action, = self.queue(observations)
        self.assertEqual(action["kind"], "compare_sources")
        self.assertEqual(action["target_url"], target["url"])
        self.assertEqual(action["signals"], ["ds_read_b64"])
        self.assertEqual(action["priority"], "exploratory")
        self.assertEqual(action["sources"][1]["url"], source["url"])
        self.assertEqual(action, self.queue(reversed(observations))[0])

        projects = self.catalog.projects()
        next(project for project in projects if project["slug"] == "xcl")["sync_status"] = "stale"
        held, = self.queue(observations, projects=projects)
        self.assertEqual((held["id"], held["state"], held["freshness"]["state"]),
                         (action["id"], "verify_sources", "stale"))

    def test_closed_pinned_source_is_a_reference_and_unavailable_source_is_omitted(self):
        source = self.row("victory", 605, signal="v_cvt_rpi_i32_f32", revision="e" * 40, status="closed")
        target = self.row("xcl", 1020, signal="v_cvt_rpi_i32_f32", reference=source["url"])
        action, = self.queue([source, target])
        self.assertEqual((action["target_url"], action["sources"][-1]["status"]), (target["url"], "closed"))
        self.assertEqual(self.queue([{**source, "metadata": {**source["metadata"], "head_sha": None}}, target]), [])
        projects = self.catalog.projects()
        next(project for project in projects if project["slug"] == "victory")["sync_status"] = "unavailable"
        self.assertEqual(self.queue([source, target], projects=projects), [])

    def test_observed_changed_head_creates_recheck_for_the_exact_pinned_lab_task(self):
        task = build_lab(task="continued-511-repeated-draw")["tasks"][0]
        prior = task["revisions"][0]["sha"]
        initial = self.row("continued", 511, revision=prior, fetched_at=(NOW - timedelta(hours=1)).isoformat())
        moved = self.row("continued", 511, revision="f" * 40)
        self.catalog.record_sync({"items": [initial]})
        self.catalog.record_sync({"items": [moved]})
        # record_sync stores the transition timestamp from its own clock. Replay that pinned
        # transition at the controlled test time without changing the actual catalog clock.
        history = [{**change, "observed_at": FRESH} for change in self.catalog.source_changes()]
        action, = self.queue([moved], [task], history)
        self.assertEqual((action["kind"], action["state"]), ("recheck_revision", "recheck_revision"))
        self.assertEqual(action["target_revision"], "f" * 40)
        self.assertEqual(action["sources"][-1]["revision"], prior)
        self.assertEqual(self.queue([moved], [task])[0]["kind"], "cover_hardware")
        self.assertEqual(self.queue([{**moved, "status": "merged"}], [task], history), [])
        self.assertIn("radar", build_activity(self.catalog))

    def test_displaced_pin_stays_queued_across_multiple_observed_updates(self):
        task = build_lab(task="continued-511-repeated-draw")["tasks"][0]
        pinned = task["revisions"][0]["sha"]
        middle, current = "d" * 40, "e" * 40
        target = self.row("continued", 511, revision=current)
        first = {"url": target["url"], "previous_revision": pinned, "revision": middle,
                 "observed_at": (NOW - timedelta(days=9)).isoformat()}
        second = {"url": target["url"], "previous_revision": middle, "revision": current, "observed_at": FRESH}
        action, = self.queue([target], [task], [first, second])
        self.assertEqual((action["kind"], action["state"]), ("recheck_revision", "recheck_revision"))
        self.assertEqual(action["sources"][-1]["revision"], pinned)
        unrelated = {**second, "previous_revision": "a" * 40}
        self.assertEqual(self.queue([target], [task], [first, unrelated])[0]["kind"], "cover_hardware")
        rolled_back = self.row("continued", 511, revision=pinned)
        self.assertEqual(self.queue([rolled_back], [task], [first, second])[0]["kind"], "cover_hardware")

    def test_review_and_uncovered_cells_can_proceed_in_parallel_for_all_policy(self):
        task = build_lab(task="framelab-12-vulkan-handoff")["tasks"][0]
        report = {
            "url": task["result_url"] + "#issuecomment-7153817545",
            "revision": task["revisions"][0]["sha"], "outcome": "pass", "authority": "community",
        }
        task.update(equipment=["amd", "intel"], coverage_policy="all", coverage=[
            {"equipment": "amd", "state": "reported"},
            {"equipment": "intel", "state": "missing"},
        ], report_sync={"state": "fresh", "checked_at": FRESH, "reports": [report]})
        actions = self.queue([], [task])
        self.assertEqual([action["kind"] for action in actions], ["review_report", "cover_hardware"])
        self.assertEqual(actions[1]["equipment"], ["intel"])
        self.assertEqual(actions[0]["sources"][-1]["url"], report["url"])
        task["coverage"][1]["state"] = "partial"
        self.assertEqual(self.queue([], [task])[1]["equipment"], ["intel"])
        task["report_sync"]["state"] = "stale"
        self.assertEqual([action["state"] for action in self.queue([], [task])],
                         ["verify_sources", "verify_sources"])
        task["coverage_policy"] = "any"
        only_review, = self.queue([], [task])
        self.assertEqual(only_review["kind"], "review_report")
