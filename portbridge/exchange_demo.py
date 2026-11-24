"""Run an isolated, two-agent PortBridge evidence exchange demonstration."""

from contextlib import contextmanager
from hashlib import sha256
from http.client import HTTPConnection
from itertools import permutations
import json
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from threading import Thread
from time import perf_counter_ns
from urllib.parse import urlencode

from .__main__ import make_server
from .catalog import Catalog
from .exchange import Exchange
from .exchange_api import PREFIX
from .preflight import preflight


SEED = Path(__file__).resolve().parent / "data" / "seed.json"
PROBLEM = "PB-0001"
START = "https://github.com/ubiquitarianism/leonida/pull/207"
REFERENCE = "https://github.com/Marvisak/VIctory/pull/346#issuecomment-7120734503"
NEW_SOURCE = "https://github.com/ivall/xcl/issues/772"
CASES = ((0, 0), (1, 0), (0, 1))
EXPECTED_CORNERS = {(0, 0), (1, 0), (0, 1), (1, 1)}
EXPECTED_DIAGONAL = {(0, 1), (1, 0)}
SIMULATION_FIXTURE = {
    "algorithm": "rectangle-cpu-v1",
    "vertices": CASES,
    "corners": sorted(EXPECTED_CORNERS),
    "shared_diagonal": sorted(EXPECTED_DIAGONAL),
    "double_area_per_triangle": 1,
}
SIMULATION_REVISION = sha256(json.dumps(SIMULATION_FIXTURE, sort_keys=True).encode("utf-8")).hexdigest()


def manual_lookup(catalog):
    """Follow the known source from the raw catalog to the first relevant passing check."""
    for card in catalog.problems():
        from_origin = any(ref["url"] == START for solution in card["solutions"] for ref in solution["source_refs"])
        if not from_origin:
            continue
        for solution in card["solutions"]:
            if solution["project"] == "continued":
                continue
            for evidence in solution["evidence"]:
                if evidence.get("outcome") == "passed":
                    return {key: evidence[key] for key in ("url", "revision", "platforms")} | {
                        "project": solution["project"],
                    }
    return None


def timed_lookup(lookup, repeats=9):
    results = []
    for _ in range(repeats):
        started = perf_counter_ns()
        result = lookup()
        results.append(perf_counter_ns() - started)
    return result, round(median(results) / 1000, 1)


def compare_lookups(catalog):
    manual, raw_elapsed = timed_lookup(lambda: manual_lookup(catalog))
    prepared, preflight_elapsed = timed_lookup(lambda: preflight(catalog, url=START)["first_check"])
    if not manual or not prepared or any(prepared[key] != value for key, value in manual.items()) or prepared["url"] != REFERENCE:
        raise RuntimeError("The two demo lookups did not identify the same public reference")
    return prepared, {"measure": "local elapsed time per lookup, microseconds, median of 9",
                      "raw_catalog": raw_elapsed, "preflight": preflight_elapsed,
                      "same_source_and_revision": True}


def expand_rectangle(vertices):
    """Build two triangles from three corners of the demo's axis-aligned rectangle."""
    for corner, a, b in permutations(vertices):
        if corner[0] == a[0] and corner[1] == b[1]:
            fourth = (b[0], a[1])
            return (corner, a, b), (a, b, fourth)
    raise ValueError("Expected three distinct axis-aligned corners")


def double_area(triangle):
    a, b, c = triangle
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def simulate_geometry():
    passed = 0
    for vertices in permutations(CASES):
        triangles = expand_rectangle(vertices)
        covers_corners = (set(triangles[0]) | set(triangles[1])) == EXPECTED_CORNERS
        shares_diagonal = (set(triangles[0]) & set(triangles[1])) == EXPECTED_DIAGONAL
        equal_areas = all(double_area(triangle) == SIMULATION_FIXTURE["double_area_per_triangle"]
                          for triangle in triangles)
        if covers_corners and shares_diagonal and equal_areas:
            passed += 1
    return passed, 6


@contextmanager
def demo_server(catalog, exchange):
    with make_server(catalog, 0, exchange=exchange) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
        thread.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            thread.join()


def call_exchange(port, agent, route, *, body=None, expected=200):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Authorization": f"Bearer {agent['token']}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        connection.request("GET" if body is None else "POST", f"{PREFIX}/{route}",
                           body=None if body is None else json.dumps(body).encode("utf-8"), headers=headers)
        with connection.getresponse() as response:
            if response.status != expected:
                raise RuntimeError(f"Unexpected HTTP status {response.status} for {route}")
            return json.load(response)
    finally:
        connection.close()


def demonstrate_new_topic(port, author, reader, reviewer):
    proposal = {"source_url": NEW_SOURCE, "title": "Wave64 lane behavior"}
    call_exchange(port, author, "propose-topic", body=proposal)
    topic = call_exchange(port, reviewer, "review-topic", body={
        "source_url": NEW_SOURCE, "decision": "accepted",
    })["topic"]
    call_exchange(port, author, "register", body={"problem_id": topic["id"]})
    submitted = call_exchange(port, author, "submit", body={
        "problem_id": topic["id"], "source_url": NEW_SOURCE, "revision": SIMULATION_REVISION,
        "platform": "SIMULATION local API, no hardware check",
        "evidence_kind": "simulation", "outcome": "unknown",
        "summary": "Workflow simulation. A hardware result for the source issue is still needed.",
    })["result"]
    route = "preflight?" + urlencode({"url": NEW_SOURCE})
    before = call_exchange(port, reader, route)
    call_exchange(port, reviewer, "review", body={"result_id": submitted["id"], "decision": "accepted"})
    after = call_exchange(port, reader, route)
    return {"topic": after["exchange_topic"], "reports_before_review": len(before["reviewed_reports"]),
            "reports_after_review": after["reviewed_reports"]}


def run_demo(*, temp_root=None):
    with TemporaryDirectory(prefix=".portbridge-exchange-demo-", dir=temp_root or Path.cwd()) as directory:
        path = Path(directory)
        catalog = Catalog(path / "catalog.sqlite3", SEED)
        exchange = Exchange(path / "exchange.sqlite3", problem_exists=lambda ident: ident == PROBLEM)
        continued = exchange.create_principal("TEST Continued Vulkan", ["read", "contribute"])
        victory = exchange.create_principal("TEST VIctory D3D12", ["read", "contribute"])
        reviewer = exchange.create_principal("TEST Human Reviewer", ["review"])

        known_check, lookup = compare_lookups(catalog)
        with demo_server(catalog, exchange) as port:
            claim = call_exchange(port, continued, "register", body={"problem_id": PROBLEM, "ttl_seconds": 1200})["work"]
            visible = call_exchange(port, victory, f"work?problem_id={PROBLEM}")["work"]
            passed, total = simulate_geometry()
            pending = call_exchange(port, continued, "submit", body={
                "problem_id": PROBLEM,
                "source_url": known_check["url"],
                "revision": SIMULATION_REVISION,
                "platform": "SIMULATION CPU geometry only",
                "evidence_kind": "simulation",
                "outcome": "passed" if passed == total else "failed",
                "summary": (f"SIMULATION: {passed}/{total} synthetic rectangle permutations match corners, diagonal and area. "
                            "CPU fixture only. Linked public test supplies prior context."),
            })["result"]
            while_pending = call_exchange(port, victory, "poll?after=0")
            evidence_before = call_exchange(port, victory, f"evidence?problem_id={PROBLEM}")["results"]
            preflight_before = call_exchange(port, victory, f"preflight?q={PROBLEM}")["reviewed_reports"]
            decision = {"result_id": pending["id"], "decision": "accepted",
                        "reason": "Accepted for this simulation only. No real project test performed."}
            denied = call_exchange(port, victory, "review", body=decision, expected=403)
            review_queue = call_exchange(port, reviewer, "pending")["results"]
            reviewed = call_exchange(port, reviewer, "review", body=decision)["result"]
            received = call_exchange(port, victory, f"poll?after={while_pending['next_cursor']}")
            repeat = call_exchange(port, victory, f"poll?after={received['next_cursor']}")
            evidence = call_exchange(port, victory, f"evidence?problem_id={PROBLEM}")["results"]
            preflight_after = call_exchange(port, victory, f"preflight?q={PROBLEM}")["reviewed_reports"]
            new_topic = demonstrate_new_topic(port, continued, victory, reviewer)
        return {
            "mode": "simulation",
            "transport": "loopback HTTP API",
            "problem_id": PROBLEM,
            "actors": [actor["name"] for actor in (continued, victory, reviewer)],
            "known_public_check": known_check,
            "lookup_comparison": lookup,
            "claim_id": claim["id"],
            "claim_visible_to_other_agent": any(work["id"] == claim["id"] for work in visible),
            "pending_result_visible_to_reviewer": any(row["id"] == pending["id"] for row in review_queue),
            "events_before_review": len(while_pending["events"]),
            "evidence_before_review": len(evidence_before),
            "preflight_reports_before_review": len(preflight_before),
            "unauthorized_review_denied": bool(denied.get("error")),
            "unauthorized_review_http_status": 403,
            "review_status": reviewed["status"],
            "received": received,
            "accepted_evidence_ids": [row["id"] for row in evidence],
            "preflight_reports_after_review": [row["id"] for row in preflight_after],
            "events_after_advancing_cursor": len(repeat["events"]),
            "new_topic": new_topic,
        }


def main():
    print(json.dumps(run_demo(), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
