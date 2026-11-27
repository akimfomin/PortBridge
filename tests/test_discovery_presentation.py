"""Offline readback and browser presentation of a saved Discovery search."""

import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from portbridge import code_search
from portbridge.__main__ import Handler, make_server
from portbridge.discovery_search import discover, discovery_index, key
from portbridge.export import export
from portbridge.mcp import PortBridgeMCP
from portbridge.preflight import public_preflight
from test_portbridge import CatalogFixture


PR = "https://github.com/xcl-dev/xcl/pull/99999"
ROOT = Path(__file__).resolve().parents[1]


def browser_binary():
    windows = Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe"
    return next((path for name in ("google-chrome", "chromium", "chromium-browser") if (path := shutil.which(name))),
                str(windows) if windows.is_file() else None)


class DiscoveryPresentationTest(CatalogFixture):
    @unittest.skipUnless(browser_binary(), "Chromium is needed to observe the initial network requests")
    def test_initial_network_route_for_export_and_local_server(self):
        site = export(self.catalog, self.workspace / "snapshot")
        visits = []
        class Static(SimpleHTTPRequestHandler):
            def do_GET(self):
                visits.append(self.path.split("?")[0])
                super().do_GET()
            def log_message(self, *args):
                pass
        def render(server, lang):
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                result = subprocess.run([browser_binary(), "--headless", "--disable-gpu", "--disable-background-networking",
                    "--no-first-run", "--no-sandbox", f"--user-data-dir={self.workspace / 'browser'}",
                    "--virtual-time-budget=3000", "--dump-dom", f"http://127.0.0.1:{server.server_port}/?lang={lang}#/lab"],
                    capture_output=True, check=True, timeout=25)
                return result.stdout.decode("utf-8")
            finally:
                server.shutdown()
                worker.join()
        def render_static(lang):
            visits.clear()
            with ThreadingHTTPServer(("127.0.0.1", 0), partial(Static, directory=site)) as server:
                return render(server, lang)
        for lang in ("en", "ru"):
            self.assertTrue('class="card lab-task"' in render_static(lang))
            self.assertIn("/data/site.json", visits)
            self.assertNotIn("/favicon.ico", visits)
            self.assertFalse(any(req.startswith("/api/") for req in visits))
        manifest = site / "data/site.json"
        raw = manifest.read_bytes()
        manifest.unlink()
        self.assertIn("Не удалось загрузить данные", render_static("ru"))
        self.assertFalse(any(req.startswith("/api/") for req in visits))
        manifest.write_bytes(raw)
        # An older, unmarked static deployment still falls back to its published manifest.
        index = site / "index.html"
        index.write_bytes(index.read_bytes().replace(b'<meta name="portbridge-mode" content="snapshot">', b""))
        self.assertTrue('class="card lab-task"' in render_static("en"))
        self.assertIn("/api/v1/health", visits)
        self.assertIn("/data/site.json", visits)
        visits.clear()
        original = Handler.do_GET
        def observed(handler):
            visits.append(handler.path.split("?")[0])
            original(handler)
        with patch.object(Handler, "do_GET", observed), make_server(self.catalog, 0) as server:
            self.assertTrue('class="card lab-task"' in render(server, "ru"))
        self.assertIn("/api/v1/health", visits)
        self.assertIn("/api/v1/lab", visits)
        self.assertNotIn("/data/site.json", visits)

    def test_empty_url_states_distinguish_search_coverage(self):
        for status, reason, expected, message in (
            ("available", None, "no_match", "no matching source"),
            ("partial", None, "partial", "incomplete"),
            ("offline", None, "offline", "No external sources were checked"),
            ("stale", None, "stale", "out of date"),
            ("unavailable", "rate_limit", "unavailable", "rate-limited"),
            ("unavailable", None, "unavailable", "could not be completed"),
            ("no_subject", None, "no_subject", "No external search ran"),
            ("not_scanned", None, "not_scanned", "--online --url"),
        ):
            with self.subTest(status=status, reason=reason):
                scan = {"subject": "", "status": status, "reason": reason, "matches": []}
                index = {**discovery_index(), "automatic": {key(PR): scan}}
                result = discover(origin_url=PR, index=index)
                self.assertEqual((result["status"], result["scan_status"], result["scan_reason"]), (expected, status, reason))
                self.assertIn(message, result["empty_reason"])
        issue = discover(origin_url=PR.replace("/pull/", "/issues/"))
        commit = discover(origin_url=PR.replace("pull/99999", "commit/" + "a" * 40))
        self.assertIn("discovery_scan --online --url", issue["empty_reason"])
        self.assertNotIn("--url", commit["empty_reason"])

    def test_mcp_and_snapshot_outage_retell_the_available_evidence(self):
        mcp = PortBridgeMCP(self.catalog)
        result = mcp.run_tool({"name": "portbridge_preflight", "arguments": {"url": PR}})
        self.assertEqual(result["structuredContent"]["discovery"]["status"], "not_scanned")
        with patch("portbridge.preflight.read_public_file", side_effect=OSError("offline")):
            fallback = public_preflight(url=PR)["discovery"]
            self.assertEqual(fallback["status"], "unavailable")
            self.assertEqual(fallback["scan_reason"], "snapshot_unavailable")
            self.assertIn("bundled", fallback["empty_reason"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed to run the static ranker")
    def test_exported_ranker_uses_the_same_subject_for_an_unmapped_pr(self):
        index = {**discovery_index(), "automatic": {
            key(PR): {"subject": "vkimagememorybarrier2", "status": "partial", "matches": []}
        }}
        ranked = discover(origin_url=PR, index=index)
        self.assertTrue(ranked["matches"])
        script = (ROOT / "portbridge/static/discovery.js").read_text(encoding="utf-8")
        script += "\nconst [index, url] = JSON.parse(require('fs').readFileSync(0, 'utf8'));" \
                  "\nconst {matches, scan_status} = PortBridgeDiscovery.search(index, url);" \
                  "\nconsole.log(JSON.stringify([matches.map(row => row.id), scan_status]));"
        result = subprocess.run(["node", "-e", script], input=json.dumps([index, PR]), text=True,
                                capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout), [[row["id"] for row in ranked["matches"]], "partial"])

    @unittest.skipUnless(browser_binary(), "Chromium is needed to render the search route")
    def test_empty_search_route_explains_an_unscanned_pr(self):
        with make_server(self.catalog, 0) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                route = f"http://127.0.0.1:{server.server_port}/?lang=ru#/problems?" + urlencode({"q": PR})
                rendered = subprocess.run([
                    browser_binary(), "--headless", "--disable-gpu", "--disable-background-networking", "--no-sandbox",
                    "--no-first-run", f"--user-data-dir={self.workspace / 'browser'}", "--virtual-time-budget=3000",
                    "--dump-dom", route,
                ], capture_output=True, timeout=25, check=True)
                self.assertIn("Для этого PR пока нет сохранённого внешнего поиска.", rendered.stdout.decode("utf-8"))
            finally:
                server.shutdown()
                thread.join()

    @unittest.skipUnless(browser_binary(), "Chromium is needed to render source-code candidates")
    def test_browser_shows_source_code_without_a_problem_card(self):
        repo, revision, source_path = "Example/Graphics", "a" * 40, "tests/queue.c"
        rule = "VUID-vkQueueSubmit-pSubmits-00001"
        reference = {"repo": repo, "revision": revision, "path": source_path, "license": "MIT",
                     "license_url": f"https://github.com/{repo}/blob/{revision}/LICENSE"}
        row = self.observation("xcl", "pr", "99999", "Synthetic source diagnostic", PR,
                               {"technical": {"code_diagnostics": [rule.lower()]}})
        self.catalog.record_sync({"items": [row]}, update_health=False)
        with patch.object(code_search, "references", return_value=[reference]):
            code_search.refresh(self.catalog, fetch=lambda _: f'assert_diagnostic("{rule}");'.encode())
            site = export(self.catalog, self.workspace / "snapshot")
            with make_server(self.catalog, 0) as api_server, ThreadingHTTPServer(
                ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=site)
            ) as snapshot_server:
                for server in (api_server, snapshot_server):
                    thread = Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    try:
                        route = f"http://127.0.0.1:{server.server_port}/?lang=en#/problems?" + urlencode({"q": PR})
                        page = subprocess.run([
                            browser_binary(), "--headless", "--disable-gpu", "--disable-background-networking",
                            "--no-first-run", "--no-sandbox", f"--user-data-dir={self.workspace / 'code-browser'}",
                            "--virtual-time-budget=3000", "--dump-dom", route,
                        ], capture_output=True, timeout=25, check=True).stdout.decode("utf-8")
                        self.assertIn("Candidate source-code lines", page)
                        self.assertIn(f"https://github.com/{repo}/blob/{revision}/{source_path}#L1", page)
                    finally:
                        server.shutdown()
                        thread.join()
