from io import BytesIO
import unittest
from unittest.mock import patch

from portbridge.github import _technical
from portbridge.preflight import assess, preflight, public_preflight, snapshot
from test_portbridge import CatalogFixture


class PublicSnapshotTest(unittest.TestCase):
    def test_observations_have_a_larger_but_bounded_download(self):
        at_limit = b'{"observations":[]}'.ljust(32)
        with patch("portbridge.preflight.SNAPSHOT_LIMIT", 16), \
                patch("portbridge.preflight.OBSERVATIONS_SNAPSHOT_LIMIT", 32), \
                patch("portbridge.preflight.build_opener") as opener:
            opener.return_value.open.side_effect = [
                BytesIO(at_limit), BytesIO(at_limit + b" "), BytesIO(at_limit),
            ]
            self.assertEqual(snapshot("observations"), {"observations": []})
            with self.assertRaisesRegex(ValueError, "size limit"):
                snapshot("observations")
            with self.assertRaisesRegex(ValueError, "size limit"):
                snapshot("health")

class PreflightTest(CatalogFixture):
    def test_xcl_repo_move_keeps_exact_link_and_scope(self):
        legacy = "https://github.com/ivall/xcl/pull/1100"
        current = "https://github.com/xcl-dev/xcl/pull/1100"
        self.catalog.record_sync({"items": [self.observation("xcl", "pr", 1100, "Check FMA modifiers", current, {})]})
        result = preflight(self.catalog, url=current)
        self.assertEqual(preflight(self.catalog, url=legacy), result)
        self.assertTrue(result["indexed"])
        self.assertEqual(result["problems"][0]["id"], "PB-0006")

    def test_one_url_returns_provenance_and_backend_limits(self):
        url = "https://github.com/ubiquitarianism/leonida/pull/207"
        report = preflight(self.catalog, url=url)
        case = report["problems"][0]
        comparison = next(row for row in case["solutions"] if row["project"] == "victory")
        self.assertEqual(case["id"], "PB-0001")
        self.assertEqual(comparison["applicability"], "test_reference_across_stacks")
        self.assertEqual(report["first_check"]["project"], "victory")
        self.assertIn("7120734503", report["first_check"]["url"])
        self.assertEqual(report["first_check"]["revision"], "cee702eb4797a2288a2519b4cbda61720cfb7db4")
        self.assertIn("Windows 11", report["first_check"]["platforms"])
        self.assertIn("64", report["first_check"]["observed"])

    def test_weak_overlap_does_not_offer_an_unrelated_test(self):
        url = "https://github.com/Marvisak/VIctory/pull/641"
        self.catalog.record_sync({"items": [
            self.observation("victory", "pr", 641, "GPU: upload partially-resident streamed textures", url,
                             {"technical": {"terms": ["d3d12"]}}),
        ]})
        report = preflight(self.catalog, q="GPU d3d12 streamed textures", url=url)
        self.assertIsNone(report["first_check"])
        self.assertTrue(all(card["match_level"] == "candidate" for card in report["problems"]))

    def test_id_and_issue_number_resolve_exactly_and_keep_ambiguity(self):
        items = [self.observation(project, "pr", 772, "Different topic", url, {})
                 for project, url in (("xcl", "https://github.com/ivall/xcl/pull/772"),
                                      ("victory", "https://github.com/Marvisak/VIctory/pull/772"))]
        self.catalog.record_sync({"items": items})
        self.assertEqual(preflight(self.catalog, q="PB-00010")["problems"], [])
        result = preflight(self.catalog, q="#772")
        self.assertEqual({row["url"] for row in result["observations"]}, {row["url"] for row in items})
        self.assertIsNone(result["first_check"])

    def test_instruction_names_survive_body_collection_and_match_as_whole_symbols(self):
        for name in ("ds_bpermute_b32", "ds_read_b64"):
            with self.subTest(opcode=name):
                left = self.observation("xcl", "issue", 10, f"Recompiler: {name} differs by host",
                                        "https://github.com/ivall/xcl/issues/10", {})
                right = self.observation("victory", "pr", 30, "Preserve LDS lanes in console flow",
                                         "https://github.com/Marvisak/VIctory/pull/30",
                                         {"technical": _technical({"body": f"Checked `{name.upper()}`."}, [], {})})
                result = assess([], self.catalog.projects(), [left, right], {}, url=left["url"])
                self.assertEqual(result["matches"][0]["basis"], "technical_signal")
                self.assertIn(name, result["matches"][0]["reason"])

    def test_grouped_lds_variants_are_a_comparison_with_scope(self):
        left_url = "https://github.com/Marvisak/VIctory/pull/571"
        right_url = "https://github.com/ivall/xcl/pull/544"
        left = _technical({"body": "Handle `ds_read_{u8,i8,u16,i16}` and `ds_write_{b8,b16}`."}, [], {})
        right = _technical({"body": "Checked `DS_READ_U8/I8/U16_D16/_HI` and `DS_WRITE_B8_D16_HI`."}, [], {})
        self.assertIn("ds_read_u8", left["signals"])
        self.assertNotIn("ds_read_u8", right["signals"])
        self.assertIn("ds_read_u16_d16_hi", right["signals"])
        records = [
            self.observation("victory", "pr", 571, "Support local data share byte operations", left_url,
                             {"technical": left}),
            self.observation("xcl", "pr", 544, "Verify sub-dword reads with a test harness", right_url,
                             {"technical": right}),
        ]
        result = assess([], self.catalog.projects(), records, {}, url=left_url)
        comparison, = result["matches"]
        self.assertEqual(comparison["right"]["url"], right_url)
        self.assertEqual(comparison["basis"], "instruction_variants")
        self.assertIsNone(result["first_check"])

    def test_generic_slot_overlap_and_runtime_wine_lead_are_suppressed(self):
        a, b = self.catalog.projects()[:2]
        first = self.observation(a["slug"], "pr", 20, "Console mesh bytes in the shader slot",
                                 f"https://github.com/{a['repo']}/pull/20")
        other = self.observation(b["slug"], "pr", 400, "Console special slot for pipeline startup",
                                 f"https://github.com/{b['repo']}/pull/400")
        ci = {**first, "title": "Wine testing: use the Linux CI subset"}
        runtime = {**other, "title": "Use a dedicated Linux queue under Wine"}
        for source, unrelated in ((first, other), (ci, runtime)):
            with self.subTest(title=source["title"]):
                result = assess([], [a, b], [source, unrelated], {}, url=source["url"])
                self.assertEqual(result["matches"], [])
                self.assertEqual(result["observations"], [])

    def test_comment_never_borrows_parent_pr_metadata(self):
        parent_url = "https://github.com/Marvisak/VIctory/pull/346"
        parent = self.observation("victory", "pr", 346, "Expand indirect rectangle-list draws", parent_url, {})
        related = self.observation("continued", "pr", 207, "Expand indirect rectangle-list draws",
                                   "https://github.com/ubiquitarianism/leonida/pull/207", {})
        explicit = self.observation("xcl", "issue", 723, "Application hangs after account screen",
                                    "https://github.com/ivall/xcl/issues/723", {})
        rows = [parent, related, explicit]
        projects = self.catalog.projects()
        self.assertTrue(assess([], projects, rows, {}, url=parent_url)["matches"])

        url = parent_url + "#issuecomment-7121170075"
        report = assess([], projects, rows, {}, url=url)
        self.assertFalse(report["indexed"])
        self.assertTrue(report["origin_url"].endswith("#issuecomment-7121170075"))
        self.assertEqual((report["matches"], report["observations"]), ([], []))
        self.assertIn("linked comment", report["next_step"])

        relevant = assess([], projects, rows, {}, url=url, q="account screen")["observations"]
        self.assertEqual([row["url"] for row in relevant], [explicit["url"]])

    def test_missing_source_is_visible_in_advice(self):
        report = preflight(self.catalog, url="https://github.com/Marvisak/VIctory/pull/99999")
        self.assertFalse(report["indexed"])
        self.assertIn("missing", report["next_step"])

    def test_translated_cards_are_searchable_and_preserve_reviewed_evidence(self):
        card = self.catalog.problem("PB-0001")
        title = "Quadrilateral topology expansion"
        card["translations"] = {"en": {"title": title}}
        candidate, = assess([card], self.catalog.projects(), [], {}, q="quadrilateral topology")["problems"]
        self.assertEqual(candidate["translations"]["en"]["title"], title)
        self.assertEqual(candidate["title"], card["title"])
        self.assertEqual(candidate["match_level"], "candidate")
        source = "https://github.com/ubiquitarianism/leonida/pull/207"
        first = assess([card], self.catalog.projects(), [], {}, url=source)["first_check"]
        self.assertIn("7120734503", first["url"])
        self.assertTrue(first["translations"]["en"]["observed"])

    def test_platform_terms_do_not_match_cross_queue_fences_to_rectangle_draws(self):
        xcl = "https://github.com/ivall/xcl/pull/795"
        rectangle = "https://github.com/Marvisak/VIctory/pull/346"
        proxy = "https://github.com/ubiquitarianism/leonida/pull/403"
        comparison = "https://github.com/ubiquitarianism/leonida/pull/432"
        platforms = ["x86_64", "proton", "wine", "vkd3d", "d3d12", "wave64"]
        records = [
            self.observation("xcl", "pr", 795, "D3D12.X: bridge Wait64BitValueX to GPU fences with exact cycle breaking",
                             xcl, {"technical": {"terms": platforms + ["deadlock"], "signals": ["id3d12commandqueue", "id3d12fence"]}}),
            self.observation("victory", "pr", 346, "GPU: expand indirect rectangle-list draws",
                             rectangle, {"technical": {"terms": platforms}}),
            self.observation("continued", "pr", 403, "Correct the command queue timestamp frequency slot",
                             proxy, {"technical": {"terms": platforms, "signals": ["id3d12commandqueue"]}}),
            self.observation("continued", "pr", 432, "Maintain a live fence value across a GPU wait",
                             comparison, {"technical": {"terms": ["d3d12", "deadlock"], "signals": ["id3d12fence"]}}),
        ]
        result = assess([], self.catalog.projects(), records, {}, url=xcl)
        self.assertEqual([row["right"]["url"] for row in result["matches"]], [comparison])
        self.assertIsNone(result["first_check"])

    def test_first_check_does_not_hide_another_projects_reference(self):
        reviews = (
            ("continued", 207, "D3D12: draw console rectangle lists and quad lists as triangles"),
            ("victory", 346, "GPU: expand indirect rectangle-list draws"),
            ("xcl", 199, "D3D12: rect lists drawn whole through a generated geometry shader"),
        )
        projects = {p["slug"]: p["repo"] for p in self.catalog.projects()}
        rows = [self.observation(project, "pr", number, title, f"https://github.com/{projects[project]}/pull/{number}")
                for project, number, title in reviews]
        self.catalog.record_sync({"items": rows})
        result = preflight(self.catalog, url=rows[0]["url"])
        self.assertIn("7120734503", result["first_check"]["url"])
        related = [row["right"]["url"] for row in result["matches"]] + [row["url"] for row in result["observations"]]
        self.assertIn(rows[2]["url"], related)
        self.assertNotIn(rows[1]["url"], related)

    def test_scoped_negative_test_can_be_a_first_check(self):
        source = "https://github.com/ubiquitarianism/leonida/pull/207"
        card = self.catalog.problem("PB-0001")
        reference = card["solutions"][1]["evidence"][0]
        reference["outcome"] = "failed"
        result = assess([card], self.catalog.projects(), [], {}, url=source)
        self.assertEqual(result["first_check"]["outcome"], "failed")
        self.assertEqual(result["first_check"]["basis"], "reviewed_test_scope")
        self.assertEqual(result["first_check"]["observed"], reference["observed"])
        self.assertIsNone(assess([card], self.catalog.projects(), [], {},
                                 url=source + "#issuecomment-7122054510")["first_check"])

    def test_copied_revision_is_one_source_even_when_titles_differ(self):
        sha = "a" * 40
        left = self.observation("continued", "pr", 772, "Enable compatibility",
                                "https://github.com/ubiquitarianism/leonida/pull/772", {"head_sha": sha})
        right = self.observation("reforge", "commit", sha, "Follow-up staged",
                                 f"https://github.com/LeonidaReforge/Leonida/commit/{sha}", {"sha": sha})
        self.catalog.record_sync({"items": [left, right]})
        report = preflight(self.catalog, q=left["url"])
        self.assertEqual([row["relationship"] for row in report["matches"]], ["same_revision"])
        self.assertEqual(report["matches"][0]["applicability"], "shared_commit_check_adoption_separately")

    def test_public_uses_same_rules_without_token_or_local_db(self):
        frozen = {"projects": {"projects": self.catalog.projects()}, "problems": {"problems": self.catalog.problems()},
                  "observations": {"observations": []}, "health": self.catalog.health()}
        with patch("portbridge.preflight.snapshot", side_effect=lambda resource, **_: frozen[resource]):
            report = public_preflight(q="#20")
        self.assertEqual(report["problems"][0]["relationship"], "source_port")
        snapshots = report["problems"][0]["solutions"][0]["evidence"]
        self.assertEqual(snapshots[0]["outcome"], "failed")
        self.assertEqual(snapshots[0]["kind"], "automated_test")

    def test_we_do_not_fetch_a_supplied_url(self):
        with self.assertRaisesRegex(ValueError, "public GitHub"):
            assess([], [], [], {}, url="https://example.com/issue/1")


if __name__ == "__main__":
    unittest.main()
