"""M2.1 discovery boundaries and bounded incremental lookup."""

import json
from pathlib import Path
import time
from unittest.mock import patch

from portbridge.action_summary import summary
from portbridge.discovery_scan import cached_index, scan
from portbridge.discovery_search import SOURCE_FOUND, discover, historical_candidates
from portbridge.github import Unavailable
from portbridge.preflight import public_preflight
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
        self.assertIn("per_page=5", requested_url)
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
