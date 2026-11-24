import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from portbridge.__main__ import DEFAULT_SEED
from portbridge.catalog import Catalog
from portbridge.ecosystem import AREAS, SEARCH_INTERVAL, _project_names, build_ecosystem, refresh_ecosystem
from portbridge.export import export
from portbridge.mcp import PortBridgeMCP


class EcosystemTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.catalog = Catalog(self.path / "catalog.sqlite3", DEFAULT_SEED)

    def test_parsers_keep_only_expected_repository_links(self):
        six = {"projects": [{"repo": "Example/Port"}, {"repo": "https://bad.test/project"}],
               "tools": [{"repo": "ignore/tool"}], "lookalikes": [{"repo": "Fake/Copy"}]}
        watch = {"efforts": [{"repo": "Example/Port"}], "tools": [],
                 "candidates": [{"repo": "Dev/Two"}, {"repo": "network/.."}],
                 "ignored": [{"repo": "Fake/Copy"}]}
        race = b"""
            <a class="name" href="https://github.com/example/outside">Outside</a>
            <section id="standings">
             <a class="name expanded" href="https://github.com/Example/Port/">Port</a>
             <a class="name" href="https://github.com.example.org/a/b">Spoof</a>
             <a class="name" href="https://github.com/a/b/issues/2">Issue</a>
             <a href="https://github.com/comment/other">Other</a>
            </section><section id="forecast">
             <a class="name" href="https://github.com/example/outside">Outside</a>
            </section>"""
        self.assertEqual(_project_names("six-on-pc", json.dumps(six).encode()), ["example/port"])
        self.assertEqual(_project_names("portwatch-vi", json.dumps(watch).encode()), ["dev/two", "example/port"])
        self.assertEqual(_project_names("pc-race", race), ["example/port"])
        with self.assertRaises(ValueError):
            _project_names("six-on-pc", b'{"projects":[{"repository":"example/port"}]}')

    def test_failures_keep_last_good_candidates_and_limit_retry_frequency(self):
        with (patch("portbridge.ecosystem.time.time", return_value=100),
              patch("portbridge.ecosystem._fetch_tracker", return_value=(["example/port", "ivall/xcl"], '"tag"')) as fetch,
              patch("portbridge.ecosystem.find_public_projects",
                    return_value={"shaders": ["Example/Port", "Another/One"], "linux": [], "windows": []}) as search):
            refresh_ecosystem(self.catalog)
            refresh_ecosystem(self.catalog)
            self.assertEqual(fetch.call_count, 3)
            self.assertEqual(search.call_count, 1)
        with (patch("portbridge.ecosystem.time.time", return_value=100 + SEARCH_INTERVAL),
              patch("portbridge.ecosystem._fetch_tracker", side_effect=[
                  (None, '"tag"'), OSError("offline"), (["example/port"], '"fresh"'),
              ]) as retry,
              patch("portbridge.ecosystem.find_public_projects", return_value={"shaders": []})):
            refresh_ecosystem(self.catalog)
            retry.assert_any_call("six-on-pc", '"tag"')
        result = build_ecosystem(self.catalog)
        self.assertEqual([row["state"] for row in result["sources"]], ["ok", "cached", "ok", "cached"])
        self.assertEqual([row["repo"] for row in result["leads"]], ["example/port", "another/one"])
        self.assertEqual(len(result["leads"][0]["sources"]), 4)

    def test_export_and_agent_read_same_reviewed_capability_evidence(self):
        snapshot = build_ecosystem(self.catalog)
        self.assertEqual({row["area"] for row in snapshot["capabilities"]}, set(AREAS))
        self.assertEqual({row["project"] for row in snapshot["capabilities"]},
                         {project["slug"] for project in self.catalog.projects()})
        self.assertTrue(all(row["state"] == "pending" for row in snapshot["sources"]))
        destination = export(self.catalog, self.path / "site")
        published = json.loads((destination / "data" / "ecosystem.json").read_text(encoding="utf-8"))
        tool = PortBridgeMCP(self.catalog).run_tool({"name": "portbridge_ecosystem"})
        self.assertEqual(published, snapshot)
        self.assertEqual(tool["structuredContent"]["capabilities"], snapshot["capabilities"])
