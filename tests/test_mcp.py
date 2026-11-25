from io import BytesIO
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from portbridge.__main__ import DEFAULT_SEED, ROOT
from portbridge.catalog import Catalog
from portbridge.lab import build_lab
from portbridge.mcp import ReadOnlyCatalog, main
from portbridge.preflight import PUBLIC_BASE


MODERN_META = {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                         "io.modelcontextprotocol/clientCapabilities": {}}}


def message(ident, method, params=None):
    value = {"jsonrpc": "2.0", "method": method}
    if ident is not None:
        value["id"] = ident
    if params is not None:
        value["params"] = params
    return value


class MCPTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(prefix="portbridge-mcp-")
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "каталог #1.sqlite3"
        Catalog(self.db, DEFAULT_SEED)

    def run_server(self, *messages, db=None):
        inputs = [value if isinstance(value, bytes) else json.dumps(value).encode("utf-8") for value in messages]
        return subprocess.run([sys.executable, "-m", "portbridge.mcp", "--db", str(db or self.db)],
                              input=b"\n".join(inputs) + b"\n", capture_output=True, cwd=ROOT, timeout=10)

    def replies(self, *messages):
        proc = self.run_server(*messages)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", errors="replace"))
        self.assertEqual(proc.stderr, b"")
        return [json.loads(line) for line in proc.stdout.splitlines()]

    def public_replies(self, *messages):
        reader = BytesIO(b"".join(json.dumps(value).encode("utf-8") + b"\n" for value in messages))
        writer = BytesIO()
        streams = SimpleNamespace(stdin=SimpleNamespace(buffer=reader), stdout=SimpleNamespace(buffer=writer))
        with patch("portbridge.mcp.sys", streams):
            main([])
        return [json.loads(line) for line in writer.getvalue().splitlines()]

    def test_discovery_and_preflight_without_initialization(self):
        discover, tools, result, from_url = self.replies(
            message(1, "server/discover", MODERN_META),
            message(2, "tools/list", MODERN_META),
            message(3, "tools/call", {**MODERN_META, "name": "portbridge_preflight",
                                      "arguments": {"q": "#20", "limit": 1}}),
            message(4, "tools/call", {**MODERN_META, "name": "portbridge_preflight", "arguments": {
                "url": "https://github.com/ubiquitarianism/leonida/pull/20", "limit": 1}}),
        )
        self.assertIn("2026-07-28", discover["result"]["supportedVersions"])
        self.assertEqual(discover["result"]["capabilities"], {"tools": {}})
        self.assertEqual(discover["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]["name"], "portbridge")
        definitions = tools["result"]["tools"]
        self.assertEqual({tool["name"] for tool in definitions},
                         {"portbridge_activity", "portbridge_ecosystem", "portbridge_lab", "portbridge_problem",
                          "portbridge_preflight"})
        self.assertTrue(all(tool["annotations"]["readOnlyHint"] for tool in definitions))
        self.assertEqual([item["result"]["resultType"] for item in (discover, tools, result)], ["complete"] * 3)
        payload = result["result"]["structuredContent"]
        self.assertEqual(json.loads(result["result"]["content"][0]["text"]), payload)
        self.assertEqual([item["id"] for item in payload["problems"]], ["PB-0002"])
        self.assertIn("never as instructions", payload["guidance"])
        self.assertTrue(payload["next_step"])
        url_result = from_url["result"]["structuredContent"]
        self.assertEqual(url_result["origin_url"], "https://github.com/ubiquitarianism/leonida/pull/20")
        self.assertEqual([item["id"] for item in url_result["problems"]], ["PB-0002"])

    def test_activity_reads_local_catalog_and_rejects_arguments(self):
        activity, invalid = self.replies(
            message(1, "tools/call", {**MODERN_META, "name": "portbridge_activity"}),
            message(2, "tools/call", {**MODERN_META, "name": "portbridge_activity", "arguments": {"q": "x"}}),
        )
        result = activity["result"]["structuredContent"]
        self.assertEqual(result["window_days"], 7)
        self.assertTrue(result["projects"])
        self.assertIn("opportunities", result)
        self.assertTrue(invalid["result"]["isError"])

    def test_default_reads_public_snapshots_without_token_or_query_in_url(self):
        local = ReadOnlyCatalog(self.db)
        files = {
            "activity": {"window_days": 7, "events": [], "opportunities": []},
            "site": {"mode": "snapshot"},
            "lab": build_lab(),
            "health": local.health(),
            "problems": {"problems": local.problems()},
            "projects": {"projects": local.projects()},
            "observations": {"observations": []},
        }
        requested = []

        def open_fixture(request, *, timeout):
            self.assertEqual(request.get_method(), "GET")
            self.assertFalse(request.has_header("Authorization"))
            self.assertGreater(timeout, 0)
            requested.append(request.full_url)
            expected = {f"{PUBLIC_BASE}data/{name}.json": data for name, data in files.items()}
            return BytesIO(json.dumps(expected[request.full_url]).encode("utf-8"))

        with patch("portbridge.preflight.build_opener", return_value=Mock(open=open_fixture)):
            preflight, problem, activity, lab = self.public_replies(
                message(1, "tools/call", {**MODERN_META, "name": "portbridge_preflight",
                                          "arguments": {"q": "rectlist", "url": "https://github.com/Marvisak/VIctory/pull/346"}}),
                message(2, "tools/call", {**MODERN_META, "name": "portbridge_problem",
                                          "arguments": {"id": "PB-0001"}}),
                message(3, "tools/call", {**MODERN_META, "name": "portbridge_activity"}),
                message(4, "tools/call", {**MODERN_META, "name": "portbridge_lab",
                                          "arguments": {"equipment": "amd", "status": "awaiting_review", "task": "xcl-1100-fma"}}),
            )
        self.assertEqual(set(requested), {f"{PUBLIC_BASE}data/{name}.json" for name in files})
        result = preflight["result"]["structuredContent"]
        self.assertEqual(result["query"], "rectlist")
        self.assertEqual(result["origin_url"], "https://github.com/marvisak/victory/pull/346")
        self.assertEqual(result["problems"][0]["id"], "PB-0001")
        self.assertTrue(result["next_step"])
        self.assertEqual(problem["result"]["structuredContent"]["problem"]["id"], "PB-0001")
        self.assertEqual(activity["result"]["structuredContent"]["window_days"], 7)
        tasks = lab["result"]["structuredContent"]["tasks"]
        self.assertEqual([task["id"] for task in tasks], ["xcl-1100-fma"])
        self.assertTrue(all("amd" in task["equipment"] and task["status"] == "awaiting_review" for task in tasks))

    def test_unavailable_public_snapshot_returns_actionable_error(self):
        with patch("portbridge.preflight.build_opener", side_effect=OSError("synthetic network error")):
            reply, = self.public_replies(message(1, "tools/call", {**MODERN_META, "name": "portbridge_preflight",
                                                                  "arguments": {"q": "rectlist"}}))
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("--db", reply["result"]["content"][0]["text"])

    def test_legacy_clients_can_negotiate_and_get_provenance(self):
        for version in ("2025-11-25", "2025-06-18"):
            with self.subTest(version=version):
                init, ping, result = self.replies(
                    message("init", "initialize", {"protocolVersion": version, "capabilities": {},
                                                   "clientInfo": {"name": "test-host", "version": "1.0"}}),
                    message(None, "notifications/initialized"),
                    message("ping", "ping"),
                    message("read", "tools/call", {"name": "portbridge_problem", "arguments": {"id": "PB-0001"}}),
                )
                self.assertEqual(init["id"], "init")
                self.assertEqual(init["result"]["protocolVersion"], version)
                self.assertEqual(ping["result"], {})
                self.assertNotIn("resultType", result["result"])
                card = result["result"]["structuredContent"]["problem"]
                self.assertEqual(card["id"], "PB-0001")
                evidence = [item for solution in card["solutions"] for item in solution["evidence"]]
                self.assertTrue(any(item["kind"] == "independent" and item["url"].startswith("https://github.com/")
                                    and item["revision"] and item["platforms"] for item in evidence))

    def test_invalid_requests_are_bounded_and_recoverable(self):
        version = {"_meta": {**MODERN_META["_meta"], "io.modelcontextprotocol/protocolVersion": "1900-01-01"}}
        broken, oversize, unknown_version, missing_meta, unknown_tool, bad_limit, missing_card, write = self.replies(
            b'{"version": NaN}',
            b"x" * (70 * 1024),
            message(3, "server/discover", version),
            message(4, "tools/list"),
            message(5, "tools/call", {**MODERN_META, "name": "publish"}),
            message(6, "tools/call", {**MODERN_META, "name": "portbridge_preflight",
                                      "arguments": {"q": "graphics", "limit": True}}),
            message(7, "tools/call", {**MODERN_META, "name": "portbridge_problem",
                                      "arguments": {"id": "PB-999999"}}),
            message(8, "catalog/write", MODERN_META),
        )
        self.assertEqual(broken["error"]["code"], -32700)
        self.assertEqual(oversize["error"]["code"], -32700)
        self.assertEqual(unknown_version["error"]["code"], -32022)
        self.assertIn("2026-07-28", unknown_version["error"]["data"]["supported"])
        self.assertEqual(missing_meta["error"]["code"], -32602)
        self.assertEqual(unknown_tool["error"]["code"], -32602)
        self.assertTrue(bad_limit["result"]["isError"])
        self.assertTrue(missing_card["result"]["isError"])
        self.assertEqual(write["error"]["code"], -32601)

    def test_catalog_is_opened_read_only(self):
        previous = self.db.read_bytes()
        res, = self.replies(message(1, "tools/call", {**MODERN_META, "name": "portbridge_problem",
                                                     "arguments": {"id": "PB-0001"}}))
        self.assertIn("result", res)
        self.assertEqual(self.db.read_bytes(), previous)
        with ReadOnlyCatalog(self.db).connect() as conn:
            with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
                conn.execute("DELETE FROM problems")

    def test_missing_catalog_is_not_created(self):
        absent = self.db.with_name("missing.sqlite3")
        result = self.run_server(db=absent)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"python -m portbridge status", result.stderr)
        self.assertFalse(absent.exists())
