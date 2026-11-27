from datetime import datetime, timezone
import json
from unittest.mock import patch

from portbridge import code_search
from portbridge.action_summary import render_report
from portbridge.backup import backup_database, checkpoint_count
from portbridge.export import export
from portbridge.github import _technical
from portbridge.preflight import preflight, public_preflight
from portbridge.radar_scan import refresh
from portbridge.radar_store import radar_view
from portbridge.release_gate import audit
from test_portbridge import CatalogFixture


class CodeDiscoveryTests(CatalogFixture):
    url = "https://github.com/LooperSalty/AnyXboxX/pull/9991"
    ref = {"repo": "Example/Graphics", "revision": "a" * 40, "path": "tests/volume.c",
           "license": "MIT", "license_url": "https://github.com/Example/Graphics/blob/" + "a" * 40 + "/LICENSE"}
    source = b"// credential MockSensitiveRecoveryWord\nint GetDiskFreeSpaceA(int);\n"

    def setUp(self):
        super().setUp()
        pins = patch.object(code_search, "references", return_value=[self.ref])
        self.pins = pins.start()
        self.addCleanup(pins.stop)

    def test_metadata_contains_only_public_api_names(self):
        signals = _technical({"title": "Fix the volume query", "body":
                              "Use GetDiskFreeSpaceA and vkQueueSubmit.\n"
                              "PlaceholderPerson@example.test FictionalRecoveryWord123\n"
                              "secret VulkanFixturePrivate\n"}, [], {})
        self.assertEqual(signals["code_symbols"], ["GetDiskFreeSpaceA", "vkQueueSubmit"])

    def test_incremental_pins_checkpoint_and_public_preflight(self):
        fetch = lambda _: self.source
        self.assertEqual(code_search.refresh(self.catalog, fetch=fetch)["indexed"], 1)
        self.assertEqual(code_search.refresh(self.catalog, fetch=fetch)["cached"], 1)
        current = code_search.projection(self.catalog)
        self.assertNotIn("mocksensitiverecoveryword", current["files"][0]["terms"])
        self.pins.return_value = [{**self.ref, "license": "BSD-3-Clause"}]
        self.assertEqual(code_search.projection(self.catalog)["files"][0]["license"], "BSD-3-Clause")

        technical = {"discovery_cues": ["getdiskfreespacea", "creategraphicspipelinestate"]}
        row = self.observation("anyxboxx", "pr", "9991", "Fix GetDiskFreeSpaceA", self.url,
                               {"head_sha": "b" * 40, "technical": technical})
        self.catalog.record_sync({"items": [row]}, update_health=False)
        self.assertEqual(preflight(self.catalog, url=self.url)["source_code"]["matches"][0]["line"], 2)
        checkpoint = backup_database(self.db_path, self.workspace / "check.sqlite3", public_checkpoint=True)
        self.assertEqual(checkpoint_count(checkpoint), 1)
        exported = export(self.catalog, self.workspace / "site")
        self.assertFalse(audit(exported))
        with patch("portbridge.preflight.read_public_file",
                   side_effect=lambda name, *_args, **_kwargs: json.loads((exported / name).read_bytes())):
            public = public_preflight(url=self.url)
        self.assertEqual(public["source_code"]["matches"][0]["url"],
                         "https://github.com/Example/Graphics/blob/" + "a" * 40 + "/tests/volume.c#L2")
        self.assertIn("Candidate source-code lines", render_report(public))
        self.pins.return_value = [{**self.ref, "revision": "c" * 40}]
        self.assertEqual(code_search.refresh(self.catalog, fetch=lambda _: (_ for _ in ()).throw(OSError()))["indexed"], 0)
        self.assertEqual(code_search.projection(self.catalog)["files"], [])

    def test_stored_exact_api_signals_work_without_title_match(self):
        source = b"void CreateGraphicsPipelineState();\nvoid UpdateTileMappings();\nvoid vkQueueSubmit();\n"
        code_search.refresh(self.catalog, fetch=lambda _: source)
        technical = _technical({"title": "Repair dispatch on resume", "body":
                                " ".join(f"FictionalName{i}" for i in range(26)) +
                                " CreateGraphicsPipelineState UpdateTileMappings vkQueueSubmit"}, [], {})
        self.assertIn("vkQueueSubmit", technical["code_symbols"])
        row = self.observation("anyxboxx", "pr", "9991", "Repair dispatch on resume", self.url,
                               {"head_sha": "b" * 40, "technical": {**technical, "code_symbols": []}})
        self.catalog.record_sync({"items": [row]}, update_health=False)
        exported = export(self.catalog, self.workspace / "site")
        with patch("portbridge.preflight.read_public_file",
                   side_effect=lambda name, *_args, **_kwargs: json.loads((exported / name).read_bytes())):
            result = public_preflight(url=self.url)
        self.assertIn("creategraphicspipelinestate", result["source_code"]["matches"][0]["signals"])
        self.assertIn("updatetilemappings", result["source_code"]["matches"][0]["signals"])

    def test_radar_revisits_unchanged_origin_after_source_index_arrives(self):
        when = datetime.now(timezone.utc)
        row = self.observation("anyxboxx", "pr", "9991", "Fix GetDiskFreeSpaceA", self.url, {"head_sha": "b" * 40})
        row["updated_at"] = row["fetched_at"] = when.isoformat()
        self.catalog.record_sync({"items": [row]}, update_health=False)
        now = int(when.timestamp())
        self.assertEqual(refresh(self.catalog, now=now)["seen"], 1)
        self.assertEqual(refresh(self.catalog, now=now)["seen"], 0)
        code_search.refresh(self.catalog, fetch=lambda _: self.source)
        self.assertEqual(refresh(self.catalog, now=now)["seen"], 1)
        candidates = radar_view(self.catalog, now)["candidates"]
        self.assertEqual(next(row for row in candidates if row["kind"] == "source_code")["confidence"], "research")
        self.pins.return_value = []
        refresh(self.catalog, now=now)
        self.assertFalse(any(row["kind"] == "source_code" and row["state"] != "stale"
                             for row in radar_view(self.catalog, now)["candidates"]))
