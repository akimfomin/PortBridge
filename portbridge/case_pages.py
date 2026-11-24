"""Static pages for curated compatibility findings."""

from html import escape
import re
from xml.etree import ElementTree

from .preflight import PUBLIC_BASE


CASE_FILE = re.compile(r"pb-[0-9]{4,}\.html")
OUTCOMES = {"passed": "Пройдено", "failed": "Не пройдено", "mixed": "Смешанный результат",
            "observed": "Наблюдение", "unknown": "Результат уточняется"}
KINDS = {"independent": "Независимая проверка", "automated_test": "Автоматическая проверка",
         "maintainer_claim": "Отчёт автора", "source_observation": "Наблюдение в источнике"}


def case_path(card):
    return f"cases/{card['id'].lower()}.html"


def link(source):
    return f'<a href="{escape(source["url"])}">{escape(source["title"])}</a>'


def evidence_block(evidence):
    outcome = OUTCOMES[evidence.get("outcome", "unknown")]
    kind = KINDS[evidence["kind"]]
    platform = ", ".join(evidence["platforms"])
    revision = f' <code>{escape(evidence["revision"])}</code>' if evidence["revision"] else ""
    scope = f" · {escape(platform)}" if platform else ""
    report_date = evidence.get("reported_at")
    date = f'<p>Дата отчёта <time datetime="{escape(report_date)}">{escape(report_date[:10])}</time></p>' if report_date else ""
    return (f'<li class="case-evidence"><p><strong>{kind} · {outcome}</strong>{scope}{revision}</p>'
            f'<p>{link(evidence)}</p>{date}<p>{escape(evidence["observed"])}</p></li>')


def case_page(card, names):
    title, ident = escape(card["title"]), escape(card["id"])
    summary = escape(card["summary"])
    date = escape(card["recorded_at"][:10])
    sections = []
    for solution in card["solutions"]:
        project = escape(names[solution["project"]])
        references = "".join(f"<li>{link(source)}</li>" for source in solution["source_refs"])
        evidence = "".join(evidence_block(item) for item in solution["evidence"])
        sections.append(f'<section class="case-section"><h2>{project}</h2><p>{escape(solution["summary"])}</p>'
                        f'<ul>{references}</ul><ul class="case-results">{evidence}</ul></section>')
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="PortBridge">
<title>{title} · PortBridge</title><meta name="description" content="{summary}">
<link rel="canonical" href="{PUBLIC_BASE}{case_path(card)}"><link rel="stylesheet" href="../static/styles.css">
</head><body><main class="case-page">
<nav aria-label="Навигация PortBridge"><a href="../#/problems/{ident}">← Карточка {ident}</a></nav>
<header><h1>{title}</h1><p>{summary}</p><p>Записано в каталоге <time datetime="{date}">{date}</time></p></header>
{''.join(sections)}
</main></body></html>
"""


def sitemap(cards):
    root = ElementTree.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for url in [PUBLIC_BASE, *(f"{PUBLIC_BASE}{case_path(card)}" for card in cards)]:
        ElementTree.SubElement(ElementTree.SubElement(root, "url"), "loc").text = url
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
