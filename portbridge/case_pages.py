"""Static pages for curated compatibility findings."""

from html import escape
import re
from xml.etree import ElementTree

from .preflight import PUBLIC_BASE, english_text


CASE_FILE = re.compile(r"pb-[0-9]{4,}(?:\.ru)?\.html")
LABELS = {
    "en": {
        "navigation": "PortBridge navigation", "card": "Catalog card", "language": "English",
        "recorded": "Recorded in the catalog", "report_date": "Report date",
        "outcomes": {"passed": "Passed", "failed": "Failed", "mixed": "Mixed result", "observed": "Observed",
                     "unknown": "Result pending"},
        "kinds": {"independent": "Independent verification", "automated_test": "Automated test",
                  "maintainer_claim": "Author report", "source_observation": "Source observation"},
    },
    "ru": {
        "navigation": "Навигация PortBridge", "card": "Карточка", "language": "Русский",
        "recorded": "Записано в каталоге", "report_date": "Дата отчёта",
        "outcomes": {"passed": "Пройдено", "failed": "Не пройдено", "mixed": "Смешанный результат",
                     "observed": "Наблюдение", "unknown": "Результат уточняется"},
        "kinds": {"independent": "Независимая проверка", "automated_test": "Автоматическая проверка",
                  "maintainer_claim": "Отчёт автора", "source_observation": "Наблюдение в источнике"},
    },
}


def case_languages(card):
    return ("en", "ru") if english_text(card, "title") and english_text(card, "summary") else ("ru",)


def case_path(card, language=None):
    suffix = ".ru" if language == "ru" and case_languages(card)[0] == "en" else ""
    return f"cases/{card['id'].lower()}{suffix}.html"


def localized_html(record, field, language):
    translation = english_text(record, field) if language == "en" else None
    return escape(translation or record[field])


def link(source, language):
    return f'<a href="{escape(source["url"])}">{localized_html(source, "title", language)}</a>'


def evidence_block(evidence, language):
    labels = LABELS[language]
    outcome = labels["outcomes"][evidence.get("outcome", "unknown")]
    kind = labels["kinds"][evidence["kind"]]
    platform = ", ".join(evidence["platforms"])
    revision = f' <code>{escape(evidence["revision"])}</code>' if evidence["revision"] else ""
    scope = f" · {escape(platform)}" if platform else ""
    report_date = evidence.get("reported_at")
    date = (f'<p>{labels["report_date"]} <time datetime="{escape(report_date)}">{escape(report_date[:10])}</time></p>'
            if report_date else "")
    return (f'<li class="case-evidence"><p><strong>{kind} · {outcome}</strong>{scope}{revision}</p>'
            f'<p>{link(evidence, language)}</p>{date}<p>{localized_html(evidence, "observed", language)}</p></li>')


def case_page(card, names, language=None):
    languages = case_languages(card)
    language = language or languages[0]
    labels = LABELS[language]
    title = localized_html(card, "title", language)
    ident = escape(card["id"])
    summary = localized_html(card, "summary", language)
    date = escape(card["recorded_at"][:10])
    canonical = PUBLIC_BASE + case_path(card, language)
    alternates = language_link = ""
    dashboard = "../?lang=ru#/problems/" if language == "ru" else "../#/problems/"
    if len(languages) > 1:
        variants = {variant: case_path(card, variant) for variant in languages}
        variants["x-default"] = case_path(card)
        alternates = "\n".join(f'<link rel="alternate" hreflang="{variant}" href="{PUBLIC_BASE}{path}">'
                               for variant, path in variants.items())
        other = "ru" if language == "en" else "en"
        relative = variants[other].removeprefix("cases/")
        language_link = f' · <a href="{relative}" lang="{other}" hreflang="{other}">{LABELS[other]["language"]}</a>'
    sections = []
    for solution in card["solutions"]:
        project = escape(names[solution["project"]])
        references = "".join(f"<li>{link(source, language)}</li>" for source in solution["source_refs"])
        evidence = "".join(evidence_block(item, language) for item in solution["evidence"])
        sections.append(f'<section class="case-section"><h2>{project}</h2><p>{localized_html(solution, "summary", language)}</p>'
                        f'<ul>{references}</ul><ul class="case-results">{evidence}</ul></section>')
    return f"""<!doctype html>
<html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="PortBridge">
<title>{title} · PortBridge</title><meta name="description" content="{summary}">
<link rel="canonical" href="{canonical}"><link rel="stylesheet" href="../static/styles.css">
{alternates}
</head><body><main class="case-page">
<nav aria-label="{labels['navigation']}"><a href="{dashboard}{ident}">← {labels['card']} {ident}</a>{language_link}</nav>
<header><h1>{title}</h1><p>{summary}</p><p>{labels['recorded']} <time datetime="{date}">{date}</time></p></header>
{''.join(sections)}
</main></body></html>
"""


def sitemap(cards):
    root = ElementTree.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    case_urls = (PUBLIC_BASE + case_path(card, language) for card in cards for language in case_languages(card))
    for url in [PUBLIC_BASE, *case_urls]:
        ElementTree.SubElement(ElementTree.SubElement(root, "url"), "loc").text = url
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
