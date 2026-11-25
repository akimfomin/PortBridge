import json
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from portbridge.preflight import assess, assess_public_index, public_preflight
from portbridge.preflight_index import MANIFEST, QUERY_READS, SHARD_LIMIT, build_search_files, digest

from test_portbridge import CatalogFixture


class PublicSearchIndexTests(CatalogFixture):
    def snapshots(self, observations):
        projects, cards = self.catalog.projects(), self.catalog.problems()
        return projects, cards, build_search_files(projects, observations)

    def sample(self):
        return [
            self.observation("continued", "pr", 550, "Preserve ds_read_b64 in rectangle topology",
                             "https://github.com/ubiquitarianism/leonida/pull/550"),
            self.observation("xcl", "pr", 550, "Translate ds_read_b64 in rectangle topology",
                             "https://github.com/xcl-dev/xcl/pull/550"),
            self.observation("victory", "pr", 551, "Report a Vulkan semaphores race",
                             "https://github.com/Marvisak/VIctory/pull/551"),
        ]

    def test_export_and_public_preflight_preserve_ranked_results_without_raw_snapshot(self):
        records = self.sample()
        projects, cards, files = self.snapshots(records)
        health = self.catalog.health()
        manifest = json.loads(files[MANIFEST])
        self.assertTrue(manifest["roots"])
        self.assertEqual(files, build_search_files(projects, list(reversed(records))))

        def fetch(path, limit, *_, **__):
            self.assertLessEqual(len(files[path]), limit)
            return json.loads(files[path])

        for q, url in (("", records[0]["url"]), ("#550", ""), ("rectangle topology", ""),
                       ("", records[1]["url"] + "#issuecomment-777"), ("PB-0001", "")):
            with self.subTest(q=q, url=url):
                actual = assess_public_index(manifest, cards, projects, health, q=q, url=url, limit=5, fetch=fetch)
                architecture = actual.pop("catalog_index")
                self.assertLessEqual(architecture["shard_reads"], QUERY_READS)
                self.assertEqual(actual, assess(cards, projects, records, health, q=q, url=url))

    def test_dense_shard_splits_and_broad_queries_report_capacity_limit(self):
        base = self.sample()[0]
        records = [{**base, "url": base["url"].rsplit("/", 1)[0] + f"/{number}",
                    "title": f"Compute scheduling rectangle on adapter fleet for synthetic replay {number}"}
                   for number in range(1, 150)]
        with patch("portbridge.preflight_index.digest", side_effect=lambda key: "11" + digest(key)[2:]):
            projects, cards, files = self.snapshots(records)
            self.assertTrue(all(len(body) <= SHARD_LIMIT for body in files.values()))
            manifest = json.loads(files[MANIFEST])
            self.assertTrue(any("children" in json.loads(body) for path, body in files.items() if path != MANIFEST))
            result = assess_public_index(manifest, cards, projects, {}, q="compute scheduling", url="", limit=5,
                                         fetch=lambda path, *_: json.loads(files[path]))
            self.assertTrue(result["catalog_index"]["partial"])
            self.assertTrue(result["observations"])

    def test_stale_manifest_retries_a_single_generation_without_legacy_download(self):
        rows = self.sample()
        projects, cards, files = self.snapshots(rows)
        latest = json.loads(files[MANIFEST])
        requested = []

        def fetch(path, maximum, *_, revalidate=False):
            requested.append(path)
            if path == MANIFEST:
                return latest if revalidate else {**latest, "generation": "0" * 24}
            if path == "data/site.json":
                return {"search_index": {key: latest[key] for key in ("version", "generation")}}
            if "0" * 24 in path:
                raise HTTPError(path, 404, "Stale generation", {}, None)
            return json.loads(files[path])

        with patch("portbridge.preflight.read_public_file", side_effect=fetch), \
                patch("portbridge.preflight.snapshot") as snapshots:
            snapshots.side_effect = lambda resource, **_: {
                "projects": {"projects": projects}, "problems": {"problems": cards}, "health": {},
                "site": {"search_index": {"version": 1, "generation": "0" * 24}},
            }[resource]
            result = public_preflight(url=rows[0]["url"])
        self.assertTrue(result["indexed"])
        self.assertEqual(requested.count(MANIFEST), 2)
        self.assertEqual([call.args[0] for call in snapshots.call_args_list], ["site", "health", "problems", "projects"])

    def test_reviewed_report_holdout_resolves_exact_evidence_only(self):
        fixture = Path(__file__).with_name("fixtures") / "reviewed-report-links.json"
        for entry in json.loads(fixture.read_text(encoding="utf-8"))["cases"]:
            with self.subTest(url=entry["url"]):
                result = assess(self.catalog.problems(), self.catalog.projects(), [], {}, url=entry["url"])
                ids = [card["id"] for card in result["problems"] if card["match_level"] == "confirmed"]
                self.assertEqual(ids, [entry["expected"]] if entry["expected"] else [])
                self.assertIsNone(result["first_check"])
