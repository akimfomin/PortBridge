from datetime import datetime, timezone
from hashlib import sha1
from unittest.mock import Mock
import json
from unittest.mock import patch

from portbridge import code_search, source_corpus
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
        snapshot = json.loads((exported / "data/discovery.json").read_bytes())
        self.assertEqual(snapshot["code_candidates"]["github.com/loopersalty/anyxboxx/pull/9991"][0]["line"], 2)
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

    def test_reuse_verified_blob_at_new_revision(self):
        blob = sha1(b"blob " + str(len(self.source)).encode("ascii") + b"\0" + self.source).hexdigest()
        self.pins.return_value = [{**self.ref, "blob": blob}]
        self.assertEqual(code_search.refresh(self.catalog, fetch=lambda _: self.source)["indexed"], 1)
        next_ref = {**self.pins.return_value[0], "revision": "b" * 40,
                    "license_url": self.ref["license_url"].replace("a" * 40, "b" * 40)}
        self.pins.return_value = [next_ref]
        fetch = Mock(side_effect=OSError())
        status = code_search.refresh(self.catalog, fetch=fetch)
        fetch.assert_not_called()
        self.assertEqual((status["indexed"], status["reused_blobs"]), (0, 1))
        rows = code_search.projection(self.catalog)["files"]
        self.assertEqual((rows[0]["revision"], rows[0]["blob"]), ("b" * 40, blob))
        self.pins.return_value = [{**next_ref, "blob": "c" * 40}]
        self.assertEqual(code_search.projection(self.catalog)["files"], [])
        self.assertEqual(code_search.refresh(self.catalog, fetch=lambda _: self.source)["errors"][0]["reason"], "ValueError")

    def test_validation_rule_from_body_picks_exact_assertion(self):
        origin = "Fix graphics validation in an edge case"
        rule = "VUID-vkQueueSubmit-pSubmits-00001"
        other = "VUID-vkQueueSubmit-pSubmits-00002"
        fixture = f'void vkQueueSubmit();\nassert_diagnostic("{other}");\nassert_diagnostic("{rule}");\n'.encode()
        technical = _technical({"title": origin, "body": f"Observed {rule}"}, [], {})
        self.assertEqual(technical["code_diagnostics"], [rule.lower()])
        code_search.refresh(self.catalog, fetch=lambda _: fixture)
        row = self.observation("anyxboxx", "pr", "9991", origin, self.url, {"technical": technical})
        self.catalog.record_sync({"items": [row]}, update_health=False)
        result = preflight(self.catalog, url=self.url)
        self.assertEqual(result["source_code"]["matches"][0]["line"], 3)
        index = code_search.projection(self.catalog)
        self.assertFalse(code_search.lookup(index, "Fix VUID-vkQueueSubmit-pSubmits-00003"))
        old = code_search.index_file(self.ref, b"void vkQueueSubmit();")
        generic = code_search.lookup({"version": 2, "files": [old]}, f"vkQueueSubmit {rule}")
        self.assertIn("diagnostic ID was not found", generic[0]["next_step"])
        peer = {**old, "repo": "Elsewhere/Graphics", "license_url":
                self.ref["license_url"].replace("Example/Graphics", "Elsewhere/Graphics")}
        fallback = code_search.lookup({**index, "files": [*index["files"], peer]}, f"vkQueueSubmit {rule}",
                                      origin_url="https://github.com/Example/Graphics/issues/1")
        self.assertEqual(fallback[0]["repo"], "Elsewhere/Graphics")
        self.assertIn("diagnostic ID was not found", fallback[0]["next_step"])

    def test_scope_selects_only_regular_bounded_source_files(self):
        group = {"directories": ["gpu"], "limit": 2}
        entry = {"type": "blob", "mode": "100644", "size": 200, "sha": "a" * 40}
        raw = {"truncated": False, "tree": [
            {**entry, "path": "gpu/fence.cpp"},
            {**entry, "path": "gpu/queue.cpp"},
            {**entry, "path": "gpu/memory.cpp", "size": 1_200_000},
            {**entry, "path": "gpu/vendor/heap.cpp"},
            {**entry, "path": "gpu/shader.cpp", "mode": "120000"},
            {**entry, "path": "core/source_buffer.cpp"},
            {**entry, "path": "gpu/../memory.cpp"},
        ]}
        self.assertEqual({row["path"] for row in source_corpus.select(group, raw)},
                         {"gpu/fence.cpp", "gpu/queue.cpp"})
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            source_corpus.select(group, {**raw, "truncated": True})

    def test_issue_timing_ignores_shared_status_code(self):
        row = code_search.index_file(self.ref, b"int vkQueueSubmit2(void) {\n return VK_ERROR_DEVICE_LOST;\n}\n")
        index = {"version": code_search.SCHEMA_VERSION, "files": [row]}
        query = "Frame timing regression on vendor driver\nvkQueueSubmit2 VK_ERROR_DEVICE_LOST"
        self.assertFalse(code_search.lookup(index, query, origin_url=self.url))
        present_modes = "VK_PRESENT_MODE_FIFO_KHR VK_PRESENT_MODE_MAILBOX_KHR"
        row = code_search.index_file(self.ref, present_modes.encode())
        unrelated = {"version": code_search.SCHEMA_VERSION, "files": [row]}
        self.assertFalse(code_search.lookup(unrelated, "FPS regression\n" + present_modes, origin_url=self.url))
        self.assertEqual(code_search.lookup(index, "vkQueueSubmit2")[0]["line"], 1)
        self.assertEqual(code_search.lookup(index, "Implement vkQueueSubmit2", origin_url=self.url)[0]["line"], 1)

    def test_scoped_tree_walk_uses_only_the_approved_path(self):
        repo = "Example/Graphics"
        group = {"repo": repo, "revision": "a" * 40, "scoped": True, "directories": ["external/core"], "limit": 2}
        trees = [
            {"tree": [{"type": "tree", "path": "external", "sha": "b" * 40}]},
            {"tree": [{"type": "tree", "path": "core", "sha": "c" * 40}]},
            {"tree": [{"type": "blob", "path": "memory.cpp", "sha": "d" * 40,
                       "size": 20, "mode": "100644"}]},
        ]
        with patch.object(source_corpus, "_fetch_tree", side_effect=trees) as fetch:
            selected = source_corpus.select(group, source_corpus.fetch_tree(group))
        self.assertEqual([call.kwargs["recursive"] for call in fetch.call_args_list], [False, False, True])
        self.assertEqual(selected, [{"path": "external/core/memory.cpp", "blob": "d" * 40}])

    def test_empty_scope_is_retryable_and_not_counted_as_complete(self):
        group = {"repo": "Example/Graphics", "revision": "a" * 40, "license": "MIT", "license_path": "LICENSE",
                 "files": [], "directories": ["approved"], "limit": 2}
        fetch = Mock(return_value={"tree": [], "truncated": False})
        with patch.object(code_search, "_manifest", return_value=[group]):
            _, errors = code_search._discover_scopes(self.catalog, fetch)
            self.assertEqual(errors, [{"scope": group["repo"], "reason": "ValueError"}])
            code_search._discover_scopes(self.catalog, fetch)
        self.assertEqual(fetch.call_count, 2)

    def test_embedded_shader_keeps_standard_subgroup_names_only(self):
        literal = (b'// gl_SubgroupID gl_SubgroupInvocationID\n'
                   b'/* example shader "gl_SubgroupID gl_SubgroupInvocationID" */\n'
                   b'std::string shader = "gl_SubgroupID gl_SubgroupInvocationID OtherLiteralContent";')
        row = code_search.index_file(self.ref, literal)
        self.assertNotIn("otherliteralcontent", row["terms"])
        symbols = code_search.public_symbols(
            "The pair gl_SubgroupID gl_SubgroupInvocationID. https://example.test/gl_SubgroupSize"
        )
        self.assertEqual(symbols, ["gl_SubgroupID", "gl_SubgroupInvocationID"])
        index = {"version": code_search.SCHEMA_VERSION, "files": [row]}
        self.assertEqual(code_search.lookup(index, " ".join(symbols), origin_url=self.url)[0]["line"], 3)

    def test_diagnostic_keeps_a_corroborated_shader_fixture(self):
        diagnostic = "VUID-vkCmdDraw-None-00001"
        values = "gl_SubgroupID gl_SubgroupInvocationID"
        documentation = code_search.index_file({**self.ref, "path": "docs/shaders.adoc"},
                                               f"* {diagnostic}\n".encode())
        fixture = code_search.index_file(self.ref, f'const char *shader = "{values}";'.encode())
        index = {"version": code_search.SCHEMA_VERSION, "files": [fixture, documentation]}
        results = code_search.lookup(index, f"Check subgroup output\n{diagnostic} {values}", origin_url=self.url)
        self.assertEqual([row["path"] for row in results], ["docs/shaders.adoc", self.ref["path"]])
