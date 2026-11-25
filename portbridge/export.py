"""Export the same catalog to a portable directory of public static files."""

from html import escape
import json
from pathlib import Path

from .activity import build_activity
from .case_pages import CASE_FILE, case_languages, case_page, case_path, sitemap
from .catalog import REPO_NAME, timestamp
from .coordination import knowledge_graph, recommendations
from .ecosystem import build_ecosystem
from .feed import build_feed
from .lab import build_lab
from .preflight_index import MANIFEST, SHARD, SHARD_FORMAT, build_search_files


PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
ASSETS = {"index.html": "index.html", "static/styles.css": "styles.css", "static/app.js": "app.js"}
SNAPSHOTS = {"site", "projects", "ecosystem", "problems", "matches", "health", "observations", "coordination", "outreach", "activity", "lab",
             "graph", "source-history", "recommendations"}
EXPORT_FILES = {*ASSETS, MANIFEST, "api.html", "api.ru.html", "feed.xml", "feed.ru.xml", "sitemap.xml", ".nojekyll",
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
                    is_output_file = is_output_file or (child.name == "data" and SHARD.fullmatch(entry.name))
                    if entry.is_symlink() or not entry.is_file() or not is_output_file:
                        raise ValueError("export directory contains files outside PortBridge's public snapshot")
                    if child.name == "data" and SHARD.fullmatch(entry.name):
                        with entry.open("rb") as stream:
                            marker = f'{{"format":"{SHARD_FORMAT}",'.encode("ascii")
                            if stream.read(len(marker)) != marker:
                                raise ValueError("export directory contains an unrecognized search shard")
                    if child.name == "cases":
                        with entry.open("rb") as stream:
                            if b'<meta name="generator" content="PortBridge">' not in stream.read(4096):
                                raise ValueError("export directory contains an unrecognized case page")
            elif not child.is_file() or child.name not in EXPORT_FILES:
                raise ValueError("export directory contains files outside PortBridge's public snapshot")
    return directory


def export(catalog, directory, repository=""):
    if repository and not REPO_NAME.fullmatch(repository):
        raise ValueError("--repository expects a GitHub owner/repo")
    directory = output_path(directory)
    data = {
        "site": {"name": "PortBridge", "api_version": 1, "mode": "snapshot", "generated_at": timestamp(),
                 "repository": repository or None, "issue_template": "evidence.yml"},
        "projects": {"projects": catalog.projects()},
        "problems": {"problems": catalog.problems()},
        "matches": {"matches": catalog.matches(limit=200)},
        "health": catalog.health(),
        "lab": build_lab(catalog),
        "observations": {"observations": catalog.observations(limit=None)},
        "coordination": {"coordination": catalog.coordination()},
        "graph": knowledge_graph(catalog),
        "source-history": {"changes": catalog.source_changes()},
        "recommendations": {"recommendations": recommendations(catalog)},
        "outreach": {"drafts": catalog.outreach()},
    }
    data["activity"] = build_activity(catalog, projects=data["projects"]["projects"], cards=data["problems"]["problems"],
                                      observations=data["observations"]["observations"], health=data["health"],
                                      drafts=data["outreach"]["drafts"])
    data["ecosystem"] = build_ecosystem(catalog, projects=data["projects"]["projects"],
                                       observations=data["observations"]["observations"])
    search = build_search_files(data["projects"]["projects"], data["observations"]["observations"])
    manifest = search.pop(MANIFEST)
    index = json.loads(manifest)
    data["site"]["search_index"] = {key: index[key] for key in ("version", "generation")}
    site = json.dumps(data.pop("site"), ensure_ascii=False).encode("utf-8")
    contents = {f"data/{name}.json": json.dumps(value, ensure_ascii=False).encode("utf-8")
                for name, value in data.items()}
    contents.update(search)
    contents.update({path: (PACKAGE / "static" / source).read_bytes() for path, source in ASSETS.items()})
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
    for path, value in contents.items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    (directory / MANIFEST).write_bytes(manifest)
    (directory / "data/site.json").write_bytes(site)
    for path in (directory / "data").iterdir():
        if SHARD.fullmatch(path.name) and f"data/{path.name}" not in search:
            path.unlink()
    return directory
