"""Offline checks for the curated catalog, localhost API and static snapshot."""

from http.client import HTTPConnection
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from xml.etree import ElementTree

from portbridge.__main__ import DEFAULT_SEED, make_server
from portbridge.backup import backup_database
from portbridge.case_pages import case_languages, case_path
from portbridge.catalog import Catalog
from portbridge.coordination import knowledge_graph, recommendations
from portbridge.export import EXPORT_FILES, export


class CatalogFixture(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix=".portbridge-test-", dir=DEFAULT_SEED.parents[2])
        self.addCleanup(directory.cleanup)
        self.workspace = Path(directory.name)
        self.db_path = self.workspace / "private" / "catalog.sqlite3"
        self.catalog = Catalog(self.db_path, DEFAULT_SEED)

    @staticmethod
    def observation(project, kind, source_id, title, url, metadata=None):
        return {
            "project": project,
            "kind": kind,
            "source_id": str(source_id),
            "title": title,
            "url": url,
            "status": "open",
            "updated_at": "2026-11-24T05:00:00+00:00",
            "metadata": metadata or {},
        }


class CatalogTest(CatalogFixture):
    def test_readable_english_overlays_preserve_curated_source_identity(self):
        for project in self.catalog.projects():
            with self.subTest(project=project["slug"]):
                self.assertTrue(project["translations"]["en"]["stack"])
        for card in self.catalog.problems():
            with self.subTest(card=card["id"]):
                self.assertEqual(case_languages(card), ("en", "ru"))
                self.assertTrue(card["translations"]["en"]["tags"])
                for solution in card["solutions"]:
                    self.assertTrue(solution["translations"]["en"]["summary"])
                    for reference in solution["source_refs"]:
                        self.assertTrue(reference["translations"]["en"]["title"])
                    for evidence in solution["evidence"]:
                        self.assertTrue(evidence["translations"]["en"]["title"])
                        self.assertTrue(evidence["translations"]["en"]["observed"])
        card, = self.catalog.problems(q="require triangle conversion")
        match, = self.catalog.matches(q="require triangle conversion")
        self.assertEqual(card["id"], match["problem_id"])
        original = card["solutions"][0]["source_refs"][0]
        self.assertEqual(match["left"]["url"], original["url"])
        self.assertEqual(match["left"]["title"], original["title"])
        self.assertEqual(match["left"]["translations"]["en"]["title"], "PR #207 by tedin7")
        coordination = self.catalog.coordination()
        self.assertEqual(len(coordination["translations"]["en"]["steps"]), len(coordination["steps"]))
        self.assertTrue(coordination["reference"]["translations"]["en"]["scope"])

    def test_seed_withdrawal_preserves_attribution_but_removes_active_references(self):
        seed = json.loads(DEFAULT_SEED.read_bytes())
        seed["problems"] = [card for card in seed["problems"] if card["id"] != "PB-0001"]
        updated_seed = self.workspace / "updated-seed.json"
        updated_seed.write_text(json.dumps(seed), encoding="utf-8")
        out = export(self.catalog, self.workspace / "snapshot")
        for _ in range(2):
            self.catalog = Catalog(self.db_path, updated_seed)
            self.assertIsNone(self.catalog.problem("PB-0001"))
            export(self.catalog, out)
            self.assertNotIn("PB-0001", (out / "data/problems.json").read_text(encoding="utf-8"))
            self.assertFalse((out / "cases/pb-0001.html").is_file())
            self.assertFalse((out / "cases/pb-0001.ru.html").is_file())
        with self.catalog.connect() as db:
            archived, = db.execute("SELECT payload FROM withdrawn_problems WHERE id='PB-0001'").fetchall()
        self.assertIn("7122193634", archived[0])

    def test_unknown_and_late_pr_updates_preserve_one_revision_change(self):
        url = "https://github.com/ubiquitarianism/leonida/pull/207"
        row = self.observation("continued", "pr", 207, "Rectangle implementation", url)
        def write(second, revision):
            self.catalog.record_sync({"items": [{**row, "updated_at": f"2026-11-24T10:00:0{second}Z",
                                                  "metadata": {"head_sha": revision}}]}, update_health=False)

        write(1, "a" * 40)
        write(2, None)
        unknown = self.catalog.observations()[0]["metadata"]
        self.assertIsNone(unknown["head_sha"])
        self.assertEqual(unknown["last_known_head_sha"], "a" * 40)
        write(3, "b" * 40)
        write(3, "b" * 40)
        write(1, "a" * 40)
        change, = self.catalog.source_changes(url=url)
        self.assertEqual((change["previous_revision"], change["revision"]), ("a" * 40, "b" * 40))
        recorded = self.catalog.problem("PB-0001")["solutions"][0]["evidence"][1]
        self.assertEqual(recorded["revision"], "21dc3889280dba49916f63342dab72750d3ee4b9")
        self.assertEqual(recorded["github"]["revision"], "b" * 40)

    def test_history_check_survives_regular_successful_sync(self):
        from portbridge.action_summary import render_report
        from portbridge.preflight import preflight

        entry = {"slug": "victory", "status": "unavailable", "next_page": 2, "warning": "GitHub rate limit"}
        states = [{"slug": project["slug"], "sync_status": "ok"} for project in self.catalog.projects()]
        self.catalog.record_sync({"items": [], "history": [entry]}, update_health=False, history_mode="backfill")
        self.catalog.record_sync({"items": [], "projects": states})
        report = preflight(self.catalog, url="https://github.com/Marvisak/VIctory/pull/641")
        self.assertEqual(report["catalog_status"], "ok")
        coverage, = report["source_coverage"]
        self.assertEqual(coverage["freshness"], "ok")
        self.assertEqual(coverage["history"]["backfill"]["warning"], "GitHub rate limit")
        self.assertIn("backfill history: unavailable", render_report(report))
        self.catalog.record_sync({"items": [], "history": [{**entry, "status": "complete", "warning": None}]},
                                 update_health=False, history_mode="backfill")
        coverage, = preflight(self.catalog, url="https://github.com/Marvisak/VIctory/pull/641")["source_coverage"]
        self.assertEqual(coverage["history"]["backfill"]["status"], "complete")
        self.assertIsNone(coverage["history"]["backfill"]["warning"])

    def test_recommendation_records_only_observed_ci_change(self):
        source = self.observation("continued", "test", 11228, "Workflow test",
                                  "https://github.com/ubiquitarianism/leonida/actions/runs/11228")
        self.catalog.record_sync({"items": [{**source, "status": "success"}]})
        self.catalog.record_sync({"items": [{**source, "status": "failure"}]})
        self.assertEqual(self.catalog.source_changes(url=source["url"])[0]["previous_status"], "success")
        changes = [row for row in recommendations(self.catalog, project="continued") if row["kind"] == "check_ci_change"]
        self.assertEqual(changes[0]["confidence"], "observed_workflow_status")
        self.catalog.record_sync({"items": [{**source, "status": "success"}]})
        self.assertFalse(any(row["kind"] == "check_ci_change" for row in recommendations(self.catalog)))
        graph = knowledge_graph(self.catalog)
        self.assertTrue(any(row["to"] == "PB-0002" and row["relationship"] == "source_port"
                            for row in graph["edges"] if row["kind"] == "technical_work"))

    def test_online_backup_reopens_and_refuses_to_replace_files(self):
        target = self.workspace / "backup.sqlite3"
        self.assertEqual(backup_database(self.db_path, target), target)
        with self.assertRaises(FileExistsError):
            backup_database(self.db_path, target)
        reopened = Catalog(target, DEFAULT_SEED)
        self.assertEqual(reopened.problems(), self.catalog.problems())

    def test_outreach_preserves_scope_and_skips_closed_discussions(self):
        drafts = {draft["problem_id"]: draft for draft in self.catalog.outreach()}
        self.assertEqual(set(drafts), {"PB-0001", "PB-0002"})
        self.assertEqual(drafts["PB-0001"]["mode"], "comparison")
        self.assertEqual(drafts["PB-0001"]["target_project"], "continued")
        self.assertIn("[PortBridge](https://github.com/akimfomin/PortBridge)", drafts["PB-0001"]["message"])
        self.assertIn("independent synthetic test", drafts["PB-0001"]["message"])
        self.assertEqual(drafts["PB-0002"]["mode"], "reference")
        self.assertIn("full automated semantic job failed", drafts["PB-0002"]["message"])
        self.assertEqual(drafts["PB-0002"]["target_status"], "unobserved")
        target = self.observation("reforge", "issue", 21, "EXEC", drafts["PB-0002"]["target_url"])
        self.catalog.record_sync({"items": [{**target, "status": "closed"}]})
        self.assertEqual([draft["problem_id"] for draft in self.catalog.outreach()], ["PB-0001"])
        self.assertIn("reviewed_symptom", {match["state"] for match in self.catalog.matches()})

    def test_real_demo_cards_have_persistent_ids_sources_and_evidence(self):
        projects = {project["slug"] for project in self.catalog.projects()}
        self.assertEqual(projects, {"continued", "reforge", "xcl", "victory",
                                    "leonida-ce", "kestrelx", "xportpc", "rebox", "scarlett-layer"})
        cards = self.catalog.problems()
        ids = [card["id"] for card in cards]
        self.assertGreaterEqual(len(ids), 3)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(Catalog(self.db_path, DEFAULT_SEED).problems(), cards)
        for card in cards:
            with self.subTest(problem=card["id"]):
                self.assertRegex(card["id"], r"^PB-\d{4,}$")
                self.assertGreaterEqual(card["project_count"], 1)
                self.assertEqual(self.catalog.problem(card["id"]), card)
                for solution in card["solutions"]:
                    self.assertIn(solution["project"], projects)
                    self.assertTrue(solution["source_refs"])
                    self.assertTrue(solution["evidence"])

        evidence = self.catalog.problem("PB-0002")["solutions"][0]["evidence"]
        by_kind = {entry["kind"]: entry for entry in evidence}
        self.assertIn("failure", by_kind["automated_test"]["observed"])
        self.assertIn("/actions/runs/", by_kind["automated_test"]["url"])
        self.assertRegex(by_kind["maintainer_claim"]["revision"], r"^[0-9a-f]{40}$")
        self.assertTrue(by_kind["source_observation"]["url"].startswith("https://github.com/"))

    def test_search_and_partial_filters_return_relevant_cards(self):
        self.assertEqual([p["id"] for p in self.catalog.problems(q="PR #20")], ["PB-0002"])
        self.assertEqual([p["id"] for p in self.catalog.problems(q="ПРЯМОУГОЛЬНИКОВ", project="continued")],
                         ["PB-0001"])
        self.assertEqual([p["id"] for p in self.catalog.problems(project="xcl")], ["PB-0004", "PB-0005", "PB-0006"])
        self.assertEqual([p["id"] for p in self.catalog.problems(status="investigating")], ["PB-0004"])
        opportunities = {p["id"] for p in self.catalog.problems(partial=True)}
        self.assertTrue({"PB-0001", "PB-0002"} <= opportunities)
        self.assertNotIn("PB-0004", opportunities)
        self.assertEqual(self.catalog.problems(q="unrelated widget"), [])

    def test_similarity_never_creates_or_links_a_reviewed_problem(self):
        original = self.catalog.problems()
        left = self.observation("continued", "issue", 1234, "Mesh allocation wave64 shared counter leaves frame clear",
                                "https://github.com/ubiquitarianism/leonida/issues/1234")
        right = self.observation("xcl", "pr", 1234, "Mesh allocation wave64 shared counter leaves frame clear",
                                 "https://github.com/ivall/xcl/pull/1234")
        self.catalog.record_sync({"items": [left, right]})
        proposals = [entry for entry in self.catalog.matches(q="shared counter") if entry["state"] == "suggested"]
        self.assertEqual(len(proposals), 1)
        suggestion = proposals[0]
        self.assertIsNone(suggestion["problem_id"])
        self.assertGreaterEqual(suggestion["score"], 0.25)
        self.assertTrue(suggestion["different_stacks"])
        self.assertEqual({suggestion["left"]["url"], suggestion["right"]["url"]}, {left["url"], right["url"]})
        self.assertEqual(self.catalog.problems(), original)
        self.assertTrue(any(item["state"] == "reviewed_same" and item["problem_id"] == "PB-0001"
                            for item in self.catalog.matches()))

    def test_metadata_upsert_and_stale_refresh_keep_last_success(self):
        entry = self.observation("continued", "test", 8787, "Semantic tests",
                                 "https://github.com/ubiquitarianism/leonida/actions/runs/8787", {"head_sha": "a" * 40})
        foreign = {**entry, "project": "unconfigured"}
        unsafe = {**entry, "source_id": "8788", "url": "https://example.invalid/test"}
        when = "2026-11-24T05:00:00+00:00"
        self.catalog.record_sync({"items": [entry, foreign, unsafe], "projects": [
            {"slug": "continued", "sync_status": "ok", "last_success": when},
        ]})
        self.catalog.record_sync({"items": [{**entry, "status": "failure"}], "projects": [
            {"slug": "continued", "sync_status": "stale", "last_success": None},
        ]})
        records = self.catalog.observations(kind="test", project="continued", limit=10)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "failure")
        self.assertEqual(records[0]["metadata"], {"head_sha": "a" * 40, "last_known_head_sha": "a" * 40})
        project = next(item for item in self.catalog.projects() if item["slug"] == "continued")
        self.assertEqual((project["sync_status"], project["last_success"]), ("stale", when))

    def test_related_looks_beyond_titles_and_keeps_direct_links_tentative(self):
        first = self.observation("continued", "pr", 301, "Wrong selection in a graphics pass",
                                 "https://github.com/ubiquitarianism/leonida/pull/301",
                                 {"technical": {"terms": ["rectangle", "d3d12"],
                                                "signals": ["ExecuteIndirect"]}})
        second = self.observation("victory", "issue", 302, "Missing draw after setup",
                                  "https://github.com/Marvisak/VIctory/issues/302",
                                  {"technical": {"terms": ["rectlist", "Direct3D12"],
                                                 "signals": ["ExecuteIndirect"]}})
        cite = self.observation("reforge", "issue", 303, "Port a tested case",
                                "https://github.com/LeonidaReforge/Leonida/issues/303",
                                {"technical": {"references": [first["url"]]}})
        unrelated = self.observation("xcl", "issue", 304, "Change a desktop setting",
                                     "https://github.com/ivall/xcl/issues/304",
                                     {"technical": {"terms": ["d3d12"]}})
        self.catalog.record_sync({"items": [first, second, cite, unrelated]})
        result = self.catalog.related(first["url"] + "#comment")
        self.assertTrue(result["indexed"])
        self.assertEqual([(entry["right"]["url"], entry["basis"], entry["state"]) for entry in result["matches"]],
                         [(cite["url"], "reference", "suggested"), (second["url"], "technical_signal", "suggested")])

    def test_source_status_does_not_overwrite_the_recorded_test_or_merge(self):
        first = self.observation("continued", "pr", 20, "Handle EXEC",
                                 "https://github.com/ubiquitarianism/leonida/pull/20", {"head_sha": "a" * 40})
        self.catalog.record_sync({"items": [{**first, "status": "merged"}], "projects": [
            {"slug": "continued", "sync_status": "ok"},
        ]})
        previous_health = self.catalog.health()
        old = {**first, "status": "closed", "metadata": {"head_sha": None},
               "updated_at": "2026-11-23T05:00:00+00:00"}
        self.catalog.record_sync({"items": [old], "warnings": ["backfill stopped"]}, update_health=False)
        card = self.catalog.problem("PB-0002")
        self.assertEqual(self.catalog.health(), previous_health)
        source = card["solutions"][0]
        self.assertEqual(source["source_refs"][0]["github"]["status"], "merged")
        self.assertEqual(source["source_refs"][0]["github"]["revision"], "a" * 40)
        ci = next(e for e in source["evidence"] if e["kind"] == "automated_test")
        self.assertEqual(ci["outcome"], "failed")
        newer = {**old, "updated_at": "2026-11-24T06:00:00Z"}
        self.catalog.record_sync({"items": [newer]}, update_health=False)
        observed = self.catalog.problem("PB-0002")["solutions"][0]["source_refs"][0]["github"]
        self.assertIsNone(observed["revision"])
        self.assertEqual(observed["status"], "merged")


class LocalAPITest(CatalogFixture):
    def setUp(self):
        super().setUp()
        self.server = make_server(self.catalog, 0)
        self.addCleanup(self.server.server_close)
        self.worker = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.03}, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.worker.join(timeout=3)

    def request(self, method, target, *, headers=None, body=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, target, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_public_reads_and_agent_preflight(self):
        status, headers, body = self.request("GET", "/api/v1")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertTrue(json.loads(body)["read_only"])

        query = urlencode({"q": "ПРЯМОУГОЛЬНИКОВ", "project": "continued", "limit": "2"})
        status, _, body = self.request("GET", f"/api/v1/preflight?{query}")
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual([p["id"] for p in result["problems"]], ["PB-0001"])
        self.assertIn("need review", result["guidance"])
        status, headers, body = self.request("HEAD", "/api/v1/problems/PB-0001")
        self.assertEqual((status, body), (200, b""))
        self.assertGreater(int(headers["Content-Length"]), 0)

        self.assertEqual(self.request("GET", "/api/v1/problems?limit=-1")[0], 400)
        self.assertEqual(self.request("GET", "/api/v1/problems/PB-9999")[0], 404)
        self.assertEqual(self.request("GET", "/api/docs")[0], 200)
        self.assertEqual(self.request("GET", "/api/v1/related?url=https://example.com")[0], 400)

    def test_modifications_and_nonlocal_host_are_rejected(self):
        original = self.catalog.problems()
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            with self.subTest(method=method):
                status, headers, body = self.request(method, "/api/v1/problems/PB-0001", body=b"{}")
                self.assertEqual(status, 405)
                self.assertEqual(headers["Allow"], "GET, HEAD")
                self.assertEqual(json.loads(body)["error"], "read-only API")
        self.assertEqual(self.request("GET", "/api/v1/projects", headers={"Host": "other.invalid"})[0], 403)
        self.assertEqual(self.catalog.problems(), original)

    def test_atom_feed_and_outreach_are_read_only_public_data(self):
        status, headers, body = self.request("GET", "/feed.xml")
        self.assertEqual(status, 200)
        self.assertIn("application/atom+xml", headers["Content-Type"])
        feed = ElementTree.fromstring(body)
        entries = feed.findall("{http://www.w3.org/2005/Atom}entry")
        ids = {entry.findtext("{http://www.w3.org/2005/Atom}id") for entry in entries}
        self.assertEqual(ids, {
            "urn:portbridge:PB-0001", "urn:portbridge:PB-0002", "urn:portbridge:PB-0005", "urn:portbridge:PB-0006",
            "urn:portbridge:PB-044801754884724660835754613454516035131",
        })
        _, _, body = self.request("GET", "/api/v1/outreach")
        self.assertEqual(json.loads(body), {"drafts": self.catalog.outreach()})
        self.assertEqual(self.request("POST", "/api/v1/outreach")[0], 405)


class SnapshotTest(CatalogFixture):
    def test_export_contains_only_public_static_files(self):
        sentinel = "PORTBRIDGE-EXPORT-SECRET-FIXTURE"
        (self.db_path.parent / ".env").write_text(f"GITHUB_TOKEN={sentinel}", encoding="utf-8")
        with patch.dict(os.environ, {"PORTBRIDGE_GITHUB_TOKEN": sentinel}):
            destination = export(self.catalog, self.workspace / "dist", "example/PortBridge")
        files = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}
        cases = {case_path(card, language) for card in self.catalog.problems() for language in case_languages(card)}
        self.assertEqual(files, EXPORT_FILES | cases)
        for name in files:
            with self.subTest(file=name):
                self.assertNotIn(sentinel.encode(), (destination / name).read_bytes())
        site = json.loads((destination / "data/site.json").read_text(encoding="utf-8"))
        self.assertEqual(site["repository"], "example/PortBridge")
        self.assertEqual(site["mode"], "snapshot")
        cards = json.loads((destination / "data/problems.json").read_text(encoding="utf-8"))
        self.assertEqual(cards["problems"], self.catalog.problems())
        base = "https://akimfomin.github.io/PortBridge/"
        english, russian = base + "cases/pb-0001.html", base + "cases/pb-0001.ru.html"
        for path, language, url, title in (
                ("cases/pb-0001.html", "en", english, "Rectangle lists require triangle conversion"),
                ("cases/pb-0001.ru.html", "ru", russian, self.catalog.problem("PB-0001")["title"])):
            with self.subTest(language=language):
                case = (destination / path).read_text(encoding="utf-8")
                self.assertIn(f'<html lang="{language}">', case)
                self.assertIn(f'rel="canonical" href="{url}"', case)
                for alternate, target in (("en", english), ("ru", russian), ("x-default", english)):
                    self.assertIn(f'rel="alternate" hreflang="{alternate}" href="{target}"', case)
                self.assertIn(f"<h1>{title}</h1>", case)
                self.assertIn("7120734503", case)
                self.assertIn("Windows 11", case)
                self.assertNotIn("<script", case)
        en_case = (destination / "cases/pb-0001.html").read_text(encoding="utf-8")
        self.assertIn("All eight rectangle cases passed in each environment.", en_case)
        self.assertIn("Independent verification · Passed", en_case)
        self.assertIn('href="pb-0001.ru.html" lang="ru" hreflang="ru"', en_case)
        ru_case = (destination / "cases/pb-0001.ru.html").read_text(encoding="utf-8")
        self.assertIn('href="../?lang=ru#/problems/PB-0001"', ru_case)
        self.assertIn('href="pb-0001.html" lang="en" hreflang="en"', ru_case)
        sitemap = ElementTree.parse(destination / "sitemap.xml")
        self.assertEqual({node.text for node in sitemap.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")},
                         {base, *(base + path for path in cases)})
        self.assertEqual(export(self.catalog, destination), destination)

    def test_export_keeps_one_default_case_for_an_untranslated_custom_card(self):
        destination = export(self.catalog, self.workspace / "dist")
        seed = json.loads(DEFAULT_SEED.read_bytes())
        card = seed["problems"][0]
        del card["translations"]
        custom_seed = self.workspace / "custom-seed.json"
        custom_seed.write_text(json.dumps(seed), encoding="utf-8")
        self.catalog = Catalog(self.db_path, custom_seed)
        export(self.catalog, destination)
        document = (destination / "cases/pb-0001.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="ru">', document)
        self.assertIn(card["title"], document)
        self.assertNotIn("hreflang", document)
        self.assertFalse((destination / "cases/pb-0001.ru.html").exists())
        self.assertNotIn("pb-0001.ru.html", (destination / "sitemap.xml").read_text(encoding="utf-8"))

    def test_export_refuses_unrelated_directory_contents(self):
        destination = self.workspace / "occupied"
        nested = destination / "data"
        nested.mkdir(parents=True)
        unrelated = nested / "keep.txt"
        unrelated.write_text("retain me", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside PortBridge"):
            export(self.catalog, destination)
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "retain me")
        self.assertFalse((destination / "index.html").exists())
        with self.assertRaisesRegex(ValueError, "outside PortBridge"):
            export(self.catalog, self.db_path.parent)


if __name__ == "__main__":
    unittest.main()
