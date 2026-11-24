from contextlib import closing
from email.message import Message
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from portbridge import github
from portbridge.__main__ import DEFAULT_SEED, sync_catalog
from portbridge.catalog import Catalog


class GitHubSyncTest(unittest.TestCase):
    project = {"slug": "example", "repo": "example/port"}
    sha = "a" * 40

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "catalog.sqlite"
        env = patch.dict(os.environ, {"PORTBRIDGE_GITHUB_TOKEN": "", "GITHUB_TOKEN": ""})
        env.start()
        self.addCleanup(env.stop)

    def fake_request(self, url, resource, etag):
        headers = {"ETag": '"metadata"'}
        if "/search/issues?" in url:
            data = {"items": [
                {"number": 1, "state": "open", "title": "Texture stalls", "body": "ignored body",
                 "user": {"login": "author"}},
                {"number": 2, "pull_request": {}, "title": "An overlapping pull request"},
            ]}
        elif "/pulls?" in url:
            data = [{"number": 2, "state": "closed", "merged_at": "2026-01-01T00:00:00Z",
                     "title": "Handle texture stub", "head": {"sha": self.sha}, "body": "ignored body"}]
        elif "/commits?" in url:
            data = [{"sha": self.sha, "commit": {"message": "Fix texture stub\nignore commit body"}}]
        elif "/actions/runs?" in url:
            data = {"workflow_runs": [{"id": 3, "name": "Windows CI", "status": "completed",
                                      "conclusion": "success", "head_sha": self.sha,
                                      "pull_requests": [{"number": 2}]}]}
        else:
            self.fail(f"unexpected endpoint {url}")
        return data, headers

    def test_targeted_refresh_groups_exact_issues_and_prs_without_scanning_pages(self):
        catalog = Catalog(self.db_path, DEFAULT_SEED)
        pr = "https://github.com/Marvisak/VIctory/pull/571"
        issue = "https://github.com/ivall/xcl/issues/772"
        current_issue = "https://github.com/xcl-dev/xcl/issues/772"

        def read_exact(url, resource, etag):
            lookup = {
                "https://api.github.com/repos/Marvisak/VIctory/pulls/571": (571, "Implement LDS byte reads"),
                "https://api.github.com/repos/xcl-dev/xcl/issues/772": (772, "Check LDS on Wave64"),
            }
            number, title = lookup[url]
            return {"number": number, "title": title, "state": "open", "head": {"sha": self.sha}}, {}

        with patch.object(github._Sync, "_request", side_effect=read_exact) as network:
            result = sync_catalog(catalog, sources=[pr, issue, pr.lower(), current_issue])["targeted_refresh"]
            self.assertEqual(network.call_count, 2)
            self.assertEqual(result["observations_saved"], 2)
            self.assertEqual(result["warnings"], [])
            with self.assertRaisesRegex(ValueError, "configured public"):
                sync_catalog(catalog, sources=[pr, "https://github.com/other/project/issues/2"])
            self.assertEqual(network.call_count, 2)
        self.assertEqual({record["url"] for record in catalog.observations()}, {pr, current_issue})

    def test_pinned_revision_and_archived_observations_accept_both_xcl_names(self):
        catalog = Catalog(self.db_path, DEFAULT_SEED)
        legacy = "https://github.com/ivall/xcl/pull/1100"
        current = "https://github.com/xcl-dev/xcl/pull/1100"
        rows = ((legacy, "open", self.sha, "2026-11-24T17:00:00Z"),
                (current, "merged", "b" * 40, "2026-11-24T17:30:00Z"))
        for url, status, head, updated in rows:
            catalog.record_sync({"items": [{"project": "xcl", "source_id": "1100", "kind": "pr", "url": url,
                                            "title": "Check FMA modifiers", "status": status, "updated_at": updated,
                                            "metadata": {"head_sha": head}}]})
            self.assertEqual(catalog.observed_revisions([legacy, current]), {legacy: head})
            matching = [ref for card in catalog.problems() for solution in card["solutions"]
                        for ref in solution["source_refs"] if ref["url"] == legacy]
            self.assertTrue(matching)
            self.assertEqual(matching[0]["github"]["revision"], head)
        self.assertEqual(catalog.source_changes(url=legacy), catalog.source_changes(url=current))
        self.assertEqual(catalog.source_changes(url=current)[0]["revision"], "b" * 40)
        self.assertEqual(len(catalog.observations(project="xcl")), 1)

        with patch.object(github._Sync, "_request", return_value=({"number": 1100, "head": {"sha": self.sha}}, {})) as network:
            revisions = github.public_source_revisions(self.db_path, [legacy])
        self.assertEqual(revisions, {legacy: self.sha})
        network.assert_called_once_with("https://api.github.com/repos/xcl-dev/xcl/pulls/1100", "core", None)

    def test_move_keeps_completed_xcl_backfill_checkpoint(self):
        github.commit_backfill(self.db_path, [{"slug": "xcl", "repo": "ivall/xcl", "mode": "backfill",
                                              "revision": 0, "next_page": 45, "complete": True,
                                              "started_at": 220, "since": None, "updated_at": 224, "anchor": []}])
        with patch.object(github._Sync, "_request") as network:
            result = github.backfill([{"slug": "xcl", "repo": "xcl-dev/xcl"}], self.db_path)
        network.assert_not_called()
        self.assertEqual(result["history"][0]["status"], "complete")
        self.assertEqual(github.backfill_status(self.db_path)[0]["repo"], "xcl-dev/xcl")

    def test_collect_normalized_metadata_and_reuse_fresh_cache(self):
        with patch.object(github._Sync, "_request", side_effect=self.fake_request) as network:
            first = github.collect([self.project], self.db_path)
            fresh = github.collect([self.project], self.db_path)
        self.assertEqual(network.call_count, 4)
        self.assertEqual(first["items"], fresh["items"])
        self.assertEqual(first["projects"][0]["sync_status"], "ok")
        self.assertIsNotNone(first["projects"][0]["last_success"])
        self.assertFalse(first["warnings"])
        self.assertEqual([x["kind"] for x in first["items"]], ["issue", "pr", "commit", "test"])
        _, pr, commit, test = first["items"]
        self.assertEqual(pr["status"], "merged")
        self.assertEqual(commit["title"], "Fix texture stub")
        self.assertEqual(test["metadata"]["pull_requests"], [2])
        self.assertEqual(test["metadata"]["evidence_kind"], "automated")
        self.assertEqual(test["metadata"]["scope"], "workflow_run")
        with closing(sqlite3.connect(self.db_path)) as db:
            rows = db.execute("SELECT items FROM github_cache").fetchall()
        self.assertNotIn("ignored body", repr(rows))
        self.assertNotIn("ignore commit body", repr(rows))

    def test_reviewed_references_refresh_exact_pr_and_job_without_fetching_logs(self):
        base = "https://github.com/example/port"

        def exact(url, resource, etag):
            if url.endswith("/pulls/2"):
                return {"number": 2, "state": "closed", "merged_at": "2026-01-01T00:00:00Z",
                        "head": {"sha": self.sha}}, {}
            if url.endswith("/actions/jobs/4"):
                return {"id": 4, "run_id": 3, "status": "completed", "conclusion": "failure"}, {}
            self.fail(f"unexpected endpoint {url}")

        refs = [f"{base}/pull/2#comment", f"{base}/actions/runs/3/job/4",
                f"{base}/actions/runs/3/logs", "https://github.com/unconfigured/other/issues/1"]
        with patch.object(github._Sync, "_request", side_effect=exact) as network:
            result = github.refresh_references([self.project], self.db_path, refs)
            cached = github.refresh_references([self.project], self.db_path, refs)
        self.assertEqual(result, cached)
        self.assertEqual(network.call_count, 2)
        self.assertEqual([item["status"] for item in result["items"]], ["merged", "failure"])
        self.assertEqual(result["items"][1]["metadata"]["scope"], "workflow_job")
        self.assertEqual(result["items"][1]["url"], refs[1])

    def test_old_signature_cache_is_reloaded_then_uses_conditional_requests(self):
        source = "https://github.com/example/port/pull/2"

        def exact(url, resource, etag):
            self.assertTrue(url.endswith("/pulls/2"))
            self.assertIsNone(etag)
            return {"number": 2, "title": "Lane exchange", "body": "Check ds_bpermute_b32."}, {"ETag": '"new"'}

        with closing(sqlite3.connect(self.db_path)) as db:
            github._Sync(db, False)
            with db:
                db.execute("INSERT INTO github_cache VALUES (?, ?, ?, ?, 0)", (
                    f"{github.API}/repos/example/port/pulls/2", '"old"', github.time.time(),
                    '[{"metadata":{"technical":{"terms":[],"signals":[]}}}]',
                ))
        with patch.object(github._Sync, "_request", side_effect=exact) as network:
            first = github.refresh_references([self.project], self.db_path, [source])
            self.assertEqual(network.call_count, 1)
        self.assertEqual(first["items"][0]["metadata"]["technical"]["signals"], ["ds_bpermute_b32"])
        with patch.object(github._Sync, "_request", return_value=(github.NOT_MODIFIED, {})) as network:
            compared = github.refresh_references([self.project], self.db_path, [source], refresh=True)
            network.assert_called_once_with(f"{github.API}/repos/example/port/pulls/2", "core", '"new"')
        self.assertEqual(first, compared)

    def test_long_instruction_list_retains_later_diagnostics_and_api_symbols(self):
        head = " ".join(f"DS_READ{i}_B64" for i in range(21))
        body = f"{head} `DS_READ_U8_D16/_HI` and `IMAGE_SAMPLE_C_D`, vkCreateGraphicsPipelines."
        signals = github._technical({"body": body}, [], {})["signals"]
        self.assertIn("ds_read_u8_d16_hi", signals)
        self.assertIn("image_sample_c_d", signals)
        self.assertIn("vkcreategraphicspipelines", signals)

    def test_conditional_refresh_retains_stale_page_when_other_pages_are_revalidated(self):
        with patch.object(github._Sync, "_request", side_effect=self.fake_request), \
                patch.object(github.time, "time", return_value=1700000000):
            first = github.collect([self.project], self.db_path)

        def revalidate(url, resource, etag):
            self.assertEqual(etag, '"metadata"')
            if "/pulls?" in url:
                raise github.Unavailable("GitHub HTTP 503")
            return github.NOT_MODIFIED, {}

        with patch.object(github._Sync, "_request", side_effect=revalidate) as network, \
                patch.object(github.time, "time", return_value=1700000060):
            again = github.collect([self.project], self.db_path, refresh=True)
        self.assertEqual(network.call_count, 4)
        self.assertEqual(first["items"], again["items"])
        self.assertEqual(again["projects"][0]["sync_status"], "partial")
        self.assertEqual(again["projects"][0]["sources"]["pr"]["sync_status"], "stale")
        self.assertEqual(again["projects"][0]["sources"]["pr"]["last_success"], "2023-11-14T22:13:20+00:00")
        self.assertEqual(again["projects"][0]["sources"]["issue"]["last_success"], "2023-11-14T22:14:20+00:00")
        self.assertIn("using stale cache", again["warnings"][0])

    def test_private_repositories_cannot_be_listed_with_token(self):
        def check(url, resource, etag):
            self.assertEqual(url, "https://api.github.com/repos/example/port")
            return {"private": True, "visibility": "private"}, {}

        with patch.dict(os.environ, {"PORTBRIDGE_GITHUB_TOKEN": "test-token"}), \
                patch.object(github._Sync, "_request", side_effect=check) as network:
            result = github.collect([self.project], self.db_path)
        self.assertEqual(network.call_count, 1)
        self.assertFalse(result["items"])
        self.assertEqual(result["projects"][0]["sync_status"], "unavailable")
        self.assertTrue(all("repository is not public" in msg for msg in result["warnings"]))

    def test_authenticated_repository_access_distinguishes_http_failures(self):
        for status, expected in ((404, "unavailable"), (451, "unavailable"), (403, "error"), (429, "error")):
            with self.subTest(status=status):
                error = github.Unavailable(f"GitHub HTTP {status}", http_status=status)
                with patch.dict(os.environ, {"PORTBRIDGE_GITHUB_TOKEN": "test-token"}), \
                        patch.object(github._Sync, "_request", side_effect=error) as network:
                    result = github.collect([self.project], self.db_path)
                network.assert_called_once_with(f"{github.API}/repos/example/port", "core", None)
                self.assertEqual(result["projects"][0]["sync_status"], expected)
                self.assertFalse(result["items"])

    def test_anonymous_repository_access_holds_cache_until_verified_recovery(self):
        with patch.object(github._Sync, "_request", side_effect=self.fake_request), \
                patch.object(github.time, "time", return_value=1700000000):
            original = github.collect([self.project], self.db_path)

        def missing(url, resource, etag):
            if "/search/issues?" in url:
                return github.NOT_MODIFIED, {}
            raise github.Unavailable("GitHub HTTP 404", http_status=404)

        with patch.object(github._Sync, "_request", side_effect=missing), \
                patch.object(github.time, "time", return_value=1700000040):
            interrupted = github.collect([self.project], self.db_path, refresh=True)
        project = interrupted["projects"][0]
        self.assertEqual(project["sync_status"], "unavailable")
        self.assertEqual(project["sources"]["pr"]["sync_status"], "stale")
        self.assertEqual(project["sources"]["pr"]["last_success"], original["projects"][0]["last_success"])
        self.assertEqual(interrupted["items"], original["items"])

        limited = github.Unavailable("GitHub HTTP 403 (rate limited)", http_status=403)
        with patch.object(github._Sync, "_request", side_effect=limited) as network, \
                patch.object(github.time, "time", return_value=1700000080):
            pending = github.collect([project], self.db_path)
        self.assertEqual(network.call_count, 4)
        self.assertEqual(pending["projects"][0]["sync_status"], "unavailable")
        self.assertEqual(pending["items"], original["items"])

        with patch.object(github._Sync, "_request", return_value=(github.NOT_MODIFIED, {})), \
                patch.object(github.time, "time", return_value=1700000120):
            restored = github.collect(pending["projects"], self.db_path)
        self.assertEqual(restored["projects"][0]["sync_status"], "ok")
        self.assertEqual(restored["items"], original["items"])

    def test_anonymous_single_endpoint_failure_keeps_repository_visible(self):
        def partial(url, resource, etag):
            if "/actions/runs?" in url:
                raise github.Unavailable("GitHub HTTP 404", http_status=404)
            return self.fake_request(url, resource, etag)

        with patch.object(github._Sync, "_request", side_effect=partial):
            result = github.collect([self.project], self.db_path)
        self.assertEqual(result["projects"][0]["sync_status"], "partial")
        self.assertEqual(result["projects"][0]["sources"]["test"]["sync_status"], "error")

    def test_rate_limit_suppresses_more_requests_for_the_same_resource(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            sync = github._Sync(db, True)
            headers = Message()
            headers["Retry-After"] = "60"
            error = HTTPError("https://api.github.com/repos/example/port/pulls", 429, "limit", headers, None)
            with patch.object(sync.opener, "open", side_effect=error) as network:
                with self.assertRaisesRegex(github.Unavailable, "429"):
                    sync._request("https://api.github.com/repos/example/port/pulls", "core", None)
                with self.assertRaisesRegex(github.Unavailable, "retry after"):
                    sync._request("https://api.github.com/repos/example/port/commits", "core", None)
                self.assertEqual(network.call_count, 1)
                self.assertEqual(network.call_args.args[0].get_method(), "GET")
                self.assertIsNone(network.call_args.args[0].data)
                with self.assertRaisesRegex(ValueError, "only https"):
                    sync._request("https://example.com/redirect", "search", None)

    def test_pagination_uses_own_numbered_url_instead_of_link_destination(self):
        seen = []

        def get_page(url, resource, etag):
            seen.append(url)
            if "/search/issues?" not in url:
                return self.fake_request(url, resource, etag)
            if "&page=1&" in url:
                return {"items": [{"number": 1, "title": "First"}]}, {
                    "Link": '<https://example.com/unsafe>; rel="next"',
                }
            return {"items": [{"number": 2, "title": "Second"}]}, {}

        with patch.object(github._Sync, "_request", side_effect=get_page):
            result = github.collect([self.project], self.db_path, pages=2)
        self.assertEqual(len(seen), 5)
        self.assertTrue(all(url.startswith("https://api.github.com/") for url in seen))
        self.assertEqual(result["projects"][0]["sources"]["issue"]["pages_checked"], 2)
        self.assertEqual([x["source_id"] for x in result["items"] if x["kind"] == "issue"], ["1", "2"])

    def test_signature_keeps_only_allowed_terms_codes_and_primary_references(self):
        second = {"slug": "second", "repo": "Example/Second"}
        private = "raw-body-marker-cannot-leak"
        attachment = "https://github.com/Example/Second/releases/download/v1/game.zip"

        def request(url, resource, etag):
            if "/search/issues?" not in url:
                return self.fake_request(url, resource, etag)
            return {"items": [{"number": 9, "title": "D3D12 shader issue", "body": (
                f"{private} vkCreateGraphicsPipelines DXGI_ERROR_DEVICE_REMOVED 0x887A0005. "
                "Compare https://github.com/example/second/pull/72#discussion. "
                "See [same](https://github.com/Example/Second/pull/72?x=1). "
                f"Fix [source](https://github.com/example/port/commit/{self.sha}). "
                f"Ignore {attachment} https://untrusted.example/VK_ERROR_FAKE. "
                "Ignore https://github.com/other/repo/issues/3 and "
                "https://github.com/Example/Second/issues/1/attachments"
            )}]}, {}

        with patch.object(github._Sync, "_request", side_effect=request):
            result = github.collect([self.project, second], self.db_path)
        signature = result["items"][0]["metadata"]["technical"]
        self.assertEqual(signature["terms"], ["d3d12", "shader"])
        self.assertEqual(signature["signals"], ["vkcreategraphicspipelines", "dxgi_error_device_removed", "0x887a0005"])
        self.assertEqual(signature["references"], ["https://github.com/Example/Second/pull/72",
                                                   f"https://github.com/example/port/commit/{self.sha}"])
        with closing(sqlite3.connect(self.db_path)) as db:
            data = repr(db.execute("SELECT items FROM github_cache").fetchall())
        for detail in (private, attachment, "untrusted.example", "#discussion", "/other/repo/"):
            self.assertNotIn(detail, data)

    def test_backfill_replays_until_caller_saves_and_resumes_after_error(self):
        requests = []
        fail = True

        def request(url, resource, etag):
            self.assertEqual(urlsplit(url).path, "/repos/example/port/issues")
            params = parse_qs(urlsplit(url).query)
            self.assertEqual((params["state"], params["sort"], params["direction"]),
                             (["all"], ["created"], ["asc"]))
            page = int(params["page"][0])
            requests.append(page)
            if page == 1:
                return [{"number": 1, "title": "Issue", "state": "open"}], {
                    "Link": '<https://api.github.com/repos/example/port/issues?page=2>; rel="next"',
                }
            if fail:
                raise github.Unavailable("rate limit test")
            return [{"number": 2, "title": "PR", "state": "closed", "pull_request": {
                     "merged_at": "2026-11-01T00:00:00Z"}}], {}

        with patch.object(github._Sync, "_request", side_effect=request):
            first = github.backfill([self.project], self.db_path, pages=2)
            self.assertEqual(github.backfill_status(self.db_path), [])
            self.assertEqual(first["projects"][0]["sync_status"], "partial")
            self.assertEqual(first["history"][0]["status"], "partial")
            self.assertEqual(first["history"][0]["warning"], "rate limit test")
            self.assertEqual(first["checkpoint"][0]["next_page"], 2)
            self.assertEqual(first["items"][0]["kind"], "issue")
            replay = github.backfill([self.project], self.db_path, pages=1)
            self.assertEqual([item["source_id"] for item in replay["items"]], ["1"])
            github.commit_backfill(self.db_path, first["checkpoint"])
            self.assertEqual(github.backfill_status(self.db_path)[0]["next_page"], 2)
            fail = False
            last = github.backfill([self.project], self.db_path)
            self.assertEqual(last["items"][0]["kind"], "pr")
            self.assertEqual(last["items"][0]["status"], "merged")
            self.assertEqual(last["history"][0]["status"], "complete")
            self.assertIsNone(last["history"][0]["warning"])
            github.commit_backfill(self.db_path, last["checkpoint"])
            github.commit_backfill(self.db_path, replay["checkpoint"])
            self.assertTrue(github.backfill_status(self.db_path)[0]["complete"])
            self.assertFalse(github.backfill([self.project], self.db_path)["items"])
        self.assertEqual(requests, [1, 2, 1, 2, 1])

    def test_complete_legacy_history_reindexes_new_signatures_in_batches(self):
        with closing(github._history_db(self.db_path)) as db, db:
            github._history_anchor_table(db)
            db.execute("INSERT INTO github_history VALUES (?, ?, 'backfill', 2, 99, 1, 1, NULL, 1)",
                       (self.project["slug"], self.project["repo"]))
            db.execute("INSERT INTO github_history_anchor VALUES (?, ?, 'backfill', '[]')",
                       (self.project["slug"], self.project["repo"]))
        body = [{"number": 1, "title": "Wave behavior", "body": "Check ds_read_b64."}]
        with patch.object(github._Sync, "_request", return_value=(body, {})) as network:
            refreshed = github.backfill([self.project], self.db_path, pages=1)
            github.commit_backfill(self.db_path, refreshed["checkpoint"])
            self.assertFalse(github.backfill([self.project], self.db_path, pages=1)["items"])
            self.assertEqual(network.call_count, 1)
            self.assertEqual(parse_qs(urlsplit(network.call_args.args[0]).query)["page"], ["1"])
        self.assertEqual(refreshed["items"][0]["metadata"]["technical"]["signals"], ["ds_read_b64"])

    def test_incremental_moves_time_cursor_with_boundary_overlap(self):
        now = 1700000000
        first_stamp = "2023-11-14T22:10:00Z"
        params_seen = []

        def request(url, resource, etag):
            self.assertEqual(urlsplit(url).path, "/repos/example/port/issues")
            params = parse_qs(urlsplit(url).query)
            self.assertEqual((params["sort"], params["direction"]), (["updated"], ["asc"]))
            params_seen.append((params["page"][0], params["since"][0]))
            if len(params_seen) == 1:
                return [{"number": 1, "title": "Issue", "updated_at": first_stamp}], {
                    "Link": '<https://api.github.com/repos/example/port/issues?page=2>; rel="next"',
                }
            return [{"number": 1, "title": "Issue", "updated_at": first_stamp},
                    {"number": 2, "title": "Pull request", "pull_request": {}, "updated_at": first_stamp}], {}

        with patch.object(github.time, "time", return_value=now), \
                patch.object(github._Sync, "_request", side_effect=request):
            result = github.incremental([self.project], self.db_path, pages=2)
            self.assertEqual(github.backfill_status(self.db_path, mode="incremental"), [])
            github.commit_backfill(self.db_path, result["checkpoint"])
        self.assertEqual(params_seen, [("1", "2023-11-13T22:13:20Z"), ("1", "2023-11-14T22:09:59Z")])
        self.assertEqual([item["kind"] for item in result["items"]], ["issue", "pr"])
        self.assertEqual(github.backfill_status(self.db_path, mode="incremental")[0]["since"],
                         "2023-11-14T22:12:20+00:00")

    def test_incremental_replays_a_shifted_same_second_boundary_without_losing_items(self):
        now = 1700000000
        tied = "2023-11-14T22:10:00Z"
        moved_at = "2023-11-14T22:13:21Z"
        issue_order = [(1, tied), (2, tied), (3, tied), (4, tied)]

        def request(url, resource, etag):
            params = parse_qs(urlsplit(url).query)
            page = int(params["page"][0])
            start = (page - 1) * 2
            records = [{"number": ident, "title": f"Issue {ident}", "updated_at": stamp}
                       for ident, stamp in issue_order[start:start + 2]]
            headers = {"Link": '<https://api.github.com/next>; rel="next"'} if page == 1 else {}
            return records, headers

        with patch.object(github.time, "time", return_value=now), \
                patch.object(github._Sync, "_request", side_effect=request):
            first = github.incremental([self.project], self.db_path, pages=2)
            github.commit_backfill(self.db_path, first["checkpoint"])
            before = github.backfill_status(self.db_path, mode="incremental")[0]
            self.assertEqual(before["next_page"], 2)
            issue_order[:] = [(2, tied), (3, tied), (4, tied), (1, moved_at)]

            shifted = github.incremental([self.project], self.db_path)
            self.assertIn("page boundary changed", shifted["warnings"][0])
            github.commit_backfill(self.db_path, shifted["checkpoint"])
            replay = github.backfill_status(self.db_path, mode="incremental")[0]
            self.assertEqual(replay["since"], before["since"])
            self.assertEqual(replay["next_page"], 1)

            recovered = github.incremental([self.project], self.db_path, pages=2)
            github.commit_backfill(self.db_path, recovered["checkpoint"])
        self.assertFalse(recovered["warnings"])
        self.assertEqual({item["source_id"] for item in recovered["items"]}, {"1", "2", "3", "4"})
        self.assertGreater(github.backfill_status(self.db_path, mode="incremental")[0]["since"], before["since"])


if __name__ == "__main__":
    unittest.main()
