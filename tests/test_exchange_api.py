from http.client import HTTPConnection
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib.parse import urlencode

from portbridge.__main__ import DEFAULT_SEED, make_server
from portbridge.backup import backup_database
from portbridge.catalog import Catalog
from portbridge.exchange import Exchange
from portbridge.exchange_api import MAX_BODY_BYTES, PREFIX


class ExchangeAPITest(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(prefix="portbridge-exchange-http-")
        self.addCleanup(temp.cleanup)
        workspace = Path(temp.name)
        self.exchange = Exchange(workspace / "exchange.sqlite3",
                                 problem_exists=lambda ident: ident in {"PB-0001", "PB-0002"})
        self.worker = self.exchange.create_principal("agent-one", {"read", "contribute"})["token"]
        self.reviewer = self.exchange.create_principal("reviewer-two", {"read", "review"})["token"]
        self.server = make_server(Catalog(workspace / "catalog.sqlite3", DEFAULT_SEED), 0, exchange=self.exchange)
        thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.addCleanup(self.server.server_close)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.server.shutdown)
        self.result = {"problem_id": "PB-0001", "source_url": "https://github.com/Marvisak/VIctory/pull/346",
                       "revision": "a" * 40, "platform": "Windows 11, D3D12 synthetic test",
                       "evidence_kind": "independent", "outcome": "passed",
                       "summary": "A synthetic primitive covered the eight expected pixels."}

    def request(self, method, route, token=None, *, payload=None, raw=None, headers=None):
        data = dict(headers or {})
        if token is not None:
            data["Authorization"] = f"Bearer {token}"
        if payload is not None:
            raw = json.dumps(payload).encode("utf-8")
        if raw is not None:
            data.setdefault("Content-Type", "application/json")
        client = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            path = route if route.startswith("/") else f"{PREFIX}/{route}"
            client.request(method, path, body=raw, headers=data)
            response = client.getresponse()
            raw = response.read()
            return response.status, json.loads(raw) if raw else None, dict(response.getheaders())
        finally:
            client.close()

    def test_work_submit_review_and_read_two_agent_flow(self):
        status, registered, _ = self.request("POST", "register", self.worker,
                                             payload={"problem_id": "PB-0001", "ttl_seconds": 120})
        self.assertEqual(status, 200)
        self.assertEqual(registered["work"]["actor"], "agent-one")
        _, active, _ = self.request("GET", "work?problem_id=PB-0001", self.reviewer)
        self.assertEqual(active["work"], [registered["work"]])

        status, submitted, _ = self.request("POST", "submit", self.worker, payload=self.result)
        self.assertEqual(status, 200)
        result = submitted["result"]
        self.assertEqual(result["status"], "pending")
        self.assertEqual(self.request("GET", "pending", self.worker)[0], 403)
        self.assertEqual(self.request("GET", "evidence?problem_id=PB-0001", self.worker)[1], {"results": []})
        self.assertEqual(self.request("GET", "poll", self.reviewer)[1]["events"], [])
        _, pending, _ = self.request("GET", "pending?limit=1", self.reviewer)
        self.assertEqual(pending["results"], [result])

        decision = {"result_id": result["id"], "decision": "accepted", "reason": "Source and test scope checked."}
        self.assertEqual(self.request("POST", "review", self.worker, payload=decision)[0], 403)
        status, accepted, _ = self.request("POST", "review", self.reviewer, payload=decision)
        self.assertEqual(status, 200)
        self.assertEqual(accepted["result"]["status"], "accepted")
        self.assertEqual(accepted["result"]["reviewer"], "reviewer-two")

        _, facts, _ = self.request("GET", "evidence?problem_id=PB-0001&limit=1", self.worker)
        self.assertEqual(facts["results"], [accepted["result"]])
        self.assertEqual(self.request("GET", "evidence?problem_id=PB-0002", self.worker)[1], {"results": []})
        _, updates, _ = self.request("GET", "poll?after=0&limit=1", self.worker)
        event, = updates["events"]
        self.assertEqual(event["kind"], "result_accepted")
        self.assertEqual(event["result"]["id"], result["id"])
        self.assertEqual(self.request("GET", f"poll?after={updates['next_cursor']}", self.worker)[1]["events"], [])
        changed = {**decision, "decision": "rejected"}
        self.assertEqual(self.request("POST", "review", self.reviewer, payload=changed)[0], 409)

    def test_private_routes_off_by_default_and_token_is_header_only(self):
        status, public, _ = self.request("GET", "/api/v1")
        self.assertEqual(status, 200)
        self.assertTrue(public["read_only"] and public["exchange_enabled"])
        self.assertEqual(self.request("POST", "/api/v1/preflight", self.worker, payload={"q": "rectlist"})[0], 405)
        status, _, headers = self.request("GET", "poll", "public-example-invalid")
        self.assertEqual(status, 401)
        self.assertIn("Bearer", headers["WWW-Authenticate"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.request("GET", f"poll?token={self.worker}")[0], 401)
        self.assertEqual(self.request("POST", "register", self.reviewer, payload={"problem_id": "PB-0001"})[0], 403)
        self.server.exchange = None
        self.assertFalse(self.request("GET", "/api/v1")[1]["exchange_enabled"])
        self.assertEqual(self.request("POST", "submit", self.worker, payload=self.result)[0], 404)

    def test_new_topic_reaches_an_isolated_client_and_can_be_withdrawn(self):
        reader = self.exchange.create_principal("copy-of-client-two", {"read"})["token"]
        source = "https://github.com/ivall/xcl/issues/772"
        path = "preflight?" + urlencode({"url": source})
        proposal = {"source_url": source, "title": "Wave64 lane behavior"}
        self.assertEqual(self.request("POST", "propose-topic", self.worker, payload=proposal)[1]["topic"]["status"],
                         "submitted")
        retry = {**proposal, "source_url": source.replace("/ivall/xcl/", "/IVALL/XCL/")}
        self.assertEqual(self.request("POST", "propose-topic", self.worker, payload=retry)[0], 200)
        self.assertEqual(self.request("GET", "pending-topics", reader)[0], 403)
        self.assertIsNone(self.request("GET", path, reader)[1]["exchange_topic"])
        listed, = self.request("GET", "pending-topics", self.reviewer)[1]["topics"]
        decision = {"source_url": source, "decision": "accepted"}
        approved = self.request("POST", "review-topic", self.reviewer, payload=decision)[1]["topic"]
        ident = approved["id"]
        self.assertEqual(ident, listed["id"])
        self.assertEqual(self.request("POST", "propose-topic", self.worker, payload=proposal)[1]["topic"]["id"], ident)
        self.assertEqual(self.request("POST", "register", self.worker, payload={"problem_id": ident})[0], 200)

        body = {**self.result, "problem_id": ident, "source_url": source, "outcome": "failed",
                "evidence_kind": "simulation", "summary": "Synthetic negative control."}
        result = self.request("POST", "submit", self.worker, payload=body)[1]["result"]
        self.assertEqual(self.request("GET", "pending", reader)[0], 403)
        self.assertEqual(self.request("GET", path, reader)[1]["reviewed_reports"], [])
        acceptance = {"result_id": result["id"], "decision": "accepted"}
        self.assertEqual(self.request("POST", "review", self.reviewer, payload=acceptance)[0], 200)
        self.assertEqual(self.request("POST", "submit", self.worker, payload=body)[1]["result"]["id"], result["id"])
        self.assertEqual(self.request("POST", "review", self.reviewer, payload=acceptance)[0], 409)
        events = self.request("GET", "poll", reader)[1]
        self.assertEqual(len(events["events"]), 1)

        environment = {**os.environ, "PORTBRIDGE_EXCHANGE_TOKEN": reader}
        port = str(self.server.server_port)
        cli = subprocess.run([sys.executable, "-m", "portbridge.preflight", "--exchange-port", port, "--url", source],
                             env=environment, capture_output=True, check=True, timeout=8)
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                      "io.modelcontextprotocol/clientCapabilities": {}},
            "name": "portbridge_preflight", "arguments": {"url": source},
        }}
        mcp = subprocess.run([sys.executable, "-m", "portbridge.mcp", "--exchange-port", port],
                             env=environment, input=json.dumps(call).encode() + b"\n",
                             capture_output=True, check=True, timeout=8)
        cli_result, mcp_result = json.loads(cli.stdout), json.loads(mcp.stdout)["result"]["structuredContent"]
        for response in (cli_result, mcp_result):
            self.assertEqual(response["exchange_topic"]["id"], ident)
            self.assertEqual(response["reviewed_reports"][0]["outcome"], "failed")
            self.assertEqual(response["report_contexts"][str(result["id"])]["revision_status"], "unknown")
            self.assertIsNone(response["first_check"])
        self.assertNotIn("exchange_topic", self.request("GET", "/api/v1/" + path)[1])

        self.exchange.revoke_principal("agent-one")
        self.assertEqual(self.request("GET", path, self.worker)[0], 401)
        pending_user = self.exchange.create_principal("pending-agent", {"read", "contribute"})["token"]
        self.request("POST", "submit", pending_user, payload={**body, "revision": "b" * 40})
        backup = backup_database(self.exchange.path, self.exchange.path.parent / "restored.sqlite3")
        restored = Exchange(backup, problem_exists=lambda _ident: False)
        self.assertEqual(restored.authenticate(self.reviewer)["scopes"], ["read", "review"])
        self.assertEqual(len(restored.pending_results(self.reviewer)), 1)
        self.assertEqual(restored.find_topic(reader, source_url=source)["id"], ident)
        self.assertEqual(restored.poll_events(reader), events)
        self.server.exchange = restored
        self.assertEqual(self.request("GET", path, self.worker)[0], 401)
        for _ in range(2):
            self.assertEqual(self.request("POST", "withdraw", self.reviewer, payload={
                "result_id": result["id"], "reason": "Simulation superseded.",
            })[0], 200)
        self.assertEqual(self.request("GET", path, reader)[1]["reviewed_reports"], [])
        followup = self.request("GET", f"poll?after={events['next_cursor']}", reader)[1]
        self.assertEqual([item["kind"] for item in followup["events"]], ["result_withdrawn"])
        self.assertNotIn("Synthetic negative control", json.dumps(self.request("GET", "poll", reader)[1]))

    def test_private_preflight_reads_reviewed_simulation_without_promotion(self):
        path = "preflight?q=PB-0001&limit=1"
        self.assertEqual(self.request("GET", path)[0], 401)
        _, submitted, _ = self.request("POST", "submit", self.worker,
                                       payload={**self.result, "evidence_kind": "simulation"})
        _, before, _ = self.request("GET", path, self.worker)
        self.assertEqual(before["reviewed_reports"], [])
        payload = {"result_id": submitted["result"]["id"], "decision": "accepted"}
        _, accepted, _ = self.request("POST", "review", self.reviewer, payload=payload)
        status, after, _ = self.request("GET", path, self.worker)
        self.assertEqual(status, 200)
        self.assertEqual(after["problems"], before["problems"])
        self.assertEqual(after["reviewed_reports"], [accepted["result"]])
        self.assertEqual(after["reviewed_reports"][0]["evidence_kind"], "simulation")
        _, unrelated, _ = self.request("GET", path + "&url=https://github.com/Marvisak/VIctory/pull/641", self.worker)
        self.assertIsNone(unrelated["first_check"])
        self.assertEqual(unrelated["reviewed_reports"], [])
        self.assertEqual(self.request("GET", "preflight?q=PB-0002", self.reviewer)[1]["reviewed_reports"], [])
        self.assertNotIn("reviewed_reports", self.request("GET", f"/api/v1/{path}")[1])

    def test_methods_origin_and_body_validation_prevent_mutation(self):
        status, body, headers = self.request("HEAD", "register", self.worker)
        self.assertEqual((status, body, headers["Allow"]), (405, None, "POST"))
        status, body, headers = self.request("HEAD", "work", self.worker)
        self.assertEqual(status, 200)
        self.assertIsNone(body)
        self.assertGreater(int(headers["Content-Length"]), 0)

        for headers in ({"Host": "example.invalid"}, {"Origin": "https://example.invalid"},
                        {"Origin": "http://127.0.0.1"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("POST", "submit", self.worker, payload=self.result, headers=headers)[0], 403)
        origin = f"http://127.0.0.1:{self.server.server_port}"
        self.assertEqual(self.request("GET", "work", self.worker, headers={"Origin": origin})[0], 200)
        status, _, headers = self.request("OPTIONS", "register", self.worker)
        self.assertEqual(status, 405)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

        cases = (
            ("submit", {"Content-Type": "text/plain"}, b"{}", 415),
            ("submit", {"Content-Length": str(MAX_BODY_BYTES + 1)}, b"{}", 413),
            ("submit", {"Transfer-Encoding": "chunked"}, b"{}", 400),
            ("register", {}, b'{"problem_id":"PB-0001","problem_id":"PB-0002"}', 400),
            ("register", {}, b'{"problem_id":"PB-0001","ttl_seconds":NaN}', 400),
            ("register", {}, b"[42]", 400),
            ("register?token=ignored", {}, b'{"problem_id":"PB-0001"}', 400),
        )
        for route, headers, raw, status in cases:
            with self.subTest(route=route, status=status):
                self.assertEqual(self.request("POST", route, self.worker, raw=raw, headers=headers)[0], status)
        self.assertEqual(self.request("GET", "poll?limit=1&limit=2", self.worker)[0], 400)
        self.assertEqual(self.request("GET", "work", self.worker)[1], {"work": []})
        self.assertEqual(self.request("GET", "pending", self.reviewer)[1], {"results": []})
