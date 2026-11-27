"""M2.1 discovery boundaries and bounded incremental lookup."""

import json
from pathlib import Path
import time
from unittest.mock import patch

from portbridge.__main__ import DEFAULT_SEED
from portbridge.action_summary import summary
from portbridge.backup import backup_database, checkpoint_count
from portbridge.catalog import Catalog
from portbridge.discovery_scan import cached_index, link_result, scan
from portbridge.discovery_search import SOURCE_FOUND, discover, historical_candidates
from portbridge.github import Unavailable
from portbridge.preflight import preflight, public_preflight
from test_portbridge import CatalogFixture

PR = "https://github.com/xcl-dev/xcl/pull/2322"
NEW = "https://github.com/xcl-dev/xcl/pull/2697"
EXTERNAL = "https://github.com/gfx-rs/wgpu/pull/11065"


class DiscoveryIncrementalTest(CatalogFixture):
    def observation(self, url=NEW, title="DXGI memory budget"):
        return {"url": url, "title": title, "status": "open", "metadata": {},
                "updated_at": "2026-11-26T06:48:52Z"}

    def response(self, requested_url, resource, etag):
        self.assertTrue(requested_url.startswith("https://api.github.com/search/issues?"))
        self.assertIn("is%3Apublic", requested_url)
        self.assertIn("per_page=15", requested_url)
        row = {"html_url": EXTERNAL, "title": "Memory budget in Vulkan", "state": "open",
               "updated_at": "2026-11-25T00:00:00Z"}
        return {"items": [row, row, {**row, "html_url": "https://github.com/other/private/issues/1"}]}, {}

    def test_old_false_matches_cannot_become_recommendations(self):
        fixture = json.loads((Path(__file__).with_name("fixtures") / "discovery-holdout-v1.json").read_bytes())
        count = 0
        for question in fixture["queries"]:
            result = discover(question["q"])
            count += sum(row["id"] in question["hard_negatives"] for row in result["matches"])
            self.assertFalse(result["technical_recommendations"], question["id"])
            self.assertFalse(historical_candidates(result), question["id"])
        self.assertEqual(count, 5)
        report = discover(origin_url=PR)
        self.assertEqual([x["id"] for x in report["technical_recommendations"]], ["llvm-stack-coloring"])
        self.assertEqual(len(historical_candidates(report)), 1)
        old_url = PR.replace("xcl-dev/", "ivall/")
        self.assertEqual(historical_candidates(discover(old_url)), historical_candidates(report))
        for row in report["matches"]:
            expected = "potentially_applicable" if row["id"] == "llvm-stack-coloring" else SOURCE_FOUND
            self.assertEqual(row["evidence_status"], expected)
        self.assertFalse(historical_candidates(discover("scratch hlsl unrelated case", origin_url=PR)))
        self.assertFalse(historical_candidates(discover(origin_url="https://github.com/LooperSalty/AnyXboxX/issues/264")))

    def test_one_shared_query_is_deduplicated_and_readable_without_network(self):
        second = "https://github.com/xcl-dev/xcl/issues/2690"
        observations = [self.observation(), self.observation(), self.observation(second),
                        self.observation("https://github.com/unconfigured/project/issues/1")]
        with patch("portbridge.discovery_scan._Sync._request", side_effect=self.response) as fetch:
            self.assertEqual(scan(self.catalog, observations)["status"], "offline")
            fetch.assert_not_called()
            report = scan(self.catalog, observations, online=True, max_lookups=1)
            self.assertEqual((report["eligible"], report["lookups"], report["cache_hits"]), (2, 1, 1))
            fetch.assert_called_once()
            replay = scan(self.catalog, observations, online=True, max_lookups=1)
            self.assertEqual((replay["lookups"], replay["cache_hits"]), (0, 2))
            fetch.assert_called_once()
        for url in (NEW, second):
            report = discover(origin_url=url, index=cached_index(self.catalog))
            self.assertEqual([x["source"] for x in report["automatic_matches"]], [EXTERNAL])
            self.assertEqual(report["automatic_matches"][0]["evidence_status"], SOURCE_FOUND)
            self.assertFalse(historical_candidates(report))
        with self.catalog.connect() as db:
            db.execute("UPDATE discovery_query SET retry_at=?",(time.time()-60,))
        with patch("portbridge.discovery_scan._Sync._request", side_effect=Unavailable("paused", reason="rate_limit")) as fetch:
            self.assertEqual(scan(self.catalog, observations, online=True)["status"], "rate_limit")
            fetch.assert_called_once()
            report = scan(self.catalog, observations, online=True)
            self.assertEqual(report["lookups"], 0)
            fetch.assert_called_once()
        report = discover(origin_url=NEW, index=cached_index(self.catalog))
        self.assertEqual(report["scan_status"], "stale")
        self.assertEqual(report["automatic_matches"][0]["source"], EXTERNAL)
        self.assertFalse(historical_candidates(report))

    def test_scheduled_queue_survives_checkpoint_without_public_projection_limit(self):
        observations = [self.observation(f"https://github.com/xcl-dev/xcl/pull/{number}")
                        for number in range(3000, 3130)]
        target = observations[0]["url"]
        with patch("portbridge.discovery_scan.fetch", return_value=("available", [{"url": EXTERNAL}])) as fetch:
            first = scan(self.catalog, observations, online=True, max_lookups=1, scheduled=True)
            self.assertEqual(first["queue"], {"jobs": 130, "ready": 10, "pending": 10})
            self.assertEqual(first["lookups"], 1)
            backup = self.catalog.path.with_name("checkpoint-discovery.sqlite3")
            backup_database(self.catalog.path, backup, public_checkpoint=True)
            self.assertEqual(checkpoint_count(backup), 0)
            restored = Catalog(backup, DEFAULT_SEED)
            second = scan(restored, observations, online=True, max_lookups=1, scheduled=True)
            self.assertEqual(second["queue"], {"jobs": 130, "ready": 0, "pending": 0})
            self.assertEqual(second["lookups"], 0)
            fetch.assert_called_once()
        public = cached_index(restored)["automatic"]
        self.assertEqual(len(public), 64)
        self.assertNotIn(target.removeprefix("https://"), public)
        self.assertEqual(preflight(restored, url=target)["discovery"]["scan_status"], "available")
        with restored.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM discovery_observation").fetchone()[0], 130)

    def test_scheduled_queue_advances_past_backoff_and_enqueues_changed_revision(self):
        other = self.observation(NEW.replace("2697", "2698"), title="vkQueueSubmit")
        first, second = self.observation(), other
        response = ("available", [])
        with patch("portbridge.discovery_scan.fetch", side_effect=[
                Unavailable("paused", reason="rate_limit"), response, response]) as fetch:
            failure = scan(self.catalog, [first, second], online=True, max_lookups=1, scheduled=True)
            self.assertEqual(failure["status"], "rate_limit")
            self.assertEqual(failure["queue"], {"jobs": 2, "ready": 1, "pending": 2})
            progress = scan(self.catalog, [first, second], online=True, max_lookups=1, scheduled=True)
            self.assertEqual([origin["url"] for origin in progress["origins"]], [other["url"]])
            self.assertEqual(progress["queue"], {"jobs": 2, "ready": 0, "pending": 1})
            newer = {**other, "updated_at": "2026-11-27T00:00:00Z", "title": "vkQueueWaitIdle"}
            refresh = scan(self.catalog, [newer], online=True, max_lookups=1, scheduled=True)
            self.assertEqual(refresh["queue"], {"jobs": 1, "ready": 0, "pending": 0})
            self.assertEqual(refresh["origins"][0]["query"], "vkqueuewaitidle")
            self.assertEqual(fetch.call_count, 3)

    def test_interactive_lookup_keeps_the_full_scheduled_result(self):
        row = self.observation()
        packages = [{"html_url": f"https://github.com/gfx-rs/wgpu/pull/{number}", "title": "GPU fixture",
                     "state": "open", "updated_at": row["updated_at"]} for number in range(1, 16)]
        with patch("portbridge.discovery_scan._Sync._request", return_value=({"items": packages}, {})) as fetch:
            self.assertEqual(scan(self.catalog, [row], online=True, scheduled=True)["lookups"], 1)
            interactive = link_result(self.catalog, row)
            self.assertEqual((interactive["lookups"], interactive["cache_hits"], len(interactive["top5"])), (0, 1, 5))
            fetch.assert_called_once()
        results = cached_index(self.catalog, origin_urls=[row["url"]])["automatic"]
        key = row["url"].removeprefix("https://")
        self.assertEqual(len(results[key]["matches"]), 15)
        self.assertEqual(len(cached_index(self.catalog)["automatic"][key]["matches"]), 5)
        self.assertEqual(scan(self.catalog, [row], online=True, scheduled=True)["queue"]["ready"], 0)

    def test_scheduled_queue_leaves_generic_crash_search_to_explicit_requests(self):
        symptom = self.observation(title="DXGI_ERROR_DEVICE_HUNG")
        mechanism = self.observation(NEW.replace("2697", "2698"), title="DXGI_ERROR_DEVICE_HUNG")
        mechanism["metadata"] = {"technical": {"discovery_cues": ["vkqueuesubmit"]}}
        with patch("portbridge.discovery_scan.fetch", return_value=("available", [])) as fetch:
            planned = scan(self.catalog, [symptom, mechanism], online=True, scheduled=True)
            self.assertEqual((planned["eligible"], planned["origins"][0]["query"]), (1, "vkqueuesubmit"))
            self.assertEqual(planned["queue"]["jobs"], 1)
            explicit = link_result(self.catalog, symptom)
            self.assertEqual((explicit["subject"], explicit["lookups"]), ("dxgi_error_device_hung", 1))
            self.assertEqual(fetch.call_count, 2)

    def test_public_snapshot_outage_uses_only_the_reviewed_bundle(self):
        with patch("portbridge.preflight.read_public_file", side_effect=OSError("offline")):
            report = public_preflight(url=PR)
            self.assertEqual(report["discovery"]["index_source"], "bundled_fallback")
            self.assertEqual(report["discovery"]["technical_recommendations"][0]["id"], "llvm-stack-coloring")
            self.assertFalse(report["discovery"]["automatic_matches"])
            with patch("portbridge.action_summary.public_pr_head", return_value="b" * 40):
                result = summary({"PORTBRIDGE_PR_URL": PR, "GITHUB_EVENT_NAME": "workflow_dispatch"})
            self.assertIn("bundled sources", result)
            self.assertIn("potentially applicable", result)
            self.assertNotIn("First check", result)
