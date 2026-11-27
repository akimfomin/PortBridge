"""M1 regression replay against local SQLite, public contracts and simulated GitHub transport."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from email.message import Message
from hashlib import sha256
from http.client import HTTPConnection
from io import BytesIO
import json
import os
import subprocess
import sys
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from portbridge import github
from portbridge.__main__ import DEFAULT_SEED, make_server
from portbridge.backup import backup_database, checkpoint_count
from portbridge.catalog import Catalog
from portbridge.coordination import knowledge_graph
from portbridge.ecosystem import build_ecosystem, refresh_ecosystem
from portbridge.export import export
from portbridge.identity import evidence_fields, repository_id, source_id
from portbridge.lab import build_lab
from portbridge.mcp import PortBridgeMCP
from portbridge.pages_health import publication_guard, verify_linked_snapshots
from portbridge.preflight import preflight
from portbridge.source_context import refresh_context
from portbridge.source_health import health_freshness
from test_portbridge import CatalogFixture


NOW = datetime(2026, 11, 26, 8, tzinfo=timezone.utc)
STAMP = (NOW - timedelta(hours=3)).isoformat()
REVISION = "a" * 40


class Response(BytesIO):
    def __init__(self, payload, headers=None):
        super().__init__(json.dumps(payload).encode())
        self.status = 200
        self.headers = headers or {}


def http_error(code, **headers):
    message = Message()
    for key, value in headers.items():
        message[key.replace("_", "-")] = str(value)
    return HTTPError("https://api.github.com/repos/example/project", code, "fixture", message, BytesIO())


def payload(path):
    if "/issues?" in path:
        return [{"number": 101, "state": "open", "title": "Bounded public issue", "updated_at": STAMP,
                 "user": {"id": 11, "login": "tester"}}]
    if "/actions/runs?" in path:
        return {"workflow_runs": []}
    return []


class M1RecoveryTest(CatalogFixture):
    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {"PORTBRIDGE_GITHUB_TOKEN": "", "GITHUB_TOKEN": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.project = next(row for row in self.catalog.projects() if row["slug"] == "continued")

    def collect(self, catalog, mock_read, at):
        project = next(row for row in catalog.projects() if row["slug"] == "continued")
        with patch.object(github, "build_opener") as opener, patch.object(github.time, "sleep"), \
                patch.object(github.time, "time", return_value=at.timestamp()):
            requests = opener.return_value.open
            requests.side_effect = mock_read
            result = github.collect([project], catalog.path, refresh=True)
        catalog.record_sync(result)
        return result, requests.call_count

    def test_failure_replay_cache_eviction_and_checkpoint_restore(self):
        def healthy(request, timeout):
            self.assertGreater(timeout, 0)
            return Response(payload(request.full_url))

        baseline, calls = self.collect(self.catalog, healthy, NOW - timedelta(hours=3))
        self.assertEqual((len(baseline["items"]), calls), (1, 4))
        with patch.object(github._Sync, "_request", return_value=(payload("/issues?"), {})):
            history = github.backfill([self.project], self.db_path)
        self.catalog.record_sync(history, update_health=False, history_mode="backfill")
        github.commit_backfill(self.db_path, history["checkpoint"])
        original_cursor = github.backfill_status(self.db_path)
        self.assertTrue(original_cursor[0]["complete"])
        backup = backup_database(self.catalog.path, self.workspace / "backup.sqlite3")
        self.assertEqual(checkpoint_count(backup), 1)

        for label, failing, expected_reason, max_calls in (
            ("connection", lambda: URLError("offline"), "connection", 4),
            ("timeout", TimeoutError, "timeout", 4),
            ("server", lambda: http_error(503), "github_unavailable", 8),
            ("rate-429", lambda: http_error(429, Retry_After=60), "rate_limit", 1),
            ("rate-403", lambda: http_error(403, X_RateLimit_Remaining=0,
                                            X_RateLimit_Reset=int(NOW.timestamp()) + 60), "rate_limit", 1),
        ):
            with self.subTest(label=label):
                restored = self.workspace / (label + ".sqlite3")
                backup_database(backup, restored)
                candidate = Catalog(restored, DEFAULT_SEED)
                with candidate.connect() as db:
                    db.execute("DELETE FROM github_cache")
                def unavailable(request, timeout):
                    raise failing()

                failure, calls = self.collect(candidate, unavailable, NOW)
                self.assertLessEqual(calls, max_calls)
                self.assertEqual(failure["projects"][0]["sources"]["issue"]["errors"][0]["reason"], expected_reason)
                report = candidate.health(now=NOW)
                self.assertEqual((report["observation_count"], report["last_success"]), (1, STAMP))
                continued = next(row for row in report["sources"] if row["slug"] == "continued")
                self.assertEqual(continued["kinds"]["issue"]["last_success"], STAMP)
                self.assertEqual(continued["age_state"], "stale")
                self.assertTrue(publication_guard(1, report)[0])
                restart, calls = self.collect(candidate, healthy, NOW + timedelta(minutes=2))
                self.assertEqual(calls, 4)
                self.assertEqual(len(restart["items"]), 1)
                self.assertEqual(candidate.health()["observation_count"], 1)
                self.assertEqual(github.backfill_status(restored), original_cursor)
                self.assertEqual(candidate.source_changes(), [])
        self.assertFalse(publication_guard(1, {"observation_count": 0})[0])
        self.assertFalse(publication_guard(None, {"observation_count": 1})[0])
        invalid = self.workspace / "invalid.sqlite3"
        backup_database(backup, invalid)
        with Catalog(invalid, DEFAULT_SEED).connect() as db:
            db.execute("CREATE TABLE private_exchange(token TEXT)")
        with self.assertRaisesRegex(ValueError, "unexpected table"):
            checkpoint_count(invalid)

    def test_unavailable_source_does_not_starve_another_project(self):
        seed_path = self.workspace / "queue.json"
        seed_path.write_text(json.dumps({"problems": [], "projects": [
            {"slug": slug, "repo": f"example/{slug}", "url": f"https://github.com/example/{slug}"}
            for slug in ("a-busy", "b-missing", "c-small", "d-small", "e-small")
        ]}), encoding="utf-8")
        catalog = Catalog(self.workspace / "queue.sqlite", seed_path)
        selection = []
        for minute in range(10):
            first = []

            def window(project, kind, page):
                slug = project["slug"]
                if not first:
                    first.append(slug)
                if slug != first[0]:
                    return [], False, "error", None, github.Unavailable("budget exhausted", reason="budget",
                                                                         attempted=False)
                if slug == "b-missing":
                    return [], False, "error", None, github.Unavailable("GitHub HTTP 404", http_status=404)
                return [], False, "live", (NOW + timedelta(minutes=minute)).timestamp(), None

            with patch.object(github._Sync, "page", side_effect=window), \
                    patch.object(github.time, "time", return_value=(NOW + timedelta(minutes=minute)).timestamp()):
                result = github.collect(catalog.projects(), catalog.path, pages=3)
            catalog.record_sync(result)
            selection.extend(first)
        self.assertEqual(selection, ["a-busy", "b-missing", "c-small", "d-small", "e-small"] * 2)

    def test_public_alias_and_safe_numeric_redirect_preserve_identity(self):
        old = "https://github.com/DesignWithTommy/Neonbridge/pull/7"
        new = "https://github.com/DesignWithTommy/i95/pull/7"
        self.assertEqual(source_id(old), source_id(new))
        self.assertEqual(repository_id("DesignWithTommy/Neonbridge"), repository_id("DesignWithTommy/i95"))
        self.assertNotEqual(repository_id("example/i95-fork"), repository_id("DesignWithTommy/i95"))
        with self.catalog.connect() as db, patch.dict(os.environ, {"PORTBRIDGE_GITHUB_TOKEN": "local-fixture-token"}):
            sync = github._Sync(db, True)
            redirect = http_error(301, Location="https://api.github.com/repositories/1469440034")
            response = Response({"id": 1469440034, "full_name": "DesignWithTommy/i95", "private": False})
            with patch.object(sync.opener, "open", side_effect=[redirect, response]) as requests:
                sync._require_public("DesignWithTommy/Neonbridge")
            self.assertEqual(sync.active_repo("DesignWithTommy/Neonbridge"), "DesignWithTommy/i95")
            self.assertEqual(requests.call_args.args[0].full_url, "https://api.github.com/repositories/1469440034")
            bad = http_error(301, Location="https://example.org/repositories/1469440034")
            with patch.object(sync.opener, "open", side_effect=bad) as requests:
                with self.assertRaises(github.Unavailable):
                    sync._require_public("example/other")
                self.assertEqual(requests.call_count, 1)

    def test_disabled_pr_and_incomplete_page_are_reported_without_losing_data(self):
        def read(request, timeout):
            url = request.full_url
            if url.endswith("/repos/ProjectLeonida/mandy"):
                return Response({"id": 22, "private": False, "has_pull_requests": False})
            if "/pulls?" in url:
                raise http_error(404)
            return Response(payload(url))

        result, _ = self.collect(self.catalog, read, NOW)
        project = result["projects"][0]
        self.assertEqual(project["sync_status"], "ok")
        self.assertEqual(project["sources"]["pr"]["sync_status"], "disabled")
        self.assertFalse(result["warnings"])

        def malformed(request, timeout):
            return Response([{"number": number} for number in range(1, 24)]) if "/issues?" in request.full_url else read(request, timeout)

        again, _ = self.collect(self.catalog, malformed, NOW + timedelta(minutes=1))
        source = again["projects"][0]["sources"]["issue"]
        self.assertEqual(source["sync_status"], "stale")
        self.assertEqual(source["errors"][0]["reason"], "incomplete_page")
        self.assertEqual(self.catalog.health()["observation_count"], 1)

    def test_continued_move_uses_the_new_endpoint_and_keeps_old_source_keys(self):
        from portbridge.code_search import _manifest
        from portbridge.matching import current_repository
        old, new = "ubiquitarianism/leonida", "ProjectLeonida/mandy"
        self.assertEqual(current_repository(old), new)
        self.assertEqual(repository_id(old), repository_id(new))
        self.assertEqual(source_id(f"https://github.com/{old}/pull/7"), source_id(f"https://github.com/{new}/pull/7"))
        specs = {row["repo"]: row for row in _manifest()}
        self.assertNotIn(old, specs)
        self.assertIn("runtime/test", specs[new]["directories"])

    def test_source_context_is_bounded_and_keeps_history_without_raw_body(self):
        url = "https://github.com/ubiquitarianism/leonida/pull/81"
        self.catalog.record_sync({"items": [self.observation("continued", "pr", 81, "Review source", url)]})
        marker = "ghp_SECRET_FIXTURE_THIS_MUST_NOT_LEAVE_MEMORY"
        def read(endpoint, resource, etag):
            if "/files?" in endpoint:
                return [{"filename": "tests/case.txt", "additions": 2, "patch": marker}], {}
            return [{"id": 67, "user": {"id": 11, "login": "tester"}, "body": marker,
                     "submitted_at": STAMP, "updated_at": STAMP}], {}

        with patch.object(github._Sync, "_request", side_effect=read) as reader:
            refresh_context(self.catalog, [self.project], [url, url])
            self.assertEqual(reader.call_count, 3)
        ctx = self.catalog.observed_sources([url])[url]["context"]
        self.assertEqual(ctx["reviews"]["entries"][0]["github_user_id"], 11)
        self.assertEqual(len(ctx["files"]["entries"][0]["patch_prefix_sha256"]), 64)
        self.assertNotIn(marker, json.dumps(ctx))

    def test_public_forks_are_candidates_without_enrolling_their_owners(self):
        self.catalog.record_sync({"items": [], "projects": [
            {"slug": self.project["slug"], "repo": self.project["repo"],
             "sync_status": "ok", "availability": "public"},
        ]})
        candidate = "author/fork"
        private = "private/fork"
        rows = [{"full_name": candidate, "private": False}, {"full_name": private, "private": True}]
        with patch.object(github._Sync, "_request", return_value=(rows, {})) as fetch, \
                patch("portbridge.ecosystem._fetch_tracker", return_value=(["other/project"], None)), \
                patch("portbridge.ecosystem.find_public_projects", return_value={}):
            refresh_ecosystem(self.catalog)
        fetch.assert_called_once()
        self.assertIn("/forks?", fetch.call_args.args[0])
        ecosystem = build_ecosystem(self.catalog)
        lead, = [item for item in ecosystem["leads"] if item["repo"] == candidate]
        self.assertEqual(lead["state"], "needs_review")
        self.assertEqual(lead["sources"], ["github-forks"])
        self.assertNotIn(private, json.dumps(ecosystem))
        self.assertFalse(any(project["repo"] == candidate for project in self.catalog.projects()))

    def test_cli_api_mcp_and_export_share_collection_facts(self):
        self.catalog.record_sync({"items": [], "projects": [{"slug": "continued", "sync_status": "partial",
                "last_success": STAMP, "last_attempt": NOW.isoformat(),
                "sources": {"issue": {"sync_status": "error", "last_success": STAMP}}}]})
        local = self.catalog.health(now=NOW)
        cli = json.loads(subprocess.check_output([sys.executable, "-B", "-m", "portbridge",
                                                 "--db", str(self.db_path), "status"]))
        report = PortBridgeMCP(self.catalog).run_tool({"name": "portbridge_health", "arguments": {}})
        structured = json.loads(report["content"][0]["text"])
        with make_server(self.catalog, 0) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with closing(HTTPConnection("127.0.0.1", server.server_port, timeout=5)) as connection:
                    connection.request("GET", "/api/v1/health")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    api = json.loads(response.read())
            finally:
                server.shutdown()
                thread.join()
        site = export(self.catalog, self.workspace / "dist")
        public = json.loads((site / "data/health.json").read_bytes())
        for key in ("status", "last_success", "refresh_at", "observation_count"):
            self.assertEqual({view[key] for view in (local, structured, api, public, cli)}, {local[key]})
        self.assertNotIn("publication", api)
        manifest_path = site / "data/site.json"
        manifest = json.loads(manifest_path.read_bytes())
        self.assertEqual(public["publication"]["generated_at"], manifest["generated_at"])
        self.assertEqual(health_freshness(public, now=NOW)["freshness"]["age_state"], "stale")
        self.assertEqual(verify_linked_snapshots(sha256(manifest_path.read_bytes()).hexdigest(),
                         request=lambda name: (site / "data" / (name + ".json")).open("rb")), ())

    def test_local_read_view_does_not_mix_concurrent_collection_cycles(self):
        with self.catalog.read_view() as view:
            first = view.health()
            url = "https://github.com/ubiquitarianism/leonida/pull/512"
            self.catalog.record_sync({"items": [self.observation("continued", "pr", 512, "New cycle", url)],
                                      "projects": [{"slug": "continued", "sync_status": "ok", "last_success": STAMP}]})
            self.assertEqual(view.health()["observation_count"], first["observation_count"])
            self.assertFalse(view.observations())
            self.assertEqual(preflight(view, url=url)["catalog_status"], "seed-only")
        self.assertEqual(self.catalog.health()["observation_count"], 1)
        self.assertTrue(preflight(self.catalog, url=url)["indexed"])

    def test_reviewed_evidence_transition_propagates_and_replays_without_duplicates(self):
        seed = json.loads(DEFAULT_SEED.read_bytes())
        problem = next(card for card in seed["problems"] if card["id"] == "PB-0024")
        solution = next(s for s in problem["solutions"] if s["project"] == "framelab")
        evidence = next(e for e in solution["evidence"] if "7153817545" in e["url"])
        eid = evidence_fields(evidence)["evidence_id"]
        changeable = self.workspace / "reviewed.json"
        changeable.write_text(json.dumps(seed), encoding="utf-8")
        catalog = Catalog(self.db_path, changeable)
        self.assertEqual(len(catalog.core_history(entity_id=eid)), 1)
        evidence["outcome"] = "failed"
        changeable.write_text(json.dumps(seed), encoding="utf-8")
        catalog = Catalog(self.db_path, changeable)
        again = Catalog(self.db_path, changeable)
        self.assertEqual([e["payload"]["outcome"] for e in again.core_history(entity_id=eid)], ["passed", "failed"])
        graph = knowledge_graph(catalog)
        self.assertEqual(next(e for e in graph["reviewed_evidence"] if e["evidence_id"] == eid)["outcome"], "failed")
        lab = build_lab(catalog, task="framelab-12-vulkan-handoff")["tasks"][0]
        self.assertEqual(next(e for e in lab["related_evidence"] if e["evidence_id"] == eid)["outcome"], "failed")
        search = preflight(catalog, url=evidence["url"])
        self.assertIn(eid, json.dumps(search))
        solution["evidence"].remove(evidence)
        changeable.write_text(json.dumps(seed), encoding="utf-8")
        revoked = Catalog(self.db_path, changeable)
        self.assertEqual(revoked.core_history(entity_id=eid)[-1]["state"], "withdrawn")
        self.assertEqual(len(revoked.core_history(entity_id=eid)), 3)
