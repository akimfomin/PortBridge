"""Contracts for source-pinned Discovery through the existing search surfaces."""

from contextlib import closing
from hashlib import sha256
from http.client import HTTPConnection
import json
import shutil
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from portbridge.__main__ import make_server
from portbridge.action_summary import summary
from portbridge.discovery_search import MAX_ENTRIES, discover, discovery_index, historical_candidates
from portbridge.export import export
from portbridge.mcp import PortBridgeMCP
from portbridge.patch_identity import compare
from portbridge.preflight import preflight, public_preflight
from test_portbridge import CatalogFixture


PR = "https://github.com/xcl-dev/xcl/pull/2322"


class DiscoverySearchTest(CatalogFixture):
    def test_all_open_investigations_have_pinned_and_localized_candidates(self):
        index = discovery_index()
        self.assertGreaterEqual(len(index["cases"]), 10)
        self.assertGreaterEqual(len({case["origin_url"].split("/")[3] for case in index["cases"]}), 5)
        self.assertLessEqual(len(index["entries"]), MAX_ENTRIES)
        for case in index["cases"]:
            with self.subTest(case=case["id"]):
                result = discover(origin_url=case["origin_url"])
                matches = {entry["id"]: entry for entry in result["matches"]}
                card = matches[case["primary"]]
                self.assertRegex(card["revision"], r"^[a-f0-9]{40}$")
                self.assertTrue(card["license"] and card["source"].startswith("https://"))
                for field in ("problem", "similarity", "differences", "limits", "adaptation", "test"):
                    self.assertTrue(card[field] and card["translations"]["ru"][field])
                self.assertTrue(all(entry["match_level"] == "candidate" for entry in matches.values()))
        unresolved = [case for case in index["cases"] if case["verdict"] == "no_transfer_found"]
        self.assertEqual(len(unresolved), 2)

    def test_exact_source_and_filters_keep_diagnostic_and_closed_states(self):
        url = "https://github.com/gfx-rs/wgpu/pull/10155"
        report = discover(url, project="wgpu", status="closed", kind="pr", platform="vulkan")
        self.assertTrue(report["matches"][0]["match"]["exact"])
        self.assertFalse(historical_candidates(report))
        self.assertFalse(discover(url, status="open")["matches"])
        archived = discover("https://github.com/KhronosGroup/Vulkan-ValidationLayers/issues/7743",
                            status="closed", kind="issue")
        self.assertTrue(archived["matches"][0]["match"]["exact"])
        self.assertFalse(historical_candidates(archived))
        revision = report["matches"][0]["revision"]
        self.assertEqual(discover(revision)["matches"][0]["id"], "wgpu-scratch-pr")
        commit_url = "https://github.com/gfx-rs/wgpu/commit/" + revision
        self.assertTrue(discover(commit_url)["matches"][0]["match"]["exact"])
        self.assertFalse(discover(url, before="2026-01-01")["matches"])
        self.assertFalse(discover("Nintendo JoyCon keyboard input repeat")["matches"])
        self.assertIsNone(discover(origin_url=PR + "#issuecomment-123")["case"])
        self.assertFalse(historical_candidates(discover("Whole quad mode")))
        with self.assertRaisesRegex(ValueError, "public HTTPS source URL"):
            discover(origin_url="https://example.com/pull/2322")
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            discover(url, after="yesterday")

    def test_discovery_reuses_preflight_without_replacing_catalog_results(self):
        report = preflight(self.catalog, url=PR)
        self.assertEqual(report["discovery"]["matches"][0]["id"], "llvm-stack-coloring")
        self.assertEqual(report["discovery"]["radar_candidates"][0]["origin_url"], PR)
        exact = preflight(self.catalog, q="PB-0011")
        self.assertEqual(exact["problems"][0]["id"], "PB-0011")
        self.assertNotIn("discovery", exact)
        self.assertNotIn("discovery", preflight(self.catalog, q="x " * 150))
        mcp = PortBridgeMCP(self.catalog).run_tool(
            {"name": "portbridge_preflight", "arguments": {"url": PR}})
        self.assertEqual(json.loads(mcp["content"][0]["text"])["discovery"]["matches"],
                         report["discovery"]["matches"])

    def test_api_and_public_export_use_the_same_reviewed_source_set(self):
        with make_server(self.catalog, 0) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with closing(HTTPConnection("127.0.0.1", server.server_port, timeout=5)) as client:
                    client.request("GET", "/api/v1/discovery?q=DXGI+adapter+LUID&project=dxvk")
                    response = client.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.loads(response.read())["matches"][0]["id"], "dxvk-adapter-luid")
                    client.request("GET", "/api/v1/discovery?q=x&q=y")
                    response = client.getresponse()
                    self.assertEqual(response.status, 400)
                    response.read()
            finally:
                server.shutdown()
                thread.join()
        site = export(self.catalog, self.workspace / "public")
        manifest = json.loads((site / "data/site.json").read_bytes())
        asset = manifest["snapshots"]["discovery"]
        payload = (site / "data" / asset).read_bytes()
        self.assertIn(sha256(payload).hexdigest()[:24], asset)
        self.assertEqual(json.loads(payload), discovery_index())

        def read(path, limit, timeout=None, revalidate=False):
            if path.startswith("data/discovery-") and broken:
                raise HTTPError(path, 404, "Fixture pub cache miss", {}, None)
            data = (site / path).read_bytes()
            self.assertLessEqual(len(data), limit)
            return json.loads(data)

        for broken, expected in ((False, "published_snapshot"), (True, "bundled_fallback")):
            with self.subTest(source=expected), patch("portbridge.preflight.read_public_file", side_effect=read):
                report = public_preflight(url=PR)
                self.assertEqual(report["discovery"]["index_source"], expected)
                self.assertEqual(report["discovery"]["matches"][0]["id"], "llvm-stack-coloring")
                self.assertEqual(public_preflight(q="PB-0011")["problems"][0]["id"], "PB-0011")

    def test_action_summary_lists_pinned_advisory_candidates(self):
        report = preflight(self.catalog, url=PR)
        with patch("portbridge.action_summary.public_pr_head", return_value="b" * 40), \
                patch("portbridge.action_summary.public_preflight", return_value=report) as client:
            output = summary({"PORTBRIDGE_PR_URL": PR, "GITHUB_EVENT_NAME": "workflow_dispatch"})
            client.assert_called_once_with(q="", url=PR, limit=5)
        self.assertIn("Historical work in other projects", output)
        self.assertIn("candidate for verification", output)
        self.assertIn("87f0227cb601", output)
        with patch("portbridge.action_summary.public_preflight") as client:
            summary({"PORTBRIDGE_PR_URL": "https://example.com/pull/1"})
            client.assert_not_called()

    @unittest.skipUnless(shutil.which("git"), "Git is required to compare patch IDs")
    def test_patch_identity_does_not_equate_different_changes(self):
        def write(name, old_line, new_line, offset=1):
            file = self.workspace / name
            file.write_text(
                "diff --git a/case.txt b/case.txt\n--- a/case.txt\n+++ b/case.txt\n"
                f"@@ -{offset} +{offset} @@\n-{old_line}\n+{new_line}\n", encoding="utf-8")
            return file

        baseline = write("first.patch", "old data", "fresh data")
        moved = write("moved.patch", "old data", "fresh data", offset=8)
        different = write("other.patch", "old data", "other data")
        self.assertTrue(compare(baseline, moved)["same_patch"])
        self.assertFalse(compare(baseline, different)["same_patch"])
