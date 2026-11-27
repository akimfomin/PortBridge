"""Read the actual GitHub Pages consumer paths and compare a partner poll with its repeat."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys

def call_public_mcp(tool, arguments, product):
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "PortBridge-release-check", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": tool, "arguments": arguments}},
    ]
    wire = "".join(json.dumps(row) + "\n" for row in messages)
    run = subprocess.run([sys.executable, "-B", "-m", "portbridge.mcp"], input=wire,
                         capture_output=True, text=True, check=True, timeout=60,
                         cwd=product)
    init, page = (json.loads(line) for line in run.stdout.splitlines())
    if (init.get("id") != 1 or init.get("result", {}).get("protocolVersion") != "2025-11-25"
            or page.get("id") != 2 or page.get("result", {}).get("isError")):
        raise ValueError(f"Public MCP call failed for {tool}")
    return page["result"]["structuredContent"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-sha256", help="optional expected data/site.json digest from the deployment")
    parser.add_argument("--continued-pilot", action="store_true", help="require both independent reports in Impact and the partner feed")
    parser.add_argument("--product", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Checkout of the product revision served by Pages")
    args = parser.parse_args()
    product = args.product.resolve()
    sys.path.insert(0, str(product))
    from portbridge.integrations import digest, select
    from portbridge.matching import canonical_url
    from portbridge.pages_health import public_snapshot, verify_linked_snapshots
    from portbridge.preflight import public_preflight

    def read(name):
        with public_snapshot(name) as res:
            return json.load(res)

    with public_snapshot("site") as res:
        raw = res.read()
    checksum = sha256(raw).hexdigest()
    if args.site_sha256 and args.site_sha256 != checksum:
        raise SystemExit("Public site.json differs from the requested build")
    failed = verify_linked_snapshots(checksum)
    if failed:
        raise SystemExit("Inconsistent public snapshots: " + ", ".join(failed))
    site = json.loads(raw)
    feed = read(site["snapshots"]["partner"].removesuffix(".json"))
    canonical_feed = read("partner")
    if feed != canonical_feed:
        raise SystemExit("Stable partner feed differs from the published generation")
    page = call_public_mcp("portbridge_partner", {"kind": "task", "limit": 1}, product)
    # MCP adds client guidance to the same public page.
    if {k: v for k, v in page.items() if k != "guidance"} != select(feed, kind="task", limit=1):
        raise SystemExit("Public MCP task page differs from the published partner feed")
    first, cursor = digest(feed, {}, kind="task")
    if first["state"] != "available":
        raise SystemExit("Current partner feed cannot initialize a subscription: " + first["state"])
    repeat, _ = digest(feed, cursor, kind="task")
    if repeat["state"] != "available" or repeat["added_or_changed"] or repeat["no_longer_listed"]:
        raise SystemExit("A repeated subscription poll changed the result")
    generation = site["browse_index"]["generation"]
    if not re.fullmatch("[0-9a-f]{24}", generation):
        raise SystemExit("Invalid public browse generation")
    index = read(f"browse-{generation}-index")
    counts = {}
    for kind in ("matches", "sources"):
        total = index["kinds"][kind]["total"]
        if total:
            first_page = read(f"browse-{generation}-{kind}-page-0")
            if len(first_page["items"]) != min(total, index["page_size"]):
                raise SystemExit(f"Invalid first {kind} page")
        counts[kind] = total
    url = "https://github.com/xcl-dev/xcl/pull/2322"
    prior = public_preflight(url=url, limit=5)
    discovery = prior.get("discovery") or {}
    if (prior.get("origin_url") != canonical_url(url) or prior.get("catalog_status") == "unavailable"
            or discovery.get("index_source") != "published_snapshot"):
        raise SystemExit("Reference PR could not be read from the published Discovery snapshot")
    if not discovery.get("matches"):
        raise SystemExit("The reference PR returned no previous work")
    via_mcp = call_public_mcp("portbridge_preflight", {"url": url, "limit": 5}, product)
    expected = [row["source"] for row in discovery["matches"]]
    observed = [row["source"] for row in via_mcp.get("discovery", {}).get("matches", [])]
    if via_mcp.get("origin_url") != prior["origin_url"] or observed != expected:
        raise SystemExit("The MCP preflight and the published URL search returned different sources")
    health = read(site["snapshots"]["health"].removesuffix(".json"))
    pilot = None
    if args.continued_pilot:
        pr = "https://github.com/ubiquitarianism/leonida/pull/2392"
        offer = pr + "#issuecomment-7202363138"
        reports = {"qhukz13": pr + "#issuecomment-7202911853", "lixonik": pr + "#pullrequestreview-6080300502"}
        proofs = {offer, *reports.values()}
        impact = read(site["snapshots"]["impact"].removesuffix(".json"))
        story = next((s for s in impact["stories"] if s["id"] == "impact:continued-m53-cache-control"), {})
        credits = {c["login"]: c["source"] for c in story.get("credits", []) if c["kind"] == "independent_test"}
        if (story.get("state") != "reviewed" or credits != reports
                or not any(r["kind"] == "result" and proofs <= set(r.get("proofs", [])) for r in feed["items"])):
            raise SystemExit("The published pilot case lacks the expected team credits or partner proofs")
        pilot = {"task": pr, "state": "reviewed", "offer": offer, "team_reports": reports}
    print(json.dumps({"site_sha256": checksum, "generated_at": site["generated_at"],
        "health_status": health["status"], "observations": health["observation_count"],
        "source_last_success": health["last_success"], "published_sections_verified": sorted(site["snapshots"]),
        "browse_totals": counts, "partner_counts": feed["counts"], "tasks_in_first_poll": len(first["added_or_changed"]),
        "changed_on_second_poll": 0, "mcp_partner_first_page_items": len(page["items"]),
        "reference_pr": url, "origin_in_source_index": prior.get("indexed"),
        "discovery_matches": len(discovery["matches"]), "mcp_and_api_sources": observed,
        "continued_pilot": pilot}, indent=2))


if __name__ == "__main__":
    main()
