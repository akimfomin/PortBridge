"""URL-only Discovery, bounded retrieval and observations saved by M5.1."""

import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from portbridge.discovery_scan import cached_index, lookup_plan, scan, search_link, subject
from portbridge.discovery_search import discover
from portbridge.github import SIGNATURE_VERSION, Unavailable, _item, _technical
from test_portbridge import CatalogFixture


PR = "https://github.com/xcl-dev/xcl/pull/71"
EXTERNAL = "https://github.com/gfx-rs/wgpu/pull/600"
PEER = "https://github.com/ubiquitarianism/leonida/pull/23"
REV = "a" * 40


def metadata(body, *, title="Fix backend", revision=REV):
    return {"number": 71, "title": title, "body": body, "state": "open", "head": {"sha": revision},
            "updated_at": "2026-11-26T11:00:00Z"}


class DiscoveryLinkTests(CatalogFixture):
    def setUp(self):
        super().setUp()
        self.project = next(p for p in self.catalog.projects() if p["repo"].lower() == "xcl-dev/xcl")

    def test_title_body_and_real_v4_sqlite_roundtrip(self):
        for api in ("vkQueueSubmit", "CreateGraphicsPipelineState"):
            for entry in (metadata("", title=api), metadata(api)):
                row = _item(entry, "pr", self.project, {})
                self.assertEqual(subject(row), api.casefold())
            sig = row["metadata"]["technical"] = {"version": 4, "signals": [api.casefold()], "terms": []}
            self.catalog.record_sync({"items": [row]}, update_health=False)
            saved = self.catalog.observations(kind="pr")[0]
            self.assertEqual(saved["metadata"]["technical"], sig)
            self.assertEqual(subject(saved), api.casefold())
        old = {"title": "Fix backend", "metadata": {"technical": {"version": 4, "signals":
               ["irrelevant"] * 48 + ["vkqueuesubmit"]}}}
        self.assertEqual(subject(old), "vkqueuesubmit")

    def test_extraction_is_bounded_and_does_not_retain_prose_or_url_symbols(self):
        body = "https://example.org/vkSecretCall no raw-private-prose D3D12_TILE_RANGE_FLAG_NULL via UpdateTileMappings"
        sig = _technical(metadata(body), [], {})
        self.assertEqual(sig["discovery_cues"], ["updatetilemappings", "d3d12_tile_range_flag_null"])
        self.assertNotIn("updatetilemappings", sig["signals"])
        self.assertNotIn("raw-private-prose", json.dumps(sig))
        long_token = "R" + "1" * 400 + "G2B3E4"
        self.assertFalse(_technical(metadata(long_token), [], {})["discovery_cues"])
        self.assertFalse(subject({"title": long_token, "metadata": {}}))

    def test_merged_explicit_pr_uses_one_search_and_does_not_pollute_catalog_references(self):
        data = metadata("D3D12_TILE_RANGE_FLAG_NULL via UpdateTileMappings. " + PEER)
        data.update(state="closed", merged_at="2026-11-26T11:02:00Z")
        calls = []
        def request(path, resource, etag):
            calls.append(resource)
            if resource == "core":
                return data, {}
            params = parse_qs(urlsplit(path).query)
            self.assertIn('"updatetilemappings"', params["q"][0])
            self.assertEqual(params["per_page"], ["15"])
            return {"items": [{"html_url": EXTERNAL, "state": "closed", "title": "Tiled image remapping"}]}, {}
        with patch("portbridge.github._Sync._request", side_effect=request):
            result = search_link(self.catalog, PR)
            repeat = search_link(self.catalog, PR)
        self.assertEqual(calls, ["core", "search"])
        self.assertEqual((result["lookups"], repeat["lookups"], repeat["cache_hits"]), (1, 0, 1))
        self.assertEqual(result["top5"][0]["url"], EXTERNAL)
        row = self.catalog.observations(kind="pr")[0]
        self.assertEqual(row["metadata"]["technical"]["references"],
                         ["https://github.com/ProjectLeonida/mandy/pull/23"])
        self.assertFalse(lookup_plan([row], {self.project["repo"].lower()}))
        self.assertEqual(discover(origin_url=PR, index=cached_index(self.catalog))["subject"], result["subject"])

    def test_revised_cueless_source_clears_saved_hits_even_before_a_new_search(self):
        with patch("portbridge.github._Sync._request", side_effect=[
            (metadata("vkQueueSubmit"), {}),
            ({"items": [{"html_url": EXTERNAL, "state": "open", "title": "Queue ordering"}]}, {}),
        ]):
            self.assertTrue(search_link(self.catalog, PR)["top5"])
        newer = metadata("Typo fixes only", revision="b" * 40)
        self.catalog.record_sync({"items": [_item(newer, "pr", self.project, {})]}, update_health=False)
        replay = discover(origin_url=PR, index=cached_index(self.catalog))
        self.assertEqual((replay["scan_status"], replay["automatic_matches"]), ("no_subject", []))
        with self.catalog.connect() as db:
            db.execute("UPDATE github_cache SET fetched_at=0")
        with patch("portbridge.github._Sync._request", return_value=(newer, {})) as core:
            result = search_link(self.catalog, PR)
            core.assert_called_once()
        self.assertEqual((result["status"], result["lookups"], result["top5"]), ("no_subject", 0, []))
        self.assertEqual(discover(origin_url=PR, index=cached_index(self.catalog))["scan_status"], "no_subject")

    def test_old_cache_without_enum_refetches_without_etag_and_captures_lost_body_signal(self):
        old = _item(metadata(""), "pr", self.project, {})
        old["metadata"]["technical"] = {"version": 4, "signals": [], "terms": []}
        with patch("portbridge.github._Sync._request", return_value=(metadata(""), {"ETag": '"old"'})):
            search_link(self.catalog, PR)
        with self.catalog.connect() as db:
            db.execute("UPDATE github_cache SET items=?", (json.dumps([old]),))
        with patch("portbridge.github._Sync._request", side_effect=[
            (metadata("D3D12_TILE_RANGE_FLAG_NULL"), {}), ({"items": []}, {}),
        ]) as requester:
            result = search_link(self.catalog, PR)
        self.assertIsNone(requester.call_args_list[0].args[2])
        self.assertEqual(result["subject"], "d3d12_tile_range_flag_null")
        self.assertEqual(result["lookups"], 1)
        self.assertEqual(self.catalog.observations(kind="pr")[0]["metadata"]["technical"]["version"], SIGNATURE_VERSION)

    def test_untracked_pr_is_scoped_and_transport_failure_is_distinct_from_no_hits(self):
        url = "https://github.com/example/graphics/pull/71"
        with patch("portbridge.github._Sync._request", side_effect=[
            (metadata("vkQueueSubmit"), {}), Unavailable("budget paused", reason="rate_limit", attempted=False),
        ]):
            result = search_link(self.catalog, url)
        self.assertEqual((result["status"], result["search_issue"], result["lookups"]), ("unavailable", "rate_limit", 0))
        self.assertIn("rate_limit", result["explanation"])
        self.assertEqual(discover(origin_url=url, index=cached_index(self.catalog))["scan_status"], "unavailable")
        self.assertNotIn("example/graphics", [p["repo"] for p in self.catalog.projects()])
        with patch("portbridge.github._Sync._request") as request:
            with self.assertRaises(ValueError):
                search_link(self.catalog, "https://other.test/x/y/pull/71")
            request.assert_not_called()
        with patch("portbridge.github._Sync._request", side_effect=Unavailable("missing", reason="not_public")):
            failed = search_link(self.catalog, "https://github.com/example/graphics/pull/72")
        self.assertEqual((failed["status"], failed["lookups"], failed["top5"]), ("not_public", 0, []))

    def test_automatic_self_match_is_not_registered_as_evidence_or_returned(self):
        url = "https://github.com/KytyPS5/KytyPS5/pull/71"
        row = {"url": url, "title": "vkQueueSubmit", "metadata": {}, "status": "open"}
        with patch("portbridge.discovery_scan.fetch", return_value=("available", [{"url": url, "source": url}])), \
                patch("portbridge.discovery_scan.remember_discovery") as remember:
            report = scan(self.catalog, [row], online=True, requested_url=url)
        self.assertEqual(remember.call_args.args[2], [])
        self.assertFalse(report["origins"][0]["matches"])
        self.assertFalse(discover(origin_url=url, index=cached_index(self.catalog))["automatic_matches"])
