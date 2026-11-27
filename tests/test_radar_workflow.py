"""M3 durability and trust boundary checks with controlled local actors."""
from concurrent.futures import ThreadPoolExecutor
import json
from datetime import datetime, timezone
from unittest.mock import patch

from portbridge import code_search
from portbridge.catalog import ReadOnlyCatalog
from portbridge.community import filter_impact, people
from portbridge.exchange import Conflict, Exchange, PermissionDenied
from portbridge.export import export
from portbridge.github import Unavailable
from portbridge.lab import build_lab
from portbridge.lab_workflow import apply, dashboard
from portbridge.mcp import PortBridgeMCP
from portbridge.preflight import preflight
from portbridge.radar_scan import classify, refresh
from portbridge.radar_store import radar_view, recent, timestamp
from test_portbridge import CatalogFixture

LEFT = "https://github.com/LooperSalty/AnyXboxX/pull/9991"
RIGHT = "https://github.com/Marvisak/VIctory/pull/9992"
NOW = int(datetime.now(timezone.utc).timestamp())


class RadarWorkflowTest(CatalogFixture):
    def setUp(self):
        super().setUp()
        self.exchange = Exchange(self.workspace / "authorization.sqlite3")
        self.first = self.exchange.create_principal("volunteer-one", ["read","contribute","review"])["token"]
        self.second = self.exchange.create_principal("volunteer-two", ["read","contribute"])["token"]
        self.reviewer = self.exchange.create_principal("scope-reviewer", ["read","review"])["token"]
        self.serial = 0
        self.seed()
        self.task = next(card for card in build_lab(self.catalog,now=NOW)["tasks"] if card.get("candidate_id"))["id"]

    def seed(self, head="a"*40, now=NOW):
        def row(url, slug, pin, target):
            return {"project":slug,"kind":"pr","source_id":url.rsplit("/",1)[1],"url":url,
                    "title":"Keep stable memory budget eviction with fence completion",
                    "status":"open","updated_at":timestamp(now),"fetched_at":timestamp(now),
                    "metadata":{"head_sha":pin,"technical":{"references":[target] if target else [],
                                 "signals":["vkgetfencestatus"],"terms":["memory budget"]}}}
        self.rows = [row(LEFT,"anyxboxx",head,RIGHT),row(RIGHT,"victory","b"*40,"")]
        self.catalog.record_sync({"items":self.rows},update_health=False)
        return refresh(self.catalog,now=now)

    def act(self, actor, action, *, now=NOW, request=None, **kwargs):
        self.serial += 1
        args = {"request_id":request or f"request-{self.serial:05}", "task":self.task, **kwargs}
        return apply(self.catalog,self.exchange,actor,action,args,now=now)

    def payload(self, outcome="PASS"):
        return dict(revisions=["a"*40,"b"*40], environment="Public fixture VM",
                    equipment="CPU", commands="compare sanitized source",outcome=outcome,
                    expected="both read the fence", observed="matched" if outcome=="PASS" else "different",
                    limitations="controlled test", ai_assistance="fixture", artifact_sha256="a"*64,
                    source_url=RIGHT,share_public=True)

    def private_review(self, report, **kwargs):
        return self.act(self.reviewer,"review",report_id=report["report_id"],decision="reviewed",
                        note="Independent review fixture",checked_artifact=True,**kwargs)

    def test_existing_lab_and_real_output_paths_preserved(self):
        self.assertEqual(len(build_lab(self.catalog)["tasks"]),17)
        task = build_lab(self.catalog,task=self.task,kind="source-only",os="Windows")["tasks"][0]
        self.assertEqual(task["workflow_state"],"draft")
        self.assertTrue(task["prompt"] and task["criteria"]["skip"])
        mcp=PortBridgeMCP(self.catalog)
        result=mcp.run_tool({"name":"portbridge_lab","arguments":{"task":self.task,"kind":"source-only"}})
        self.assertEqual(json.loads(result["content"][0]["text"])["tasks"][0]["id"], self.task)
        path=export(self.catalog,self.workspace / "published")
        radar=json.loads((path/"data/radar.json").read_bytes())
        self.assertEqual(radar["catalog"][0]["task_id"], self.task)
        self.assertFalse(radar["external_delivery"])
        self.assertEqual(refresh(self.catalog,now=NOW)["seen"],0)

    def test_uncited_mechanism_is_visible_in_radar_without_automatic_task(self):
        first = {**self.rows[0], "title": "Fix BVH node fetch for directory lookup",
                 "metadata": {"head_sha": "c" * 40, "technical": {}}}
        second = {**self.rows[1], "title": "Fix BVH node reads for second-half boundaries",
                  "metadata": {"head_sha": "d" * 40, "technical": {}}}
        self.catalog.record_sync({"items": [first, second]}, update_health=False)
        refresh(self.catalog, now=NOW)
        card = next(candidate for candidate in radar_view(self.catalog, NOW)["candidates"]
                    if candidate["kind"] == "shared_mechanism")
        self.assertEqual((card["confidence"], card["signals"]), ("research", ["bvh/node-fetch"]))
        self.assertIsNone(card.get("task_id"))

    def test_indexed_source_review_prepares_one_draft_without_adoption_credit(self):
        donor = "https://github.com/Example/Graphics/blob/" + "e" * 40
        reference = {"repo": "Example/Graphics", "revision": "e" * 40, "path": "tests/cache.cpp",
                     "license": "MIT", "license_url": donor + "/LICENSE"}
        item = {**self.rows[0], "url": LEFT.replace("9991", "9998"), "source_id": "9998",
                "title": "Preserve CreateGraphicsPipelineState across fresh launches",
                "metadata": {"head_sha": "f" * 40, "technical": {}}}
        ci = {**item, "kind": "test", "url": LEFT.replace("/pull/9991", "/actions/runs/9988"), "source_id": "9988"}
        self.catalog.record_sync({"items": [ci, item]}, update_health=False)
        fixture = b"int CreateGraphicsPipelineState(Cache* cache) { return replay_pipeline_key(cache); }\n"
        with patch.object(code_search, "references", return_value=[reference]):
            code_search.refresh(self.catalog, fetch=lambda _: fixture)
            refresh(self.catalog, now=NOW)
            card, = [card for card in radar_view(self.catalog, NOW)["candidates"]
                     if card["kind"] == "source_code"]
        self.assertEqual(card["target_url"], item["url"])
        self.assertEqual(card["evidence_status"], "source_found")
        self.assertIsNone(card["task_id"])
        args = {"request_id": "source-prepare-1", "candidate": card["id"], "generation": card["generation"],
                "note": "Both paths persist a D3D12 pipeline across launches.",
                "expected": "Read the same pipeline key in a fresh process.",
                "control": "Start with an empty cache and expect a miss.", "share_public": True}
        with self.assertRaises(PermissionDenied):
            apply(self.catalog, self.exchange, self.second, "prepare", args, now=NOW)
        with self.assertRaises(ValueError):
            apply(self.catalog, self.exchange, self.reviewer, "prepare", {**args, "share_public": False}, now=NOW)
        with self.assertRaises(ValueError):
            apply(self.catalog, self.exchange, self.reviewer, "prepare", {**args, "note": "C:\\Users\\Example"}, now=NOW)
        created = apply(self.catalog, self.exchange, self.reviewer, "prepare", args, now=NOW)
        repeated = dict(reversed(list(args.items())))
        self.assertEqual(apply(self.catalog, self.exchange, self.reviewer, "prepare", repeated, now=NOW), created)
        with self.assertRaises(Conflict):
            apply(self.catalog, self.exchange, self.reviewer, "prepare",
                  {**args, "request_id": "source-prepare-2"}, now=NOW)
        task = build_lab(self.catalog, task=created["task"], now=NOW)["tasks"][0]
        self.assertEqual((task["workflow_state"], task["adoption"]), ("draft", "pending"))
        self.assertEqual(task["source_review"]["license_url"], donor + "/LICENSE")
        self.assertIn(args["control"], task["prompt"])
        self.assertNotIn("radar_findings", preflight(self.catalog, url=item["url"]))
        self.assertFalse(filter_impact(people(self.catalog, now=NOW)[1], target=item["url"])["stories"])
        queued = self.act(self.reviewer, "queue", task=created["task"], note=args["note"])
        self.assertEqual(queued["state"], "queued")
        self.assertEqual(self.act(self.second, "claim", task=created["task"])["state"], "claimed")
        with patch.object(code_search, "references", return_value=[{**reference, "revision": "a" * 40}]):
            code_search.refresh(self.catalog, fetch=lambda _: fixture)
        with self.assertRaisesRegex(Conflict, "no longer indexed"):
            self.act(self.second, "submit", task=created["task"], report={})

        self.catalog.record_sync({"items": [{**item, "updated_at": timestamp(NOW + 1),
                                             "metadata": {"head_sha": "a" * 40}}]}, update_health=False)
        with self.assertRaises(Conflict):
            apply(self.catalog, self.exchange, self.reviewer, "prepare",
                  {**args, "request_id": "source-prepare-3"}, now=NOW + 1)
        with self.assertRaisesRegex(Conflict, "receiving revision changed"):
            self.act(self.second, "submit", task=created["task"], now=NOW + 1, report={})

    def test_unpinned_discovery_card_expires_even_with_fresh_receiver(self):
        source = {"html_url": "https://github.com/gfx-rs/wgpu/pull/123", "title": "Memory budget",
                  "state": "open", "updated_at": timestamp(NOW)}
        with patch("portbridge.radar_scan.sample", return_value=0), patch(
                "portbridge.discovery_scan._Sync._request", return_value=({"items": [source]}, {})):
            refresh(self.catalog, online_discovery=True, now=NOW)
        card = next(c for c in radar_view(self.catalog, NOW)["candidates"] if c["kind"] == "historical_source")
        self.assertEqual(card["age_state"], "fresh")
        target, peer = card["sources"]
        self.assertTrue(peer["checked_at"])
        card["sources"] = [target, {**peer, "checked_at": timestamp(NOW - 86401)}]
        self.assertFalse(recent(card, NOW))
        card["sources"] = [target, {**peer, "revision": "f" * 40, "checked_at": None}]
        self.assertTrue(recent(card, NOW))

    def test_claim_release_expiry_concurrency_and_stale_pins(self):
        self.act(self.reviewer,"queue",note="Visible source-backed check")
        def claim(actor,request):
            try:
                return apply(self.catalog,self.exchange,actor,"claim",
                             {"request_id":request,"task":self.task,"ttl_seconds":60},now=NOW)
            except Conflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as group:
            f=group.submit(claim,self.first,"claim-unique-1")
            g=group.submit(claim,self.second,"claim-unique-2")
            finished=[f.result(),g.result()]
        self.assertEqual(sum(bool(x) for x in finished),1)
        holder=self.first if finished[0] else self.second
        self.act(holder,"release")
        self.act(holder,"claim",ttl_seconds=60)
        self.assertEqual(radar_view(self.catalog,NOW+61)["candidates"][0]["state"],"queued")
        self.act(self.second,"claim",now=NOW+61)
        self.seed("c"*40,now=NOW+62)
        self.assertEqual(build_lab(self.catalog,task=self.task,now=NOW+62)["tasks"][0]["workflow_state"],"draft")
        with self.assertRaises((Conflict,PermissionDenied)):
            self.act(self.second,"submit",report=self.payload(),now=NOW+63)

    def test_independent_negative_corrected_report_and_retraction(self):
        self.act(self.reviewer,"queue",note="Read both revisions")
        self.act(self.first,"claim")
        incomplete=self.act(self.first,"submit",report={"outcome":"SKIP"})
        self.assertEqual(incomplete["report_status"],"incomplete")
        with self.assertRaises(Conflict):
            self.private_review(incomplete)
        corrected=self.act(self.first,"correct",report_id=incomplete["report_id"],report=self.payload("FAIL"),
                           request="same-correction")
        replay=self.act(self.first,"correct",report_id=incomplete["report_id"],report=self.payload("FAIL"),
                        request="same-correction")
        self.assertEqual(corrected,replay)
        self.assertNotIn("radar_findings",preflight(self.catalog,url=LEFT))
        self.assertEqual(filter_impact(people(self.catalog,now=NOW)[1],target=LEFT)["stories"],[])
        with self.assertRaises(PermissionDenied):
            self.act(self.first,"review",report_id=corrected["report_id"],decision="reviewed",
                     note="I reviewed myself",checked_artifact=True)
        result=self.private_review(corrected,hypothesis_rejected=True)
        self.assertEqual(result["state"],"rejected")
        self.assertEqual(preflight(self.catalog,url=LEFT)["radar_findings"][0]["outcome"],"FAIL")
        credited=filter_impact(people(self.catalog,now=NOW)[1],target=LEFT)["stories"][0]
        self.assertEqual([row["kind"] for row in credited["credits"]],["negative_result","review"])
        self.act(self.first,"withdraw_report",report_id=corrected["report_id"])
        self.assertNotIn("radar_findings",preflight(self.catalog,url=LEFT))
        self.assertEqual(filter_impact(people(self.catalog,now=NOW)[1],target=LEFT)["stories"],[])

    def test_authors_can_retract_reports_without_reopening_a_withdrawn_task(self):
        self.act(self.reviewer, "queue", note="Compare pinned sources")
        self.act(self.first, "claim")
        first = self.act(self.first, "submit", report=self.payload())
        self.private_review(first)
        self.act(self.reviewer, "recheck", note="Check the same result independently")
        self.act(self.second, "claim")
        second = self.act(self.second, "submit", report=self.payload())
        self.act(self.reviewer, "withdraw_task", note="The receiving project ended this check")

        for author, report in ((self.first, first), (self.second, second)):
            report_id = report["report_id"]
            result = self.act(author, "withdraw_report", report_id=report_id)
            self.assertEqual(result["state"], "withdrawn")
            view = dashboard(self.catalog, self.exchange, author, task_id=self.task, now=NOW)
            self.assertEqual(next(r["state"] for r in view["reports"] if r["id"] == report_id), "withdrawn")
            self.assertEqual(build_lab(self.catalog, task=self.task, now=NOW)["tasks"], [])
            self.assertEqual(radar_view(self.catalog, NOW)["candidates"], [])
            with self.assertRaises(Conflict):
                self.act(self.second, "claim")

    def test_reproduction_conflicting_outcomes_do_not_close_the_check(self):
        self.act(self.reviewer,"queue",note="Pinned source test")
        self.act(self.first,"claim")
        initial=self.act(self.first,"submit",report=self.payload("PASS"))
        self.private_review(initial)
        self.act(self.reviewer,"recheck",note="Independent volunteer run")
        with self.assertRaises(Conflict):
            self.act(self.first,"claim")
        self.act(self.second,"claim")
        later=self.act(self.second,"submit",report=self.payload("FAIL"))
        with self.assertRaises(Conflict):
            self.act(self.reviewer,"review",report_id=later["report_id"],decision="reproduced",
                     note="Mismatch",checked_artifact=True)
        accepted=self.private_review(later)
        self.assertEqual(accepted["state"],"investigated")
        self.assertTrue(accepted["conflicting_results"])
        findings = preflight(self.catalog, url=LEFT)["radar_findings"]
        self.assertEqual({row["outcome"] for row in findings}, {"PASS", "FAIL"})
        self.assertTrue(all(row["contested"] for row in findings))
        with self.assertRaises(Conflict):
            self.act(self.reviewer,"deliver",evidence_url=LEFT,checked_artifact=True,note="not yet")

    def test_rejected_report_never_surfaces_as_technical_evidence(self):
        self.act(self.reviewer, "queue", note="Pinned source test")
        self.act(self.first, "claim")
        report = self.act(self.first, "submit", report=self.payload())
        result = self.act(self.reviewer, "review", report_id=report["report_id"],
                          decision="rejected", note="The claimed artifact cannot be verified")
        self.assertEqual(result["state"], "rejected")
        self.assertNotIn("radar_findings", preflight(self.catalog, url=LEFT))

    def test_online_discovery_retries_unchanged_input_after_outage(self):
        changed = {**self.rows[0], "metadata": {**self.rows[0]["metadata"], "head_sha": "c" * 40}}
        self.catalog.record_sync({"items": [changed]}, update_health=False)
        self.assertEqual(refresh(self.catalog, now=NOW)["seen"], 1)
        self.assertEqual(refresh(self.catalog, now=NOW)["seen"], 0)
        with patch("portbridge.radar_scan.sample", return_value=0), patch("portbridge.discovery_scan.fetch") as fetch:
            fetch.side_effect = Unavailable("GitHub rate limit", http_status=429)
            initial = refresh(self.catalog, online_discovery=True, now=NOW)
            self.assertEqual(initial["discovery"]["status"], "rate_limit")
            self.assertEqual(initial["discovery_deferred"], 2)
            self.assertEqual(build_lab(self.catalog, task=self.task)["tasks"][0]["workflow_state"], "draft")
            cached = refresh(self.catalog, online_discovery=True, now=NOW + 1)
            self.assertEqual(cached["discovery"]["lookups"], 0)
            self.assertEqual(cached["discovery_deferred"], 2)
            with self.catalog.connect() as db:
                db.execute("UPDATE discovery_query SET retry_at=0")
            fetch.side_effect = None
            fetch.return_value = ("available", [])
            recovered = refresh(self.catalog, online_discovery=True, now=NOW + 2)
            self.assertEqual(recovered["discovery"]["lookups"], 1)
            self.assertEqual(recovered["discovery_deferred"], 0)
            self.assertEqual(refresh(self.catalog, online_discovery=True, now=NOW + 3)["seen"], 0)

    def test_external_receipt_requires_the_observed_message_or_decision(self):
        self.act(self.reviewer, "queue", note="Pinned source test")
        self.act(self.first, "claim")
        self.private_review(self.act(self.first, "submit", report=self.payload()))
        with self.assertRaises(ValueError):
            self.act(self.reviewer, "deliver", evidence_url=LEFT, checked_artifact=True, note="Only target URL")
        recorded = self.act(self.reviewer, "deliver", evidence_url=LEFT + "#issuecomment-1234",
                            checked_artifact=True, note="Delivery receipt fixture")
        self.assertEqual(recorded["state"], "delivered")
        with self.assertRaises(ValueError):
            self.act(self.reviewer, "adopt", evidence_url=RIGHT + "#issuecomment-5678",
                     checked_artifact=True, note="Wrong repository")
        adopted = self.act(self.reviewer, "adopt", evidence_url=LEFT + "#issuecomment-5678",
                           checked_artifact=True, note="Receiving decision fixture")
        self.assertEqual(adopted["state"], "adopted")
        impact = filter_impact(people(self.catalog, now=NOW)[1], target=LEFT)
        outcome = next(row for row in impact["stories"] if row["type"] == "receiving_outcome")
        self.assertEqual(outcome["state"], "accepted")
        self.assertEqual([source["url"] for source in outcome["sources"]],
                         [LEFT + "#issuecomment-1234", LEFT + "#issuecomment-5678"])

    def test_console_tags_keep_cross_platform_candidates_in_review(self):
        ps5 = {**self.rows[0], "project":"anyps5", "url":"https://github.com/boykopovar/AnyPS5/pull/10000"}
        card = classify(ps5,self.rows[1],"reference",{p["slug"]:p for p in self.catalog.projects()})
        self.assertEqual(card["consoles"],["ps5","xbox-series"])
        self.assertTrue(card["cross_platform"])
        self.assertEqual(card["confidence"],"review")
        self.assertNotIn("verified",card["evidence_status"])


    def test_patch_identity_and_opt_in_digest_scope(self):
        first,second = self.rows
        digest="e"*40
        one={**first,"metadata":{**first["metadata"],"patch_id":digest,"patch_revision":"a"*40}}
        two={**second,"metadata":{**second["metadata"],"patch_id":digest,"patch_revision":"b"*40}}
        self.assertEqual(classify(one,two,"patch",{})["kind"],"same_patch")
        self.assertNotEqual(classify(one,second,"reference",{})["kind"],"same_patch")
        self.act(self.reviewer,"queue",note="Check two pinned sources")
        self.assertEqual(dashboard(self.catalog,self.exchange,self.first,now=NOW)["digest"],[])
        self.act(self.first,"profile",enabled=True,equipment=["cpu"],os="Windows",specialty="gpu")
        digest=dashboard(self.catalog,self.exchange,self.first,now=NOW)["digest"]
        self.assertEqual([card["id"] for card in digest],[self.task])
        self.act(self.first,"profile",enabled=False)
        self.assertEqual(dashboard(self.catalog,self.exchange,self.first,now=NOW)["digest"],[])
