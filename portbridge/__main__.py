"""Command line and localhost API for PortBridge."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Event, Thread
from urllib.parse import parse_qs, unquote, urlsplit

from .activity import build_activity
from .case_pages import CASE_FILE, case_languages, case_page, case_path
from .catalog import Catalog, OBSERVATION_KIND, PROBLEM_ID, PROBLEM_STATUS
from .coordination import knowledge_graph, recommendations
from .ecosystem import build_ecosystem, refresh_ecosystem
from .exchange_api import ExchangeHandlerMixin
from .feed import build_feed
from .lab import build_lab


PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
DEFAULT_DB = ROOT / ".portbridge" / "portbridge.sqlite3"
DEFAULT_SEED = PACKAGE / "data" / "seed.json"
STATIC = {
    "/": (PACKAGE / "static" / "index.html", "text/html; charset=utf-8"),
    "/static/styles.css": (PACKAGE / "static" / "styles.css", "text/css; charset=utf-8"),
    "/static/app.js": (PACKAGE / "static" / "app.js", "text/javascript; charset=utf-8"),
    "/api/docs": (ROOT / "API.md", "text/plain; charset=utf-8"),
}
OFFICE_STATIC = {
    "/office": (PACKAGE / "static" / "office.html", "text/html; charset=utf-8"),
    "/static/office.css": (PACKAGE / "static" / "office.css", "text/css; charset=utf-8"),
    "/static/office.js": (PACKAGE / "static" / "office.js", "text/javascript; charset=utf-8"),
}
COLLECTIONS = ("projects", "ecosystem", "problems", "observations", "matches", "related", "preflight", "coordination", "activity", "lab",
               "graph", "source-history", "recommendations", "outreach", "health")


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
    watched = refresh_references(projects, catalog.path, references, refresh=refresh)
    result["items"].extend(watched["items"])
    result["warnings"].extend(watched["warnings"])
    catalog.record_sync(result, update_health=False)
    candidates = revision_references(catalog.observations(limit=None))
    checked = {"items": [], "warnings": []}
    if candidates:
        checked = refresh_references(projects, catalog.path, candidates, refresh=refresh)
    catalog.record_sync({**result, "items": checked["items"], "warnings": result["warnings"] + checked["warnings"]})
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
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
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
        self.json_response(405, {"error": "read-only API"})

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
        catalog = self.server.catalog
        if path in {"/api/v1", "/api/v1/"}:
            return 200, {"name": "PortBridge", "version": 1, "read_only": True, "docs": "/api/docs",
                         "exchange_enabled": self.server.exchange is not None,
                         "routes": {key: f"/api/v1/{key}" for key in COLLECTIONS}}
        name = path.removeprefix("/api/v1/")
        if name == "projects":
            return 200, {"projects": catalog.projects()}
        if path == "/api/v1/ecosystem":
            return 200, build_ecosystem(catalog)
        if name == "health":
            return 200, catalog.health()
        if name == "activity":
            return 200, build_activity(catalog)
        if name == "lab":
            if params.keys() - {"equipment", "status", "task"} or any(len(values) != 1 for values in params.values()):
                raise ValueError("use each Test Lab filter at most once")
            return 200, build_lab(**{key: values[0] for key, values in params.items()})
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
    stop = Event()

    def poll():
        while not stop.is_set():
            try:
                sync_catalog(catalog, pages=args.pages)
            except Exception as exc:
                print(f"GitHub sync failed: {type(exc).__name__}", file=sys.stderr)
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
    commands.add_parser("status", help="show cached synchronization status")
    backup = commands.add_parser("backup", help="write a separate verified SQLite backup of --db")
    backup.add_argument("--out", type=Path, required=True)
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
            print(backup_database(args.db, args.out))
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        return 0
    catalog = Catalog(args.db, args.seed)
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
        print(json.dumps({"observations_saved": len(batch["items"]), "warnings": batch["warnings"],
                          "history": backfill_status(catalog.path, mode=args.command)}, indent=2, ensure_ascii=True))
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
