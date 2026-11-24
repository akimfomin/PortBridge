"""Loopback checks for private conversations and automated coordination."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from portbridge.__main__ import DEFAULT_SEED
from portbridge.backup import backup_database
from portbridge.catalog import Catalog
from portbridge.coordinator import run_coordination
from portbridge.exchange import Exchange
from portbridge.exchange_client import ExchangeClient, ExchangeClientError
from portbridge.exchange_demo import demo_server
from portbridge.export import export


class DiscussionTest(unittest.TestCase):
    def setUp(self):
        lifetime = ExitStack()
        self.addCleanup(lifetime.close)
        self.root = Path(lifetime.enter_context(TemporaryDirectory()))
        self.catalog = Catalog(self.root / "catalog.sqlite3", DEFAULT_SEED)
        self.exchange = Exchange(self.root / "exchange.sqlite3",
                                 problem_exists=lambda ident: self.catalog.problem(ident) is not None)
        self.port = lifetime.enter_context(demo_server(self.catalog, self.exchange))
        self.first_token, self.first = self.client("Team A", ["read", "contribute"])
        self.second_token, self.second = self.client("Team B", ["read", "contribute"])
        _, self.other = self.client("Team C", ["read", "contribute"])
        _, self.reviewer = self.client("Reviewer", ["review"])
        self.topic = "PB-0001"
        self.message = {"problem_id": self.topic, "client_id": "test-message-first",
                        "text": "Synthetic test discussion.\nTest scope only."}

    def client(self, label, scopes):
        token = self.exchange.create_principal(label, scopes)["token"]
        return token, ExchangeClient(self.port, token)

    def subscribe(self, client, problem=None, enabled=True):
        return client.request("subscribe", body={"problem_id": problem or self.topic, "enabled": enabled})

    def assert_status(self, status, call, *args, **options):
        with self.assertRaises(ExchangeClientError) as error:
            call(*args, **options)
        self.assertEqual(error.exception.status, status)

    def test_connected_clients_share_replies_and_receive_only_subscribed_updates(self):
        self.assert_status(403, self.first.request, "message", body=self.message)
        self.subscribe(self.first)
        self.subscribe(self.second)
        self.subscribe(self.other, "PB-0002")
        self.assert_status(400, self.first.request, "message", body={**self.message, "text": self.first_token})
        self.assert_status(403, self.other.request, "thread", query={"problem_id": self.topic})
        with ThreadPoolExecutor(3) as pool:
            start = time.monotonic()
            waiting = pool.submit(self.second.request, "updates", query={"wait_seconds": 5})
            sent = list(pool.map(lambda _: self.first.request("message", body=self.message), range(2)))
            updates = waiting.result(timeout=7)
        self.assertLess(time.monotonic() - start, 4)
        self.assertEqual(sent[0], sent[1])
        message, = [row["message"] for row in updates["events"]]
        self.assertEqual(message, sent[0]["message"])
        self.assertEqual(message["author"], "Team A")
        self.assertEqual(message["author_kind"], "participant")
        self.assertEqual(message["text"], self.message["text"])
        self.assertEqual(self.other.request("updates")["events"], [])
        self.assertEqual(self.second.request("updates", query={"after": updates["next_cursor"]})["events"], [])
        self.assert_status(409, self.first.request, "message", body={**self.message, "text": "Changed content."})
        self.assert_status(404, self.other.request, "message",
                           body={**self.message, "problem_id": "PB-0002", "reply_to": message["id"]})
        reply = {**self.message, "client_id": "test-message-reply", "reply_to": message["id"], "text": "Checked."}
        self.second.request("message", body=reply)
        self.assertEqual([row["author"] for row in self.first.request("thread", query={
            "problem_id": self.topic,
        })["messages"]], ["Team A", "Team B"])

        self.subscribe(self.second, enabled=False)
        self.assert_status(403, self.second.request, "thread", query={"problem_id": self.topic})
        self.assertEqual(self.second.request("updates")["events"], [])
        self.subscribe(self.second)
        self.subscribe(self.second)
        self.assertEqual(self.second.request("updates")["events"], [])
        self.assertEqual(len(self.second.request("thread", query={"problem_id": self.topic})["messages"]), 2)
        self.exchange.revoke_principal("Team B")
        self.assert_status(401, self.second.request, "updates")
        self.assert_status(401, self.second.request, "message", body=reply)

    def test_review_and_withdrawal_share_a_cursor_and_survive_backup(self):
        self.subscribe(self.first)
        self.subscribe(self.second)
        self.first.request("message", body=self.message)
        submission = {"problem_id": self.topic, "source_url": "https://github.com/Marvisak/VIctory/pull/346",
                      "revision": "a" * 40, "platform": "Test setup", "outcome": "failed",
                      "evidence_kind": "simulation", "summary": "Synthetic negative control"}
        result = self.first.request("submit", body=submission)["result"]
        events = self.second.request("updates", query={"limit": 1})
        self.assertEqual([item["kind"] for item in events["events"]], ["message"])
        self.assertEqual(self.second.request("updates", query={"after": events["next_cursor"]})["events"], [])
        self.reviewer.request("review", body={"result_id": result["id"], "decision": "accepted"})
        updates = self.second.request("updates", query={"after": events["next_cursor"]})
        self.assertEqual([item["kind"] for item in updates["events"]], ["result_accepted"])
        self.reviewer.request("withdraw", body={"result_id": result["id"], "reason": "Synthetic result superseded."})
        after = self.second.request("updates", query={"after": updates["next_cursor"]})
        self.assertEqual([item["kind"] for item in after["events"]], ["result_withdrawn"])
        self.assertEqual(after["events"][0]["result_id"], result["id"])
        self.assertEqual(len(self.second.request("poll")["events"]), 2)
        private = self.second.request("preflight", query={"q": self.topic})
        self.assertEqual(private["reviewed_reports"], [])
        self.assertNotIn(self.message["text"], json.dumps(private))

        restored = Exchange(backup_database(self.exchange.path, self.root / "restored.sqlite3"))
        self.assertEqual(restored.discussions.updates(self.second_token, after=updates["next_cursor"]), after)
        self.assertEqual(len(restored.discussions.thread(self.second_token, self.topic)["messages"]), 1)
        public = export(self.catalog, self.root / "public")
        for path in public.rglob("*"):
            if path.is_file():
                self.assertNotIn(self.message["text"].splitlines()[0].encode(), path.read_bytes())

    def test_opt_in_mcp_tools_can_be_used_from_two_separate_processes(self):
        def rpc(token, method, params, *, writable=False):
            args = [sys.executable, "-m", "portbridge.mcp", "--exchange-port", str(self.port)]
            if writable:
                args.append("--enable-discussion-writes")
            message = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {**params, "_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": {},
            }}}
            result = subprocess.run(args, input=json.dumps(message).encode() + b"\n", capture_output=True,
                                    env={**os.environ, "PORTBRIDGE_EXCHANGE_TOKEN": token}, check=True, timeout=8)
            return json.loads(result.stdout)

        observed = rpc(self.second_token, "tools/list", {})["result"]["tools"]
        self.assertNotIn("portbridge_send_message", {item["name"] for item in observed})
        allowed = rpc(self.first_token, "tools/list", {}, writable=True)["result"]["tools"]
        notice, = [item for item in allowed if item["name"] == "portbridge_send_message"]
        self.assertFalse(notice["annotations"]["readOnlyHint"])
        self.subscribe(self.first)
        self.subscribe(self.second)
        posted = rpc(self.first_token, "tools/call", {"name": "portbridge_send_message", "arguments": self.message},
                     writable=True)["result"]["structuredContent"]["message"]
        result = rpc(self.second_token, "tools/call", {"name": "portbridge_updates", "arguments": {}})
        received, = result["result"]["structuredContent"]["events"]
        self.assertEqual(received["message"], posted)

    def test_portbridge_posts_actions_and_revises_stale_links(self):
        self.subscribe(self.first)
        self.subscribe(self.second)
        self.subscribe(self.other, "PB-0002")
        origin = "https://github.com/ubiquitarianism/leonida/pull/207"
        related = "https://github.com/LeonidaReforge/Leonida/pull/480"

        def observation(project, ident, url, revision, second):
            return {"project": project, "kind": "pr", "source_id": str(ident), "url": url,
                    "title": "Synthetic revision comparison", "status": "open",
                    "updated_at": f"2026-11-24T08:00:0{second}Z", "metadata": {"head_sha": revision}}

        self.catalog.record_sync({"items": [observation("continued", 207, origin, "a" * 40, 1),
                                            observation("reforge", 480, related, "a" * 40, 1)]})
        for client in (self.first, self.second):
            client.request("register", body={"problem_id": self.topic})
        self.assertEqual(run_coordination(self.catalog, self.exchange), 2)
        self.assertEqual(run_coordination(self.catalog, self.exchange), 0)
        notices = self.second.request("updates")
        self.assertEqual(len(notices["events"]), 2)
        self.assertTrue(all(row["message"]["author_kind"] == "portbridge" for row in notices["events"]))
        self.assertEqual(self.other.request("updates")["events"], [])
        self.assert_status(403, self.other.request, "coordination", query={"problem_id": self.topic})
        coordination = self.second.request("coordination", query={"problem_id": self.topic})
        self.assertEqual(coordination["links"][0]["revision"], "a" * 40)
        self.assertEqual(coordination["drafts"][0]["target_url"], origin)
        self.assertEqual(coordination["drafts"][0]["source_url"], related.lower())
        self.assertIn("[PortBridge](https://github.com/akimfomin/PortBridge)", coordination["drafts"][0]["message"])

        self.catalog.record_sync({"items": [observation("reforge", 480, related, "b" * 40, 2)]})
        self.assertEqual(run_coordination(self.catalog, self.exchange), 1)
        self.assertEqual(run_coordination(self.catalog, self.exchange), 0)
        revised, = self.second.request("updates", query={"after": notices["next_cursor"]})["events"]
        self.assertEqual(revised["message"]["author"], "PortBridge")
        self.assertEqual(revised["message"]["source_url"], related.lower())
        self.assertEqual(self.second.request("coordination", query={"problem_id": self.topic}),
                         {"links": [], "drafts": []})
