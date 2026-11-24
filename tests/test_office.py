"""Real loopback exercises of the shared plan and project discovery workflow."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from portbridge.__main__ import DEFAULT_SEED
from portbridge.catalog import Catalog
from portbridge.coordinator import run_coordination
from portbridge.discovery import refresh_project_leads
from portbridge.exchange import Exchange
from portbridge.exchange_client import ExchangeClient, ExchangeClientError
from portbridge.exchange_demo import demo_server
from portbridge.export import export
from portbridge.github import _technical
from portbridge.mcp import PortBridgeMCP
from portbridge.office_engine import refresh_external_sources


ORIGIN = "https://github.com/Marvisak/VIctory/pull/571"
COMPARISON = "https://github.com/ivall/xcl/pull/544"
CONTINUED = "https://github.com/ubiquitarianism/leonida/pull/207"
RECTANGLES = "https://github.com/Marvisak/VIctory/pull/346"
NEW_SOURCE = "https://github.com/new-team/test-recompiler/pull/14"
NEW_REPO = "new-team/test-recompiler"


class OfficeTest(unittest.TestCase):
    def setUp(self):
        lifetime = ExitStack()
        self.addCleanup(lifetime.close)
        self.root = Path(lifetime.enter_context(TemporaryDirectory()))
        self.catalog = Catalog(self.root / "catalog.sqlite3", DEFAULT_SEED)
        self.exchange = Exchange(self.root / "exchange.sqlite3", problem_exists=lambda ident: self.catalog.problem(ident) is not None,
                                 find_curated_topic=self.catalog.curated_topic)
        self.port = lifetime.enter_context(demo_server(self.catalog, self.exchange))
        self.first = self.client("Team A", ["read", "contribute", "review"])
        self.second = self.client("Team B", ["read", "contribute"])
        self.reviewer = self.client("Reviewer", ["read", "review"])
        self.observer = self.client("Observer", ["read"])
        self.topic = self.accept_topic(ORIGIN)
        self.record("victory", ORIGIN, "a", "Handle `ds_read_{u8,i8,u16,i16}` and `ds_write_{b8,b16}`.")
        self.record("xcl", COMPARISON, "b", "Checked `DS_READ_U8/I8/U16_D16/_HI` and `DS_WRITE_B8_D16_HI`.")

    def client(self, name, scopes):
        return ExchangeClient(self.port, self.exchange.create_principal(name, scopes)["token"])

    def accept_topic(self, url):
        self.first.request("propose-topic", body={"source_url": url, "title": "Synthetic barrier smoke test"})
        result = self.reviewer.request("review-topic", body={"source_url": url, "decision": "accepted"})
        ident = result["topic"]["id"]
        for client in (self.first, self.second, self.reviewer):
            client.request("subscribe", body={"problem_id": ident, "enabled": True})
        return ident

    def record(self, project, url, letter, description="", second=1):
        item = {"project": project, "kind": "pr", "source_id": url.rsplit("/", 1)[-1], "url": url,
                "title": "Synthetic scope fixture", "status": "open", "updated_at": f"2026-11-24T08:00:0{second}Z",
                "metadata": {"head_sha": letter * 40, "technical": _technical({"body": description}, [], {})}}
        self.catalog.record_sync({"items": [item]})

    def run_office(self):
        return run_coordination(self.catalog, self.exchange, office=True)

    def plan(self, ident=None, client=None):
        plans = (client or self.second).request("plans")["plans"]
        return next(plan for plan in plans if ident is None or plan["id"] == ident)

    def submit(self, *, url=ORIGIN, revision="a", label="independent", summary="Synthetic fixture for the evidence review"):
        return self.first.request("submit", body={"problem_id": self.topic, "source_url": url,
            "revision": revision * 40, "platform": "Synthetic runner", "evidence_kind": label,
            "outcome": "passed", "summary": summary})["result"]

    def rejected(self, code, client, route, body):
        with self.assertRaises(ExchangeClientError) as raised:
            client.request(route, body=body)
        self.assertEqual(raised.exception.status, code)

    def test_office_coordinates_two_teams_and_invalidates_dependent_work(self):
        run_coordination(self.catalog, self.exchange)
        self.assertEqual(self.second.request("plans")["plans"], [])
        self.assertGreaterEqual(self.run_office(), 2)
        self.assertEqual(self.run_office(), 0)
        draft = self.plan()
        ident = draft["id"]
        self.assertEqual((draft["author"], draft["basis"], draft["state"]),
                         ("PortBridge", "instruction_variants", "draft"))
        self.assertEqual((draft["origin_revision"], draft["comparison_revision"]), ("a" * 40, "b" * 40))
        self.assertEqual(draft["outreach_drafts"], [])
        self.assertEqual(self.observer.request("plans")["plans"], [])
        self.assertTrue(any(topic["id"] == self.topic for topic in self.observer.request("plans")["topics"]))
        self.reviewer.request("plan-review", body={"plan_id": ident, "decision": "accept", "priority": 1})
        drafts = self.plan(ident)["outreach_drafts"]
        self.assertEqual({draft["target_url"] for draft in drafts}, {ORIGIN.lower(), COMPARISON})
        for draft in drafts:
            self.assertIn("[PortBridge](https://github.com/akimfomin/PortBridge)", draft["message"])

        self.record("continued", CONTINUED, "c")
        self.record("victory", RECTANGLES, "d")
        next_plan = self.first.request("plan-propose", body={"problem_id": self.topic, "objective": "Synthetic next step",
                                       "origin_url": CONTINUED, "comparison_url": RECTANGLES})["plan"]
        downstream = next_plan["id"]
        self.rejected(403, self.first, "plan-review", {"plan_id": downstream, "decision": "accept"})
        self.reviewer.request("plan-review", body={"plan_id": downstream, "decision": "accept", "requires": [ident]})
        self.assertEqual(self.plan(downstream)["state"], "blocked")
        self.assertEqual(self.plan(ident)["unblocks"], 1)
        self.rejected(409, self.second, "plan-claim", {"plan_id": downstream})
        self.first.request("plan-claim", body={"plan_id": ident})
        self.rejected(409, self.second, "plan-claim", {"plan_id": ident})
        wrong = self.submit(revision="e")
        self.rejected(409, self.first, "plan-result", {"plan_id": ident, "result_id": wrong["id"]})
        wrong_project = self.submit(url=COMPARISON)
        self.rejected(409, self.first, "plan-result", {"plan_id": ident, "result_id": wrong_project["id"]})
        report = self.submit()
        self.first.request("plan-result", body={"plan_id": ident, "result_id": report["id"]})
        self.assertIsNone(self.plan(ident)["report"])
        self.assertEqual(self.plan(ident, client=self.reviewer)["report"]["summary"], report["summary"])
        self.reviewer.request("review", body={"result_id": report["id"], "decision": "accepted"})
        self.rejected(403, self.first, "plan-decision", {"plan_id": ident, "decision": "adopt", "reason": "Self approval"})
        self.assertEqual(self.plan(ident)["state"], "decision")
        progress = self.second.request("plans")["progress"]
        self.assertEqual(progress["verified"], 1)
        self.assertIn(ident, progress["needs"])
        self.assertIn(ident, progress["milestones"])
        self.assertTrue(any(project["name"] == "XCL" for project in progress["by_project"]))
        self.assertGreater(self.run_office(), 0)
        self.reviewer.request("plan-decision", body={"plan_id": ident, "decision": "adopt", "reason": "Synthetic acceptance"})
        self.assertEqual(self.plan(downstream)["state"], "ready")
        progress = self.second.request("plans")["progress"]
        self.assertEqual((progress["available"], progress["adopted"]), (1, 1))
        self.assertGreater(self.run_office(), 0)
        messages = self.second.request("thread", query={"problem_id": self.topic})["messages"]
        self.assertTrue(any("Зависимости" in message["text"] for message in messages))

        self.record("victory", ORIGIN, "f", "Handle `ds_read_{u8,i8,u16,i16}`.", second=2)
        self.rejected(409, self.second, "plan-claim", {"plan_id": downstream})
        self.run_office()
        self.assertEqual(self.plan(ident)["state"], "superseded")
        self.assertEqual(self.plan(ident)["decision"], "adopt")
        self.assertEqual(self.plan(downstream)["state"], "blocked")
        self.assertEqual(self.run_office(), 0)
        public_site = export(self.catalog, self.root / "public")
        self.assertFalse((public_site / "office.html").exists())
        for path in public_site.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"Synthetic acceptance", path.read_bytes())

    def test_simulation_can_inform_investigation_but_not_unlock_adoption(self):
        self.run_office()
        ident = self.plan()["id"]
        self.reviewer.request("plan-review", body={"plan_id": ident, "decision": "accept"})
        self.first.request("plan-claim", body={"plan_id": ident})
        report = self.submit(label="simulation")
        self.first.request("plan-result", body={"plan_id": ident, "result_id": report["id"]})
        self.reviewer.request("review", body={"result_id": report["id"], "decision": "accepted"})
        decision = {"plan_id": ident, "decision": "adopt", "reason": "Synthetic result"}
        self.rejected(409, self.reviewer, "plan-decision", decision)
        self.reviewer.request("plan-decision", body={**decision, "decision": "investigate"})
        self.assertEqual(self.plan(ident)["decision"], "investigate")

    def test_agent_tools_respect_read_only_mode_and_can_claim_with_opt_in(self):
        self.run_office()
        ident = self.plan()["id"]
        self.reviewer.request("plan-review", body={"plan_id": ident, "decision": "accept"})
        observer = PortBridgeMCP(None, self.second)
        writer = PortBridgeMCP(None, self.second, discussion_writes=True)
        self.assertNotIn("portbridge_claim_plan", observer.discussion_tools)
        seen = observer.run_discussion_tool("portbridge_plans", {})["structuredContent"]["plans"]
        self.assertEqual(seen[0]["state"], "ready")
        claimed = writer.run_discussion_tool("portbridge_claim_plan", {"plan_id": ident})["structuredContent"]["plan"]
        self.assertEqual(claimed["volunteer"], "Team B")

    def test_html_shell_is_local_and_requires_a_key_for_data(self):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(connection.close)
        connection.request("GET", "/office")
        with connection.getresponse() as response:
            self.assertEqual(response.status, 200)
            self.assertIn("Ключ участника", response.read().decode())
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        connection.request("GET", "/api/v1/exchange/plans")
        with connection.getresponse() as response:
            self.assertEqual(response.status, 401)

    def test_nomination_can_become_a_scoped_comparison(self):
        self.record("victory", ORIGIN, "a", f"Related public comparison in {NEW_SOURCE}", second=2)
        self.record("xcl", COMPARISON, "b", f"Test tooling at https://github.com/{NEW_REPO}", second=2)
        entry, = self.first.request("office-projects")["projects"]
        self.assertEqual((entry["repo"], entry["state"], entry["project_count"]), (NEW_REPO, "mentioned", 2))
        proposal = {"repo": NEW_REPO, "evidence_url": NEW_SOURCE, "next_step": "Compare one reproducible shader fixture"}
        self.first.request("project-nominate", body=proposal)
        self.rejected(403, self.first, "project-review", {"repo": NEW_REPO, "decision": "compare"})
        draft = self.first.request("plan-propose", body={"problem_id": self.topic, "objective": "Check external source",
                                   "origin_url": ORIGIN, "comparison_url": NEW_SOURCE})["plan"]
        self.assertFalse(draft["sources_available"])
        with patch("portbridge.github.public_source_revisions", return_value={NEW_SOURCE: "e" * 40}) as check:
            refresh_external_sources(self.exchange)
            check.assert_not_called()
            self.reviewer.request("project-review", body={"repo": NEW_REPO, "decision": "compare"})
            refresh_external_sources(self.exchange)
            check.assert_called_once_with(self.exchange.path, [NEW_SOURCE])
        self.run_office()
        self.assertEqual(self.plan(draft["id"])["comparison_revision"], "e" * 40)
        self.reviewer.request("plan-review", body={"plan_id": draft["id"], "decision": "accept"})
        self.assertEqual(self.plan(draft["id"])["state"], "ready")
        self.reviewer.request("project-review", body={"repo": NEW_REPO, "decision": "defer"})
        self.rejected(409, self.second, "plan-claim", {"plan_id": draft["id"]})
        self.run_office()
        self.assertEqual(self.plan(draft["id"])["state"], "waiting_sources")

    def test_repository_sweep_filters_visibility_and_keeps_last_complete_results(self):
        record = {"full_name": NEW_REPO, "private": False, "archived": False, "fork": False}
        raw = {"incomplete_results": False, "items": [
            record,
            {**record, "full_name": "example/private-repo", "private": True},
            {**record, "full_name": "example/internal-repo", "visibility": "internal"},
            {**record, "full_name": "example/archived-repo", "archived": True},
            {**record, "full_name": "example/forked-repo", "fork": True},
            {**record, "full_name": "Marvisak/VIctory"},
        ]}
        with patch("portbridge.github._Sync._request", return_value=(raw, {})) as check:
            refresh_project_leads(self.exchange)
            self.assertEqual(check.call_count, 3)
            refresh_project_leads(self.exchange)
            self.assertEqual(check.call_count, 3)
        entry, = self.first.request("office-projects")["projects"]
        self.assertEqual((entry["repo"], entry["state"], len(entry["search_focus"])), (NEW_REPO, "found", 3))
        with self.exchange._connect() as db:
            db.execute("UPDATE office_project_search SET checked_at=0")
        with patch("portbridge.github._Sync._request", return_value=({"incomplete_results": True, "items": []}, {})):
            refresh_project_leads(self.exchange)
        self.assertEqual(self.first.request("office-projects")["projects"], [entry])

    def test_claim_is_atomic_and_revocation_releases_it(self):
        self.run_office()
        ident = self.plan()["id"]
        self.reviewer.request("plan-review", body={"plan_id": ident, "decision": "accept"})

        def claim(client):
            try:
                return client.request("plan-claim", body={"plan_id": ident})["plan"]["volunteer"]
            except ExchangeClientError as error:
                return error.status

        with ThreadPoolExecutor(2) as workers:
            results = list(workers.map(claim, (self.first, self.second)))
        self.assertEqual(results.count(409), 1)
        volunteer = next(value for value in results if value != 409)
        self.exchange.revoke_principal(volunteer)
        self.run_office()
        self.assertEqual(self.plan(ident, client=self.reviewer)["state"], "ready")
