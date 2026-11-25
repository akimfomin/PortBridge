"""Read the published browsing contract against a real catalog and later observations."""

from hashlib import sha256
import json
from unittest.mock import patch

from portbridge.export import export
from portbridge.preflight_index import SHARD_FORMAT, digest
from portbridge.public_browse import BROWSE_MANIFEST, PAGE_SIZE, build_browse_files
from test_portbridge import CatalogFixture


def read(directory, file):
    return json.loads((directory / file).read_bytes())


def manifest(directory):
    return read(directory, BROWSE_MANIFEST)


def posting(directory, index, kind, key):
    hashed = digest(key)
    prefix = hashed[:2]
    if prefix not in index["kinds"][kind]["roots"]:
        return []
    while True:
        shard = read(directory, f'data/browse-{index["generation"]}-{kind}-terms-{prefix}.json')
        if shard["format"] != SHARD_FORMAT:
            raise AssertionError("invalid browse shard")
        if "entries" in shard:
            value = shard["entries"].get(key) or []
            if isinstance(value, dict):
                path = f'data/browse-{index["generation"]}-{kind}-post-{hashed}'
                return [ident for part in range(value["parts"])
                        for ident in read(directory, f"{path}-part-{part}.json")["items"]]
            return value
        child = hashed[len(prefix)]
        if child not in shard["children"]:
            return []
        prefix += child


def page(directory, index, kind, number):
    return read(directory, f'data/browse-{index["generation"]}-{kind}-page-{number}.json')["items"]


class PublicBrowseTest(CatalogFixture):
    def test_all_pairs_and_public_observations_remain_reachable_after_updates(self):
        rows = []
        for number in range(8000, 8220):
            receiver = self.observation("continued", "pr", number, f"Fixture {number}",
                                        f"https://github.com/ubiquitarianism/leonida/pull/{number}")
            sender = self.observation("xcl", "pr", number, f"Control {number}",
                                      f"https://github.com/xcl-dev/xcl/pull/{number}",
                                      {"technical": {"references": [receiver["url"]]}})
            rows += [receiver, sender]
        late = {**rows[-1], "title": "Late_marker ПРОВЕРКА"}
        rows[-1] = late
        self.catalog.record_sync({"items": rows})
        with patch.object(self.catalog, "matches", wraps=self.catalog.matches) as calculate:
            destination = export(self.catalog, self.workspace / "site")
        calculate.assert_called_once_with(limit=None)
        index = manifest(destination)
        site = read(destination, "data/site.json")
        self.assertEqual(site["browse_index"], {"version": 1, "generation": index["generation"]})
        self.assertEqual(read(destination, f'data/browse-{index["generation"]}-index.json'), index)
        self.assertEqual(index["page_size"], PAGE_SIZE)
        self.assertEqual(index["kinds"]["sources"]["total"], len(rows))
        self.assertGreater(index["kinds"]["matches"]["total"], 200)
        self.assertEqual(index["kinds"]["sources"]["counts"]["project"], {"continued": 220, "xcl": 220})
        preview = read(destination, "data/matches.json")
        self.assertEqual(preview["total"], index["kinds"]["matches"]["total"])
        self.assertEqual(len(preview["matches"]), 200)
        match_hits = posting(destination, index, "matches", "word:late_marker")
        self.assertEqual(len(match_hits), 1)
        self.assertGreaterEqual(match_hits[0], 200)
        self.assertIn(match_hits[0], posting(destination, index, "matches", "word:проверка"))
        self.assertEqual(posting(destination, index, "matches", "number:8219"), match_hits)
        self.assertIn(match_hits[0], posting(destination, index, "matches", "stage:candidate"))
        match = page(destination, index, "matches", match_hits[0] // PAGE_SIZE)[match_hits[0] % PAGE_SIZE]
        self.assertIn(late["url"], (match["left"]["url"], match["right"]["url"]))
        self.assertNotIn(match, preview["matches"])

        source_hit, = posting(destination, index, "sources", "url:https://github.com/ivall/xcl/pull/8219")
        self.assertEqual(posting(destination, index, "sources", "word:late_marker"), [source_hit])
        sources = page(destination, index, "sources", source_hit // PAGE_SIZE)
        self.assertLessEqual(len(sources), PAGE_SIZE)
        self.assertEqual(set(sources[source_hit % PAGE_SIZE]), {
            "title", "url", "project", "kind", "status", "updated_at", "fetched_at",
        })
        self.assertEqual(len(posting(destination, index, "sources", "status:open")), len(rows))
        for name, alias in site["snapshots"].items():
            data = (destination / f"data/{alias}").read_bytes()
            self.assertEqual(data, (destination / f"data/{name}.json").read_bytes())
            self.assertEqual(alias, f"{name}-{sha256(data).hexdigest()[:24]}.json")

        self.catalog.record_sync({"items": [{**late, "title": "Revised_marker", "status": "closed",
                                            "updated_at": "2026-11-24T06:00:00Z"}]})
        export(self.catalog, destination)
        changed = manifest(destination)
        self.assertNotEqual(changed["generation"], index["generation"])
        self.assertEqual(posting(destination, changed, "sources", "word:late_marker"), [])
        self.assertEqual(posting(destination, changed, "sources", "word:revised_marker"), [0])
        self.assertEqual(posting(destination, changed, "sources", "status:closed"), [0])
        self.assertEqual(read(destination, "data/site.json")["snapshots"]["projects"], site["snapshots"]["projects"])

    def test_does_not_reuse_an_output_directory_with_an_unverified_alias(self):
        destination = self.workspace / "site"
        (destination / "data").mkdir(parents=True)
        invalid = destination / f'data/projects-{"0" * 24}.json'
        invalid.write_text("keep me", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unrecognized generated file"):
            export(self.catalog, destination)
        self.assertEqual(invalid.read_text(encoding="utf-8"), "keep me")

    def test_large_posting_remains_complete_through_bounded_parts(self):
        rows = [self.observation("xcl", "pr", number, "Same term", f"https://github.com/xcl-dev/xcl/pull/{number}")
                for number in range(1, 231)]
        with patch("portbridge.public_browse.SHARD_LIMIT", 512):
            files = build_browse_files([], rows)
        parts = [body for path, body in files.items() if "-post-" in path]
        self.assertTrue(parts)
        self.assertTrue(all(len(body) <= 512 for body in parts))
        for name, value in files.items():
            path = self.workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        index = manifest(self.workspace)
        self.assertEqual(posting(self.workspace, index, "sources", "word:same"), list(range(len(rows))))
