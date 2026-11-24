"""Opt-in feed of progress already reviewed in the catalog."""

import xml.etree.ElementTree as ET

from .preflight import english_text


def build_feed(catalog, language="en"):
    titles = {"en": "PortBridge — reviewed progress", "ru": "PortBridge — проверенный прогресс"}
    if language not in titles:
        raise ValueError("Feed language must be en or ru")

    def localized(record, field):
        translation = english_text(record, field) if language == "en" else None
        return translation or record[field]

    feed = ET.Element("feed", {"xmlns": "http://www.w3.org/2005/Atom", "xml:lang": language})
    ET.SubElement(feed, "id").text = "urn:portbridge:reviewed-progress"
    ET.SubElement(feed, "title").text = titles[language]
    ET.SubElement(ET.SubElement(feed, "author"), "name").text = "PortBridge"
    entries = []
    for problem in catalog.problems():
        ready = [solution for solution in problem["solutions"] if solution["status"] in {"verified", "merged"}]
        if ready and problem.get("recorded_at"):
            entries.append((problem, ready))
    ET.SubElement(feed, "updated").text = max((p["recorded_at"] for p, _ in entries),
                                           default="2026-11-24T00:00:00Z")
    for problem, ready in sorted(entries, key=lambda row: (row[0]["recorded_at"], row[0]["id"]), reverse=True):
        entry = ET.SubElement(feed, "entry")
        ident = problem["id"]
        ET.SubElement(entry, "id").text = f"urn:portbridge:{ident}"
        ET.SubElement(entry, "title").text = f"{ident} — {localized(problem, 'title')}"
        ET.SubElement(entry, "updated").text = problem["recorded_at"]
        ET.SubElement(entry, "link", href=ready[0]["source_refs"][0]["url"])
        ET.SubElement(entry, "summary").text = "\n\n".join(
            [localized(problem, "summary"),
             *(f"{solution['project']}: {localized(solution, 'summary')}" for solution in ready)]
        )
    return ET.tostring(feed, encoding="utf-8", xml_declaration=True)
