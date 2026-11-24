"""Verify localized Atom progress without changing subscription identity."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.etree import ElementTree

from portbridge.__main__ import DEFAULT_SEED
from portbridge.catalog import Catalog
from portbridge.feed import build_feed


ATOM = "{http://www.w3.org/2005/Atom}"
LANGUAGE = "{http://www.w3.org/XML/1998/namespace}lang"


class FeedTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.workspace = Path(directory.name)
        self.catalog = Catalog(self.workspace / "catalog.sqlite3", DEFAULT_SEED)

    @staticmethod
    def entries(feed):
        return {entry.findtext(ATOM + "id"): entry for entry in feed.findall(ATOM + "entry")}

    def test_english_is_default_and_russian_preserves_the_same_reviewed_records(self):
        english = ElementTree.fromstring(build_feed(self.catalog))
        russian = ElementTree.fromstring(build_feed(self.catalog, language="ru"))
        self.assertEqual(english.attrib[LANGUAGE], "en")
        self.assertEqual(russian.attrib[LANGUAGE], "ru")
        self.assertEqual(english.findtext(ATOM + "title"), "PortBridge — reviewed progress")
        self.assertEqual(russian.findtext(ATOM + "title"), "PortBridge — проверенный прогресс")
        for field in ("id", "updated"):
            self.assertEqual(english.findtext(ATOM + field), russian.findtext(ATOM + field))

        english_entries, russian_entries = self.entries(english), self.entries(russian)
        self.assertEqual(list(english_entries), [
            "urn:portbridge:PB-0009", "urn:portbridge:PB-0008", "urn:portbridge:PB-0007",
            "urn:portbridge:PB-0006",
            "urn:portbridge:PB-044801754884724660835754613454516035131",
            "urn:portbridge:PB-0005", "urn:portbridge:PB-0002", "urn:portbridge:PB-0001",
        ])
        self.assertEqual(list(english_entries), list(russian_entries))
        for ident, entry in english_entries.items():
            other = russian_entries[ident]
            card = self.catalog.problem(ident.removeprefix("urn:portbridge:"))
            self.assertEqual(entry.findtext(ATOM + "updated"), other.findtext(ATOM + "updated"))
            self.assertEqual(entry.find(ATOM + "link").get("href"), other.find(ATOM + "link").get("href"))
            self.assertIn(card["translations"]["en"]["title"], entry.findtext(ATOM + "title"))
            self.assertIn(card["translations"]["en"]["summary"], entry.findtext(ATOM + "summary"))
            self.assertIn(card["title"], other.findtext(ATOM + "title"))
            self.assertIn(card["summary"], other.findtext(ATOM + "summary"))
            solution = next(item for item in card["solutions"] if item["status"] in {"verified", "merged"})
            self.assertIn(solution["translations"]["en"]["summary"], entry.findtext(ATOM + "summary"))
            self.assertIn(solution["summary"], other.findtext(ATOM + "summary"))

    def test_custom_editorial_fields_remain_when_english_translations_are_missing(self):
        seed = json.loads(DEFAULT_SEED.read_bytes())
        card = seed["problems"][0]
        del card["translations"]
        solution = next(item for item in card["solutions"] if item["status"] == "verified")
        del solution["translations"]
        seed_path = self.workspace / "custom-seed.json"
        seed_path.write_text(json.dumps(seed), encoding="utf-8")
        catalog = Catalog(self.workspace / "catalog.sqlite3", seed_path)
        feed = ElementTree.fromstring(build_feed(catalog))
        entry = self.entries(feed)["urn:portbridge:PB-0001"]
        self.assertIn(card["title"], entry.findtext(ATOM + "title"))
        self.assertIn(card["summary"], entry.findtext(ATOM + "summary"))
        self.assertIn(solution["summary"], entry.findtext(ATOM + "summary"))


if __name__ == "__main__":
    unittest.main()
