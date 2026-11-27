"""Export the same catalog to a portable directory of public static files."""

from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import quote

from .activity import build_activity
from .case_pages import CASE_FILE, case_languages, case_page, case_path, sitemap
from .backup import backup_database
from .catalog import REPO_NAME, ReadOnlyCatalog, timestamp
from .coordination import knowledge_graph, recommendations
from .discovery_scan import cached_index
from .code_search import projection as code_projection
from .ecosystem import build_ecosystem
from .feed import build_feed
from .identity import SCHEMA_VERSION
from .integrations import projection as partner_projection
from .lab import build_lab
from .radar_store import epoch, radar_view, reviewed_snapshot
from .community import people
from .preflight_index import MANIFEST, SHARD, SHARD_FORMAT, VERSIONED_MANIFEST, build_search_files
from .public_browse import BROWSE_INDEX, BROWSE_MANIFEST, BROWSE_PAGE, BROWSE_POSTING, BROWSE_TERMS, build_browse_files


PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
ASSETS = {"index.html": "index.html", "letter.html": "letter.html", "letter.ru.html": "letter.ru.html",
          "start.html": "start.html", "start.ru.html": "start.ru.html", "partner.html": "partner.html",
          "static/partner.js": "partner.js",
          "static/styles.css": "styles.css", "static/app.js": "app.js", "static/discovery.js": "discovery.js"}
SNAPSHOTS = {"site", "projects", "ecosystem", "problems", "matches", "health", "observations", "coordination", "outreach", "activity", "lab", "discovery", "radar", "people", "people-directory", "impact", "partner", "source-code",
             "graph", "source-history", "recommendations"}
VERSIONED_SNAPSHOTS = ("projects", "ecosystem", "problems", "health", "lab", "activity", "outreach", "coordination", "discovery", "radar", "people", "people-directory", "impact", "partner", "source-code")
VERSIONED_SNAPSHOT = re.compile(rf"(?:{'|'.join(VERSIONED_SNAPSHOTS)})-([0-9a-f]{{24}})\.json")
VERSIONED_ASSET = re.compile(r"(?:styles-([0-9a-f]{24})\.css|(?:app|discovery)-([0-9a-f]{24})\.js)")
MATCH_PREVIEW_LIMIT = 200
RELEASE_FILES = "release-files.json"
# The existing bridge mark doubles as the icon even on a subpath or an offline copy.
SITE_ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
             '<rect width="32" height="32" rx="7" fill="#b8e69e"/>'
             '<path d="M6 20a10 10 0 0 1 20 0M4 21h24" fill="none" stroke="#132724" stroke-width="2"/></svg>')
ICON_LINK = ('<link rel="icon" href="data:image/svg+xml,' + quote(SITE_ICON, safe="") + '">').encode("ascii")
EXPORT_FILES = {*ASSETS, MANIFEST, BROWSE_MANIFEST, RELEASE_FILES, "api.html", "api.ru.html", "feed.xml", "feed.ru.xml", "sitemap.xml", ".nojekyll",
                *(f"data/{name}.json" for name in SNAPSHOTS)}


def docs_page(language="en"):
    filename, back, alternate, label = {
        "en": ("API.en.md", "Back to PortBridge", "api.ru.html", "Русский"),
        "ru": ("API.md", "Вернуться в PortBridge", "api.html", "English"),
    }[language]
    suffix = "?lang=ru" if language == "ru" else ""
    docs = escape((ROOT / filename).read_text(encoding="utf-8"))
    return f'''<!doctype html>
<html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PortBridge API</title><link rel="stylesheet" href="./static/styles.css"></head>
<body><main class="api-documentation"><p><a href="./{suffix}">← {back}</a> · <a href="./{alternate}">{label}</a></p>
<pre>{docs}</pre></main></body></html>
'''


def content_id(payload):
    return sha256(payload).hexdigest()[:24]


def release_inventory_digest(files):
    body = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("ascii")
    return sha256(body).hexdigest()


def generated_file(folder, name):
    if folder == "data":
        if SHARD.fullmatch(name) or BROWSE_TERMS.fullmatch(name):
            return f'{{"format":"{SHARD_FORMAT}",'.encode("ascii")
        if BROWSE_PAGE.fullmatch(name) or BROWSE_POSTING.fullmatch(name):
            return b'{"items":['
        if BROWSE_INDEX.fullmatch(name):
            return b'{"version":1,"generation":'
        if VERSIONED_MANIFEST.fullmatch(name):
            return b'{"version":1,"generation":'
        match = VERSIONED_SNAPSHOT.fullmatch(name)
    elif folder == "static":
        match = VERSIONED_ASSET.fullmatch(name)
    else:
        return None
    return next((digest for digest in match.groups() if digest), None) if match else None


def recognized_file(path, marker):
    with path.open("rb") as stream:
        if isinstance(marker, bytes):
            return stream.read(len(marker)) == marker
        identity = sha256()
        for block in iter(lambda: stream.read(64 * 1024), b""):
            identity.update(block)
    return identity.hexdigest()[:24] == marker


def output_path(directory):
    directory = Path(directory).expanduser().resolve()
    if directory == ROOT or directory in ROOT.parents or directory == PACKAGE or PACKAGE in directory.parents:
        raise ValueError("export must use a separate output directory")
    if directory.is_dir():
        allowed_dirs = {"data", "static", "cases"}
        for child in directory.iterdir():
            if child.is_symlink() or (hasattr(child, "is_junction") and child.is_junction()):
                raise ValueError("export directory contains a link")
            if child.is_dir() and child.name in allowed_dirs:
                for entry in child.iterdir():
                    is_output_file = (CASE_FILE.fullmatch(entry.name) if child.name == "cases"
                                      else f"{child.name}/{entry.name}" in EXPORT_FILES)
                    marker = generated_file(child.name, entry.name)
                    if entry.is_symlink() or not entry.is_file() or not (is_output_file or marker):
                        raise ValueError("export directory contains files outside PortBridge's public snapshot")
                    if marker and not recognized_file(entry, marker):
                        raise ValueError("export directory contains an unrecognized generated file")
                    if child.name == "cases":
                        with entry.open("rb") as stream:
                            if b'<meta name="generator" content="PortBridge">' not in stream.read(4096):
                                raise ValueError("export directory contains an unrecognized case page")
            elif not child.is_file() or child.name not in EXPORT_FILES:
                raise ValueError("export directory contains files outside PortBridge's public snapshot")
    return directory


def browser_assets():
    assets = {path: (PACKAGE / "static" / source).read_bytes() for path, source in ASSETS.items()}
    index = assets["index.html"].decode("utf-8")
    index = index.replace("<head>", '<head>\n  <meta name="portbridge-mode" content="snapshot">', 1)
    index = index.replace('href="/api/docs?lang=en"', 'href="./api.html"')
    for path in ("static/styles.css", "static/discovery.js", "static/app.js"):
        source = Path(path)
        alias = f"static/{source.stem}-{content_id(assets[path])}{source.suffix}"
        assets[alias] = assets[path]
        index = re.sub(rf'\./{re.escape(path)}(?:\?[^"]*)?(?=")', f"./{alias}", index)
    assets["index.html"] = index.encode("utf-8")
    return assets


def export(catalog, directory, repository=""):
    if repository and not REPO_NAME.fullmatch(repository):
        raise ValueError("--repository expects a GitHub owner/repo")
    directory = output_path(directory)
    with TemporaryDirectory(prefix="portbridge-export-") as temp:
        checkpoint = backup_database(catalog.path, Path(temp) / "snapshot.sqlite3")
        return _export(ReadOnlyCatalog(checkpoint), directory, repository)


def _export(catalog, directory, repository):
    matches = catalog.matches(limit=None)
    preview = matches[:MATCH_PREVIEW_LIMIT]
    generated_at = timestamp()
    data = {
        "site": {"name": "PortBridge", "api_version": 1, "data_schema_version": SCHEMA_VERSION,
                 "mode": "snapshot", "generated_at": generated_at,
                 "repository": repository or None, "issue_template": "evidence.yml"},
        "projects": {"projects": catalog.projects()},
        "problems": {"problems": catalog.problems()},
        "matches": {"matches": preview, "total": len(matches)},
        "health": catalog.health(generated_at=generated_at),
        "discovery": cached_index(catalog),
        "source-code": code_projection(catalog),
        "lab": build_lab(catalog, now=epoch(generated_at)),
        "radar": radar_view(catalog, epoch(generated_at), include_catalog=True),
        "observations": {"observations": catalog.observations(limit=None)},
        "coordination": {"coordination": catalog.coordination()},
        "graph": knowledge_graph(catalog),
        "source-history": {"changes": catalog.source_changes()},
        "recommendations": {"recommendations": recommendations(catalog, matches=preview)},
        "outreach": {"drafts": catalog.outreach()},
    }
    data["radar"]["findings"] = reviewed_snapshot(catalog, lab=data["lab"])
    data["activity"] = build_activity(catalog, projects=data["projects"]["projects"], cards=data["problems"]["problems"],
                                      observations=data["observations"]["observations"], health=data["health"],
                                      drafts=data["outreach"]["drafts"])
    data["ecosystem"] = build_ecosystem(catalog, projects=data["projects"]["projects"],
                                       observations=data["observations"]["observations"])
    data["people"], data["impact"] = people(catalog, now=epoch(generated_at), lab=data["lab"],
                                            radar=data["radar"], observations=data["observations"]["observations"],
                                            projects=data["projects"]["projects"])
    data["partner"] = partner_projection(data["projects"]["projects"], data["lab"], data["impact"], as_of=generated_at)
    directory_view = data["people"]
    data["people-directory"] = {**directory_view, "profiles": [
        {**{key: row[key] for key in ("id", "login", "url", "latest", "activity", "consoles", "availability")},
         "roles": [{key: role[key] for key in ("role", "repo", "source", "confidence", "age")} for role in row["roles"][:3]],
         "projects": [{"repo": entry["repo"]} for entry in row["projects"]],
         "specialties": [{"name": tag["name"]} for tag in row["specialties"]],
         "evidence": [{key: evidence[key] for key in ("subject", "source", "discovery_for") if key in evidence}
                      for evidence in row["evidence"]]}
        for row in directory_view["profiles"]]}
    search = build_search_files(data["projects"]["projects"], data["observations"]["observations"])
    manifest = search.pop(MANIFEST)
    index = json.loads(manifest)
    data["site"]["search_index"] = {key: index[key] for key in ("version", "generation")}
    browse = build_browse_files(matches, data["observations"]["observations"])
    browse_manifest = browse.pop(BROWSE_MANIFEST)
    index = json.loads(browse_manifest)
    site = data.pop("site")
    site["browse_index"] = {key: index[key] for key in ("version", "generation")}
    contents = {f"data/{name}.json": json.dumps(value, ensure_ascii=False).encode("utf-8")
                for name, value in data.items()}
    site["snapshots"] = {}
    for name in VERSIONED_SNAPSHOTS:
        body = contents[f"data/{name}.json"]
        alias = f"{name}-{content_id(body)}.json"
        site["snapshots"][name] = alias
        contents[f"data/{alias}"] = body
    contents.update(search)
    contents.update(browse)
    contents[f"data/preflight-{site['search_index']['generation']}-index.json"] = manifest
    site["search_index"]["manifest"] = f"preflight-{site['search_index']['generation']}-index.json"
    contents.update(browser_assets())
    contents["api.html"] = docs_page("en").encode("utf-8")
    contents["api.ru.html"] = docs_page("ru").encode("utf-8")
    contents["feed.xml"] = build_feed(catalog, language="en")
    contents["feed.ru.xml"] = build_feed(catalog, language="ru")
    contents[".nojekyll"] = b""
    cards = data["problems"]["problems"]
    names = {project["slug"]: project["name"] for project in data["projects"]["projects"]}
    contents["sitemap.xml"] = sitemap(cards)
    for card in cards:
        for language in case_languages(card):
            contents[case_path(card, language)] = case_page(card, names, language).encode("utf-8")
    if (directory / "cases").is_dir():
        for path in (directory / "cases").iterdir():
            if f"cases/{path.name}" not in contents:
                path.unlink()
    contents[MANIFEST] = manifest
    contents[BROWSE_MANIFEST] = browse_manifest
    contents["data/site.json"] = json.dumps(site, ensure_ascii=False).encode("utf-8")
    for name, value in contents.items():
        if name.endswith(".html"):
            contents[name] = value.replace(b"</head>", ICON_LINK + b"</head>", 1)
    files = {name: sha256(value).hexdigest() for name, value in contents.items()}
    for path, value in contents.items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    for folder in ("data", "static"):
        for path in (directory / folder).iterdir():
            if generated_file(folder, path.name) and f"{folder}/{path.name}" not in contents:
                path.unlink()
    inventory = {"version": 1, "files": files, "sha256": release_inventory_digest(files)}
    (directory / RELEASE_FILES).write_text(json.dumps(inventory, sort_keys=True), encoding="utf-8")
    return directory
