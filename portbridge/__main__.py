"""Command line and localhost API for PortBridge."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import time
from threading import Event, Thread
from time import monotonic
from urllib.parse import parse_qs, unquote, urlsplit

from .activity import build_activity
from .case_pages import CASE_FILE, case_languages, case_page, case_path
from .catalog import Catalog, OBSERVATION_KIND, PROBLEM_ID, PROBLEM_STATUS
from .coordination import knowledge_graph, recommendations
from .discovery_scan import cached_index
from .discovery_search import discover, historical_candidates
from .ecosystem import build_ecosystem, refresh_ecosystem
from .exchange_api import ExchangeHandlerMixin
from .feed import build_feed
from .identity import SCHEMA_VERSION
from .lab import build_lab
from .radar_store import radar_view, reviewed_snapshot, filter_findings


PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
DEFAULT_DB = ROOT / ".portbridge" / "portbridge.sqlite3"
DEFAULT_SEED = PACKAGE / "data" / "seed.json"
STATIC = {
    "/": (PACKAGE / "static" / "index.html", "text/html; charset=utf-8"),
    "/static/styles.css": (PACKAGE / "static" / "styles.css", "text/css; charset=utf-8"),
    "/static/app.js": (PACKAGE / "static" / "app.js", "text/javascript; charset=utf-8"),
    "/static/discovery.js": (PACKAGE / "static" / "discovery.js", "text/javascript; charset=utf-8"),
    "/static/partner.js": (PACKAGE / "static" / "partner.js", "text/javascript; charset=utf-8"),
    "/start.html": (PACKAGE / "static" / "start.html", "text/html; charset=utf-8"),
    "/start.ru.html": (PACKAGE / "static" / "start.ru.html", "text/html; charset=utf-8"),
    "/partner.html": (PACKAGE / "static" / "partner.html", "text/html; charset=utf-8"),
    "/letter.html": (PACKAGE / "static" / "letter.html", "text/html; charset=utf-8"),
    "/letter.ru.html": (PACKAGE / "static" / "letter.ru.html", "text/html; charset=utf-8"),
    "/api/docs": (ROOT / "API.md", "text/plain; charset=utf-8"),
}
OFFICE_STATIC = {
    "/office": (PACKAGE / "static" / "office.html", "text/html; charset=utf-8"),
    "/static/office.css": (PACKAGE / "static" / "office.css", "text/css; charset=utf-8"),
    "/static/office.js": (PACKAGE / "static" / "office.js", "text/javascript; charset=utf-8"),
}
COLLECTIONS = ("projects", "ecosystem", "problems", "observations", "matches", "related", "preflight", "coordination", "activity", "lab",
               "graph", "source-history", "recommendations", "outreach", "health", "discovery", "radar", "people", "impact", "partner")


def sync_catalog(catalog, *, refresh=False, pages=1, sources=()):
    from .github import PAIR_CHECK_LIMIT, WORK_URL, collect, refresh_references, revision_references
    from .matching import canonical_url, current_repository

    projects = catalog.projects()
    if sources:
        repos = {current_repository(project["repo"]).casefold() for project in projects}
        if len(sources) > PAIR_CHECK_LIMIT or any(not WORK_URL.fullmatch(source) for source in sources):
            raise ValueError("--source accepts up to eight public GitHub issue or PR URLs")
        if any(current_repository("/".join(urlsplit(source).path.split("/")[1:3])).casefold() not in repos
               for source in sources):
            raise ValueError("--source must belong to a configured public repository")
        requested = list(dict.fromkeys(map(canonical_url, sources)))
        checked = refresh_references(projects, catalog.path, requested, refresh=refresh)
        catalog.record_sync(checked, update_health=False)
        candidates = revision_references(catalog.observations(limit=None), sources=requested)
        related = {"items": [], "warnings": []}
        if candidates:
            related = refresh_references(projects, catalog.path, candidates, refresh=refresh)
            catalog.record_sync(related, update_health=False)
        return {**catalog.health(), "targeted_refresh": {
            "requested": sources[0] if len(sources) == 1 else requested,
            "observations_saved": len(checked["items"]), "related_saved": len(related["items"]),
            "warnings": checked["warnings"] + related["warnings"],
        }}
    result = collect(projects, catalog.path, refresh=refresh, pages=pages)
    references = [ref["url"] for card in catalog.problems() for solution in card["solutions"]
                  for ref in solution["source_refs"] + solution["evidence"]]
    watched = refresh_references(result["projects"], catalog.path, references, refresh=refresh, skip_unavailable=True)
    result["items"].extend(watched["items"])
    result["warnings"].extend(watched["warnings"])
    result["references"] = watched["references"]
    catalog.record_sync(result, update_health=False)
    candidates = revision_references(catalog.observations(limit=None))
    checked = {"items": [], "warnings": []}
    if candidates:
        checked = refresh_references(result["projects"], catalog.path, candidates, refresh=refresh, skip_unavailable=True)
        result["references"].extend(checked["references"])
    catalog.record_sync({**result, "items": checked["items"], "warnings": result["warnings"] + checked["warnings"]})
    if references:
        from .source_context import refresh_context
        refresh_context(catalog, result["projects"], references)
    refresh_ecosystem(catalog)
    return catalog.health()


def query_rules(params):
    query = params.get("q", [""])[0].strip()
    project = params.get("project", [""])[0]
    status = params.get("status", [""])[0]
    kind = params.get("kind", [""])[0]
    partial = params.get("partial", ["0"])[0]
    limit = params.get("limit", ["60"])[0]
    if len(query) > 300 or len(project) > 40:
        raise ValueError("q is limited to 300 characters and project to 40")
    if status and status not in PROBLEM_STATUS:
        raise ValueError("unknown problem status")
    if kind and kind not in OBSERVATION_KIND:
        raise ValueError("unknown observation kind")
    if partial not in {"0", "1"}:
        raise ValueError("partial must be 0 or 1")
    if not limit.isascii() or not limit.isdecimal() or len(limit) > 3 or not 1 <= int(limit) <= 200:
        raise ValueError("limit must be between 1 and 200")
    return query, project, status, kind, partial == "1", int(limit)


REJECTED_BODY_LIMIT = 4096
REJECTED_BODY_TIMEOUT = 0.25


class Handler(ExchangeHandlerMixin, BaseHTTPRequestHandler):
    server_version = "PortBridge/0.1"

    def log_message(self, format, *args):
        # Search queries can contain text copied by users. Do not write them to logs.
        pass

    def respond(self, status, content_type, contents, *, head=False):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(contents)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        route = urlsplit(self.path).path
        frame = "*" if route == "/partner.html" else "'none'"
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; "
                         f"connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors {frame}")
        if route == "/api/v1/partner":
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        if status == 405:
            self.send_header("Allow", "GET, HEAD")
        self.end_headers()
        if not head:
            self.wfile.write(contents)

    def json_response(self, status, payload, *, head=False):
        contents = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.respond(status, "application/json; charset=utf-8", contents, head=head)

    def do_GET(self):
        self.read_route()

    def do_HEAD(self):
        self.read_route(head=True)

    def do_POST(self):
        if self.handle_exchange(self.path, self.command):
            return
        self.discard_small_request_body()
        self.json_response(405, {"error": "read-only API"})

    def discard_small_request_body(self):
        # Closing with unread request bytes can reset the socket before the client sees the 405.
        length = self.headers.get("Content-Length", "")
        if (self.headers.get("Transfer-Encoding") or self.headers.get("Expect") or not length.isascii()
                or not length.isdecimal() or len(length) > len(str(REJECTED_BODY_LIMIT))):
            return
        remaining = int(length)
        if not 0 < remaining <= REJECTED_BODY_LIMIT:
            return
        timeout = self.connection.gettimeout()
        deadline = monotonic() + REJECTED_BODY_TIMEOUT
        try:
            while remaining:
                available = deadline - monotonic()
                if available <= 0:
                    return
                self.connection.settimeout(available)
                chunk = self.rfile.read1(remaining)
                if not chunk:
                    return
                remaining -= len(chunk)
        except OSError:
            pass
        finally:
            self.connection.settimeout(timeout)

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST

    def read_route(self, *, head=False):
        if self.handle_exchange(self.path, self.command, head=head):
            return
        host = self.headers.get("Host", "").lower()
        if host not in {"127.0.0.1", "localhost", f"127.0.0.1:{self.server.server_port}",
                        f"localhost:{self.server.server_port}"}:
            self.json_response(403, {"error": "localhost only"}, head=head)
            return
        try:
            target = urlsplit(self.path)
            path = unquote(target.path)
            if path in {"/feed.xml", "/feed.ru.xml"}:
                language = "ru" if path == "/feed.ru.xml" else "en"
                self.respond(200, "application/atom+xml; charset=utf-8",
                             build_feed(self.server.catalog, language=language), head=head)
                return
            if path == "/api/docs" and target.query == "lang=en":
                self.respond(200, "text/plain; charset=utf-8", (ROOT / "API.en.md").read_bytes(), head=head)
                return
            if path.startswith("/cases/") and CASE_FILE.fullmatch(path.removeprefix("/cases/")):
                self.read_case(path, head=head)
                return
            asset = STATIC.get(path)
            if self.server.exchange is not None:
                asset = asset or OFFICE_STATIC.get(path)
            if asset:
                file, content_type = asset
                if not file.is_file():
                    self.json_response(404, {"error": "asset missing"}, head=head)
                    return
                self.respond(200, content_type, file.read_bytes(), head=head)
                return
            params = parse_qs(target.query, max_num_fields=25)
            status, result = self.api(path, params)
        except ValueError as exc:
            status, result = 400, {"error": str(exc)}
        self.json_response(status, result, head=head)

    def read_case(self, path, *, head=False):
        ident = path.removeprefix("/cases/").split(".", 1)[0].upper()
        catalog = self.server.catalog
        card = catalog.problem(ident)
        if card:
            language = "ru" if path.endswith(".ru.html") else case_languages(card)[0]
            if f"/{case_path(card, language)}" == path:
                names = {project["slug"]: project["name"] for project in catalog.projects()}
                self.respond(200, "text/html; charset=utf-8", case_page(card, names, language).encode("utf-8"), head=head)
                return
        self.json_response(404, {"error": "case not found"}, head=head)

    def api(self, path, params):
        with self.server.catalog.read_view() as catalog:
            return self.read_api(catalog, path, params)

    def read_api(self, catalog, path, params):
        if path in {"/api/v1", "/api/v1/"}:
            return 200, {"name": "PortBridge", "version": 1, "data_schema_version": SCHEMA_VERSION,
                         "read_only": True, "docs": "/api/docs",
                         "exchange_enabled": self.server.exchange is not None,
                         "routes": {key: f"/api/v1/{key}" for key in COLLECTIONS}}
        name = path.removeprefix("/api/v1/")
        if name == "projects":
            return 200, {"projects": catalog.projects()}
        if path == "/api/v1/ecosystem":
            return 200, build_ecosystem(catalog)
        if name == "health":
            return 200, catalog.health()
        if name == "discovery":
            fields = {"q", "url", "project", "kind", "status", "platform", "before", "after", "limit"}
            if params.keys() - fields or any(len(values) != 1 for values in params.values()):
                raise ValueError("Use each Discovery filter at most once")
            options = {key: value[0] for key, value in params.items()}
            limit = options.pop("limit", "5")
            if not limit.isascii() or not limit.isdecimal() or len(limit) > 2:
                raise ValueError("Discovery limit must be between 1 and 10")
            result = discover(origin_url=options.pop("url", ""), index=cached_index(catalog), limit=int(limit), **options)
            return 200, {**result, "radar_candidates": historical_candidates(result)}
        if name == "activity":
            return 200, build_activity(catalog)
        if name == "partner":
            from .integrations import public_feed, select
            if params.keys() - {"project", "console", "kind", "limit", "after"} or any(len(values) != 1 for values in params.values()):
                raise ValueError("Use each partner filter at most once")
            options = {key: values[0] for key, values in params.items()}
            size = options.pop("limit", "24")
            if not size.isascii() or not size.isdecimal() or len(size) > 3:
                raise ValueError("Invalid partner feed limit")
            after = options.pop("after", "0")
            if not after.isascii() or not after.isdecimal() or len(after) > 9:
                raise ValueError("Invalid partner feed offset")
            return 200, select(public_feed(catalog), limit=int(size), after=int(after), **options)
        if name in {"people", "impact"}:
            from .community import filter_impact, filter_people, people

            fields = ({"q", "profile", "project", "specialty", "console", "period", "target", "limit", "after"}
                      if name == "people" else {"console", "kind", "target"})
            if params.keys() - fields or any(len(v) != 1 for v in params.values()):
                raise ValueError("Use each People or Impact filter at most once")
            options = {key: values[0] for key, values in params.items()}
            for key in fields & {"limit", "after"} & options.keys():
                value = options[key]
                if not value.isascii() or not value.isdecimal() or len(value) > 7:
                    raise ValueError("Invalid People pagination")
                options[key] = int(value)
            profiles, stories = people(catalog)
            return 200, filter_people(profiles, **options) if name == "people" else filter_impact(stories, **options)
        if name == "radar":
            if params.keys() - {"confidence", "state", "limit", "after", "q", "url", "console"} or any(len(v) != 1 for v in params.values()):
                raise ValueError("Use each Radar filter at most once")
            options = {key: values[0] for key, values in params.items()}
            if "q" in options or "url" in options:
                return 200, {"findings": filter_findings(reviewed_snapshot(catalog), url=options.get("url",""),
                                                         query=options.get("q",""))}
            for field in ("limit", "after"):
                if field in options:
                    value = options[field]
                    if not value.isascii() or not value.isdecimal() or len(value)>4:
                        raise ValueError("Invalid Radar pagination")
                    options[field] = int(value)
            return 200, radar_view(catalog, int(time.time()), **options)
        if name == "lab":
            if params.keys() - {"equipment", "status", "task", "os", "kind", "specialty", "difficulty", "age", "console"} or any(len(values) != 1 for values in params.values()):
                raise ValueError("use each Test Lab filter at most once")
            return 200, build_lab(catalog, **{key: values[0] for key, values in params.items()})
        if name == "coordination":
            return 200, {"coordination": catalog.coordination()}
        if name == "graph":
            return 200, knowledge_graph(catalog)
        if name == "source-history":
            _, _, _, _, _, limit = query_rules(params)
            return 200, {"changes": catalog.source_changes(url=params.get("url", [""])[0], limit=limit)}
        if name == "recommendations":
            _, project, _, _, _, limit = query_rules(params)
            return 200, {"recommendations": recommendations(catalog, project=project, limit=limit)}
        if name == "outreach":
            return 200, {"drafts": catalog.outreach()}
        if name.startswith("problems/"):
            ident = name.split("/", 1)[1]
            problem = catalog.problem(ident) if PROBLEM_ID.fullmatch(ident) else None
            return (200, {"problem": problem}) if problem else (404, {"error": "problem not found"})
        if name not in {"problems", "observations", "matches", "related", "preflight"}:
            return 404, {"error": "not found"}
        if name == "preflight":
            from .preflight import preflight

            limit = params.get("limit", ["5"])[0]
            if not limit.isdecimal() or len(limit) > 2:
                raise ValueError("preflight limit must be between 1 and 20")
            return 200, preflight(catalog, q=params.get("q", [""])[0], url=params.get("url", [""])[0],
                                  limit=int(limit))
        q, project, status, kind, partial, limit = query_rules(params)
        if name == "related":
            return 200, catalog.related(params.get("url", [""])[0], limit=limit)
        if name == "observations":
            return 200, {"observations": catalog.observations(q=q, kind=kind, project=project, limit=limit)}
        if name == "matches":
            return 200, {"matches": catalog.matches(q=q, limit=limit)}
        problems = catalog.problems(q=q, project=project, status=status, partial=partial)
        return 200, {"problems": problems[:limit]}


def make_server(catalog, port, *, exchange=None):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.catalog = catalog
    server.exchange = exchange
    return server


def serve(catalog, args):
    from .community_sources import refresh as refresh_people
    from .radar_scan import refresh as refresh_radar

    stop = Event()

    def poll():
        while not stop.is_set():
            try:
                sync_catalog(catalog, pages=args.pages)
            except Exception as exc:
                print(f"GitHub sync failed: {type(exc).__name__}", file=sys.stderr)
            if not stop.is_set():
                try:
                    refresh_radar(catalog, online_discovery=True)
                    refresh_people(catalog)
                except Exception as exc:
                    print(f"Radar refresh failed: {type(exc).__name__}", file=sys.stderr)
            if args.office and not stop.is_set():
                from .discovery import refresh_project_leads
                from .office_engine import refresh_external_sources

                try:
                    refresh_external_sources(exchange)
                    refresh_project_leads(exchange)
                except Exception as exc:
                    print(f"Office source check failed: {type(exc).__name__}", file=sys.stderr)
            if stop.wait(args.interval):
                return

    exchange = None
    if args.exchange_db:
        from .exchange import Exchange

        exchange = Exchange(args.exchange_db, problem_exists=lambda ident: catalog.problem(ident) is not None,
                            find_curated_topic=catalog.curated_topic)
    with make_server(catalog, args.port, exchange=exchange) as server:
        if not args.offline:
            Thread(target=poll, name="portbridge-sync", daemon=True).start()
        if args.coordinate or args.office:
            from .coordinator import COORDINATION_INTERVAL, run_coordination

            def coordinate():
                while not stop.is_set():
                    try:
                        run_coordination(catalog, exchange, office=args.office)
                    except Exception as exc:
                        print(f"Coordination pass failed: {type(exc).__name__}", file=sys.stderr)
                    if stop.wait(COORDINATION_INTERVAL):
                        return

            Thread(target=coordinate, name="portbridge-coordinator", daemon=True).start()
        print(f"PortBridge — http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="local SQLite database")
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED, help="reviewed local catalog JSON")
    commands = parser.add_subparsers(dest="command", required=True)
    refresh = commands.add_parser("sync", help="refresh public GitHub metadata once")
    refresh.add_argument("--force", action="store_true", help="revalidate even fresh cached responses")
    refresh.add_argument("--pages", type=int, choices=range(1, 4), default=1)
    refresh.add_argument("--source", action="append", help="refresh an exact public issue or PR URL (repeatable)")
    backfill = commands.add_parser("backfill", help="index older public issues and pull requests")
    backfill.add_argument("--pages", type=int, choices=range(1, 11), default=3,
                          help="maximum history pages per project in this run")
    update = commands.add_parser("incremental", help="index issues and pull requests updated since the last sweep")
    update.add_argument("--pages", type=int, choices=range(1, 11), default=3)
    update.add_argument("--discovery", action="store_true",
                        help="run a bounded public historical-source search for new observations")
    commands.add_parser("status", help="show cached synchronization status")
    radar = commands.add_parser("radar", help="read or refresh the local research queue")
    radar.add_argument("--refresh", action="store_true")
    radar.add_argument("--discovery", action="store_true", help="allow bounded anonymous historical lookup")
    radar.add_argument("--confidence", choices=("high","review","research"), default="")
    radar.add_argument("--limit", type=int, default=24)
    radar.add_argument("--state", default="")
    radar.add_argument("--console", choices=("xbox-series","ps5"), default="")
    radar.add_argument("--after", type=int, default=0)
    lab_queue = commands.add_parser("lab", help="read public Lab cards")
    people_view = commands.add_parser("people", help="filter evidence-backed public technical profiles")
    for field in ("q", "profile", "project", "specialty", "console", "period", "target"):
        people_view.add_argument("--" + field, default="")
    people_view.add_argument("--limit", type=int, default=24)
    people_view.add_argument("--after", type=int, default=0)
    impact_view = commands.add_parser("impact", help="read credited impact stories and audited counts")
    for field in ("console", "kind", "target"):
        impact_view.add_argument("--" + field, default="")
    people_update = commands.add_parser("refresh-people", help="read bounded public GitHub reviews and technical comments")
    people_update.add_argument("--limit", type=int, default=8)
    for field in ("equipment","status","task","os","kind","specialty","difficulty","age","console"):
        lab_queue.add_argument("--"+field, default="")
    lab_refresh = commands.add_parser("refresh-lab", help="refresh reports for monitored Test Lab checks")
    lab_refresh.add_argument("--authenticated", action="store_true", help="use the configured read token for public reports")
    backup = commands.add_parser("backup", help="write a separate verified SQLite backup of --db")
    backup.add_argument("--out", type=Path, required=True)
    backup.add_argument("--public-checkpoint", action="store_true",
                        help="compact the snapshot and verify its public catalog schema and Lab state")
    principal = commands.add_parser("exchange-key", help="create a scoped local exchange key")
    principal.add_argument("--exchange-db", type=Path, required=True)
    principal.add_argument("--name", required=True)
    principal.add_argument("--scope", action="append", choices=("read", "contribute", "review"), required=True)
    revoke = commands.add_parser("exchange-revoke", help="revoke a local exchange key")
    revoke.add_argument("--exchange-db", type=Path, required=True)
    revoke.add_argument("--name", required=True)
    snapshot = commands.add_parser("export", help="write a static site and public JSON snapshots")
    snapshot.add_argument("--out", type=Path, default=ROOT / "dist")
    snapshot.add_argument("--repository", default="", help="optional own GitHub repo for public submissions")
    run = commands.add_parser("serve", help="start the local dashboard and read-only API")
    run.add_argument("--port", type=int, default=8765)
    run.add_argument("--offline", action="store_true", help="serve without any requests to GitHub")
    run.add_argument("--exchange-db", type=Path, help="enable optional exchange with this separate local database")
    run.add_argument("--coordinate", action="store_true", help="post automated notices in subscribed local topics")
    run.add_argument("--office", action="store_true", help="propose and reconcile private cross-project plans")
    run.add_argument("--interval", type=int, default=900, help="automatic refresh seconds (minimum 60)")
    run.add_argument("--pages", type=int, choices=range(1, 4), default=1)
    args = parser.parse_args(argv)
    if args.command == "serve" and (args.interval < 60 or not 0 <= args.port <= 65535):
        parser.error("use an interval of at least 60 seconds and a valid port")
    if args.command == "serve" and (args.coordinate or args.office) and args.exchange_db is None:
        parser.error("coordination requires --exchange-db")
    if getattr(args, "exchange_db", None) and args.exchange_db.resolve() == args.db.resolve():
        parser.error("the exchange needs a separate SQLite database")
    if args.command in {"exchange-key", "exchange-revoke"}:
        from .exchange import Conflict, Exchange

        try:
            exchange = Exchange(args.exchange_db)
            result = (exchange.create_principal(args.name, args.scope) if args.command == "exchange-key"
                      else exchange.revoke_principal(args.name))
        except (Conflict, LookupError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, ensure_ascii=True))
        return 0
    if args.command == "backup":
        from .backup import backup_database

        try:
            print(backup_database(args.db, args.out, public_checkpoint=args.public_checkpoint))
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        return 0
    catalog = Catalog(args.db, args.seed)
    if args.command in {"people", "impact", "refresh-people"}:
        from .community import filter_impact, filter_people, people
        from .community_sources import refresh as refresh_people

        try:
            if args.command == "refresh-people":
                result = refresh_people(catalog, limit=args.limit)
            else:
                with catalog.read_view() as view:
                    profiles, stories = people(view)
                if args.command == "people":
                    result = filter_people(profiles, **{key: getattr(args, key) for key in
                        ("q", "profile", "project", "specialty", "console", "period", "target", "limit", "after")})
                else:
                    result = filter_impact(stories, console=args.console, kind=args.kind, target=args.target)
        except ValueError as error:
            parser.error(str(error))
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    if args.command == "radar":
        from .radar_scan import refresh
        if args.discovery and not args.refresh:
            parser.error("--discovery requires --refresh")
        try:
            if args.discovery:
                from .code_search import refresh as refresh_code
                code_status = refresh_code(catalog)
            result = (refresh(catalog, online_discovery=args.discovery, limit=args.limit) if args.refresh
                      else radar_view(catalog, int(time.time()), confidence=args.confidence, limit=args.limit,
                                     state=args.state, console=args.console, after=args.after))
            if args.discovery:
                result["source_code_index"] = code_status
        except ValueError as error:
            parser.error(str(error))
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    if args.command == "lab":
        filters = {field: getattr(args,field) for field in (
            "equipment","status","task","os","kind","specialty","difficulty","age","console")}
        try:
            print(json.dumps(build_lab(catalog, **filters), indent=2, ensure_ascii=True))
        except ValueError as error:
            parser.error(str(error))
        return 0
    if args.command == "refresh-lab":
        from .lab import TASKS
        from .lab_reports import refresh_reports

        print(json.dumps({"tasks": refresh_reports(catalog, TASKS, authenticated=args.authenticated)}, indent=2, ensure_ascii=True))
        return 0
    if args.command == "serve":
        serve(catalog, args)
        return 0
    if args.command == "export":
        from .export import export

        try:
            print(export(catalog, args.out, args.repository))
        except ValueError as exc:
            parser.error(str(exc))
        return 0
    if args.command in {"backfill", "incremental"}:
        from .github import backfill, backfill_status, commit_backfill, incremental

        operation = backfill if args.command == "backfill" else incremental
        batch = operation(catalog.projects(), catalog.path, pages=args.pages)
        catalog.record_sync(batch, update_health=False, history_mode=args.command)
        commit_backfill(catalog.path, batch["checkpoint"])
        result = {"observations_saved": len(batch["items"]), "warnings": batch["warnings"],
                  "history": backfill_status(catalog.path, mode=args.command)}
        if args.command == "incremental" and args.discovery:
            from .discovery_scan import scan

            result["discovery"] = scan(catalog, catalog.observations(limit=None), online=True, scheduled=True)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    if args.command == "sync":
        try:
            status = sync_catalog(catalog, refresh=args.force, pages=args.pages, sources=args.source or ())
        except ValueError as exc:
            parser.error(str(exc))
    else:
        status = catalog.health()
    print(json.dumps(status, indent=2, ensure_ascii=True))
    targeted = status.get("targeted_refresh")
    if targeted:
        return int(not targeted["observations_saved"])
    return int(args.command == "sync" and status["status"] == "error")


if __name__ == "__main__":
    raise SystemExit(main())
