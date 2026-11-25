"""Verify public activity keeps source dates, evidence, and work states distinct."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
import json
from threading import Thread

from portbridge.__main__ import make_server
from portbridge.activity import EVENTS_PER_KIND, build_activity
from portbridge.export import export

from test_portbridge import CatalogFixture


NOW = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)


class ActivityTest(CatalogFixture):
    def save_pr(self, project, number, *, at, status="open", merged_at=None, revision=None, draft=False):
        repo = next(item["repo"] for item in self.catalog.projects() if item["slug"] == project)
        url = f"https://github.com/{repo}/pull/{number}"
        row = self.observation(project, "pr", number, f"Change {number}", url,
                               {"merged_at": merged_at, "head_sha": revision, "draft": draft})
        self.catalog.record_sync({"items": [{**row, "status": status, "updated_at": at, "fetched_at": at}]})
        return url

    def test_activity_uses_actual_merge_date_and_current_pull_state(self):
        recent = (NOW - timedelta(hours=2)).isoformat()
        old = (NOW - timedelta(days=8)).isoformat()
        future = (NOW + timedelta(hours=1)).isoformat()
        merged = self.save_pr("xcl", 10, at=recent, status="merged", merged_at=recent)
        old_merge = self.save_pr("xcl", 11, at=recent, status="merged", merged_at=old)
        undated_merge = self.save_pr("xcl", 12, at=recent, status="merged")
        open_draft = self.save_pr("continued", 13, at=recent, draft=True)
        future_open = self.save_pr("xcl", 14, at=future)
        self.save_pr("xcl", 15, at="invalid-date")
        summary = build_activity(self.catalog, now=NOW)
        self.assertEqual(summary["window_start"], (NOW - timedelta(days=7)).isoformat())
        self.assertEqual((summary["counts"]["merged"], summary["counts"]["open"]), (1, 1))
        events = {event["url"]: event for event in summary["events"]}
        self.assertEqual(events[merged]["date_basis"], "merged_at")
        self.assertEqual(events[open_draft]["date_basis"], "updated_at")
        self.assertTrue(events[open_draft]["draft"])
        self.assertTrue({old_merge, undated_merge, future_open}.isdisjoint(events))

    def test_status_and_revision_are_real_changes_and_reviewed_failures_remain_visible(self):
        at = lambda hour: (NOW - timedelta(hours=hour)).isoformat()
        self.save_pr("xcl", 71, at=at(4), revision="a" * 40)
        self.save_pr("xcl", 71, at=at(3), revision="b" * 40)
        self.save_pr("xcl", 71, at=at(2), status="closed", revision="b" * 40)
        self.save_pr("xcl", 71, at=at(1), status="closed", revision="b" * 40)
        summary = build_activity(self.catalog, now=NOW, cards=[self.catalog.problem("PB-0001")])
        self.assertEqual(summary["counts"]["changed"], 2)
        self.assertEqual(summary["counts"]["open"], 0)
        events = {e["kind"]: e for e in summary["events"] if e["project"] == "xcl"}
        self.assertEqual(events["revision_change"]["previous_revision"], "a" * 40)
        self.assertEqual(events["revision_change"]["revision"], "b" * 40)
        self.assertEqual(events["status_change"]["previous_status"], "open")
        self.assertEqual(events["status_change"]["at"], at(2))
        self.assertEqual(events["status_change"]["date_basis"], "observed_at")
        evidence = {e["url"].split("#")[-1]: e for e in summary["events"] if e["kind"] == "verified_result"}
        for comment, outcome in (("issuecomment-7120734503", "passed"), ("issuecomment-7122054510", "failed")):
            result = evidence[comment]
            self.assertEqual(result["outcome"], outcome)
            self.assertEqual(result["evidence_kind"], "independent")
            self.assertTrue(result["translations"]["en"]["summary"])

    def test_timeline_cap_preserves_counts_and_each_projects_latest_event(self):
        recent = (NOW - timedelta(hours=2)).isoformat()
        older = (NOW - timedelta(hours=3)).isoformat()
        for number in range(EVENTS_PER_KIND + 4):
            self.save_pr("xcl", number + 100, at=recent)
        older_open = self.save_pr("victory", 99, at=older)
        summary = build_activity(self.catalog, now=NOW, cards=[])
        visible = [event for event in summary["events"] if event["kind"] == "open_pr"]
        self.assertEqual(len(visible), EVENTS_PER_KIND)
        self.assertEqual(summary["counts"]["open"], EVENTS_PER_KIND + 5)
        self.assertNotIn(older_open, {event["url"] for event in visible})
        winner = next(team for team in summary["projects"] if team["slug"] == "victory")
        self.assertEqual(winner["last_activity"]["url"], older_open)

    def test_handoffs_keep_delivery_review_reproduction_and_adoption_distinct(self):
        date = (NOW - timedelta(hours=2)).isoformat()
        self.save_pr("xcl", 111, at=date, status="merged", merged_at=date)
        summary = build_activity(self.catalog, now=NOW)
        handoffs = summary["handoffs"]
        self.assertEqual(summary["counts"]["merged"], 1)
        self.assertEqual(handoffs["counts"], {"delivered": 15, "independently_reproduced": 9,
                                             "formally_reviewed": 4, "adopted": 5})
        (continued, xcl, anyxboxx, rounding, division, warp, texture, paired_lds, lds_wait,
         frame_pacer, xcl_compact, monitor, framelab, scratch_candidate, gfx10) = handoffs["items"]
        self.assertEqual(continued["problem_id"], "PB-044801754884724660835754613454516035131")
        self.assertTrue(continued["review_url"].endswith("#pullrequestreview-6039203797"))
        self.assertTrue(xcl["independent_url"].endswith("#issuecomment-7133929789"))
        self.assertTrue(rounding["independent_url"].endswith("#issuecomment-7133315650"))
        self.assertTrue(rounding["review_url"].endswith("#pullrequestreview-6041873843"))
        self.assertTrue(division["independent_url"].endswith("#issuecomment-7133823866"))
        self.assertNotIn("review_url", xcl)
        self.assertTrue(all("adopted_url" not in item for item in
                            (continued, xcl, division, texture, paired_lds, lds_wait, frame_pacer)))
        self.assertTrue(rounding["adopted_url"].endswith("71d4c615c6981280b95c11290fd48ef015b5d4cb"))
        self.assertTrue(scratch_candidate["independent_url"].endswith("issuecomment-7162128623"))
        self.assertNotIn("adopted_url", scratch_candidate)
        self.assertTrue(gfx10["branch_implementation_url"].endswith("c5ca937c371d8b21e56feb36f3d009ecffe5765a"))
        self.assertNotIn("adopted_url", gfx10)
        self.assertTrue(warp["delivered_url"].endswith("/pull/144"))
        self.assertTrue(texture["delivered_url"].endswith("/issues/145"))
        self.assertEqual(paired_lds["problem_id"], "PB-0018")
        self.assertTrue(paired_lds["delivered_url"].endswith("/pull/966"))
        self.assertTrue(paired_lds["review_url"].endswith("#pullrequestreview-6042837366"))
        self.assertTrue(lds_wait["independent_url"].endswith("#issuecomment-7138695955"))
        self.assertTrue(frame_pacer["review_url"].endswith("#pullrequestreview-6044064503"))
        self.assertNotIn("independent_url", warp)
        self.assertTrue(warp["adopted_url"].endswith("becaf7829d2aa03c293e0b52125fc740c5590ea1"))
        self.assertTrue(anyxboxx["adopted_url"].endswith("b15d8821bffcd8fbc98e56f41daf07fc91118192"))
        self.assertTrue(xcl_compact["independent_url"].endswith("#issuecomment-7149592580"))
        self.assertTrue(xcl_compact["adopted_url"].endswith("aaa093657bd96a146c05c0c1a9b61149fe761453"))
        self.assertTrue(monitor["adopted_url"].endswith("1ac612868fe1392443b6f96ee06bf4341e9b8d60"))
        self.assertNotIn("independent_url", monitor)
        self.assertTrue(framelab["independent_url"].endswith("#issuecomment-7147944059"))
        self.assertNotIn("adopted_url", framelab)
        self.assertNotIn("review_url", framelab)
        reports = self.catalog.problem(framelab["problem_id"])["solutions"][0]["evidence"]
        self.assertEqual({report["url"].split("#")[-1] for report in reports},
                         {"issuecomment-7147944059", "issuecomment-7153817545"})
        self.assertEqual(build_activity(self.catalog, now=NOW, cards=[])["handoffs"]["items"], [])

    def test_handoffs_automatically_count_only_the_reviewed_head_on_merge(self):
        date = (NOW - timedelta(hours=2)).isoformat()
        fix = "66dbbf3e176880487617609547b02c98add60297"
        self.save_pr("continued", 701, at=date, status="merged", merged_at=date, revision=fix)
        self.save_pr("xcl", 1100, at=date, status="merged", merged_at=date, revision="a" * 40)
        handoffs = build_activity(self.catalog, now=NOW)["handoffs"]
        self.assertEqual(handoffs["counts"]["adopted"], 6)
        continued, xcl, *_ = handoffs["items"]
        self.assertEqual(continued["adopted_url"], continued["delivered_url"])
        self.assertNotIn("adopted_url", xcl)

    def test_opportunity_requires_reviewed_evidence_and_observed_open_target(self):
        self.assertEqual(build_activity(self.catalog, now=NOW)["opportunities"], [])
        target = self.save_pr("continued", 207, at=(NOW - timedelta(hours=2)).isoformat())
        opportunity, = build_activity(self.catalog, now=NOW)["opportunities"]
        self.assertEqual(opportunity["kind"], "reuse_test")
        self.assertEqual(opportunity["target_url"], target)
        self.assertIn("7120734503", opportunity["source_url"])
        self.assertEqual(opportunity["outcome"], "passed")
        self.assertIn("revision", opportunity["translations"]["en"]["next_step"])
        cards = self.catalog.problems()
        for card in cards:
            for solution in card["solutions"]:
                for evidence in solution["evidence"]:
                    evidence.pop("check_for", None)
        self.assertEqual(build_activity(self.catalog, now=NOW, cards=cards)["opportunities"], [])
        self.save_pr("continued", 207, at=(NOW - timedelta(hours=1)).isoformat(), status="closed")
        self.assertEqual(build_activity(self.catalog, now=NOW)["opportunities"], [])

    def test_showcase_refreshes_source_state_without_inventing_adoption(self):
        url = "https://github.com/xcl-dev/xcl/pull/2126"
        revision = "f6fa8a931eaadf925cb42dbac8024af9e3875e1b"
        row = self.observation("xcl", "pr", 2126, "XCL scratch", url,
                               {"head_sha": revision, "merged_at": "2026-11-25T13:36:36Z"})
        self.catalog.record_sync({"items": [row]})
        before = next(item for item in build_activity(self.catalog)["research"] if item["problem_id"] == "PB-0025")
        self.assertEqual(before["source_state"], "open")
        self.catalog.record_sync({"items": [{**row, "status": "merged", "updated_at": "2026-11-25T09:00:00Z"}]})
        after = next(item for item in build_activity(self.catalog)["research"] if item["problem_id"] == before["problem_id"])
        self.assertEqual(after["source_state"], "merged")
        self.assertTrue(after["independent_url"].endswith("issuecomment-7162128623"))
        self.assertNotIn("adopted_url", after)
        self.assertEqual(before["delivered_url"], after["delivered_url"])

    def test_showcase_distinguishes_branch_integration_from_merged_contribution(self):
        items = {item["problem_id"]: item for item in build_activity(self.catalog)["research"]}
        gfx10 = items["PB-0026"]
        self.assertIn("branch_implementation_url", gfx10)
        self.assertNotIn("adopted_url", gfx10)
        rounding = items["PB-0011"]
        self.assertEqual(rounding["source_url"], "https://github.com/LooperSalty/AnyXboxX/pull/133")
        self.assertIn("adopted_url", rounding)
        self.assertEqual(items["PB-0027"]["source_url"], "https://github.com/akimfomin/PortBridge/issues/58")
        self.assertNotIn("adopted_url", items["PB-0027"])

    def test_local_route_and_static_snapshot_share_the_public_payload(self):
        self.save_pr("xcl", 111, at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat())
        directory = export(self.catalog, self.workspace / "activity-site")
        snapshot = json.loads((directory / "data/activity.json").read_bytes())
        self.assertTrue(snapshot["original_research"])
        for item in snapshot["original_research"]:
            self.assertTrue(item["report_url"].startswith("https://github.com/akimfomin/PortBridge/"))
            self.assertNotIn("adopted_url", item)
            self.assertNotIn("independent_url", item)
            self.assertTrue(item["translations"]["en"]["summary"])
        with make_server(self.catalog, 0) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with closing(HTTPConnection("127.0.0.1", server.server_port, timeout=5)) as connection:
                    connection.request("GET", "/api/v1/activity")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    local = json.loads(response.read())
            finally:
                server.shutdown()
                thread.join()
        for timing_field in ("as_of", "window_start"):
            snapshot.pop(timing_field)
            local.pop(timing_field)
        self.assertEqual(local, snapshot)
