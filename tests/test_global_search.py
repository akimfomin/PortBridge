import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from portbridge.github import Unavailable
from portbridge.global_search import external_search, search_terms


class GlobalSearchTests(unittest.TestCase):
    def test_scope_is_public_read_only_and_candidates_stay_tentative(self):
        origin = "https://github.com/example/renderer/pull/1"
        useful = "https://github.com/llvm/llvm-project/issues/2"
        response = {"items": [
            {"html_url": origin, "title": "Known", "state": "open"},
            {"html_url": useful, "title": "Temporary scratch storage", "state": "closed", "body": "Hidden raw body"},
            {"html_url": useful, "title": "Duplicate", "state": "closed"},
            {"html_url": "https://github.com@evil.invalid/llvm/pull/9", "title": "Spoof", "state": "open"},
        ], "incomplete_results": True}
        with patch("portbridge.global_search._Sync") as transport:
            transport.return_value._request.return_value = (response, {})
            result = external_search("DXIL scratch memory private-project-key", excluded=[origin])
        self.assertEqual(result["state"], "partial")
        self.assertEqual([row["url"] for row in result["matches"]], [useful])
        self.assertEqual(result["matches"][0]["match_level"], "candidate")
        self.assertNotIn("body", result["matches"][0])
        self.assertTrue(transport.call_args.kwargs["anonymous"])
        request = transport.return_value._request.call_args.args
        endpoint = urlsplit(request[0])
        self.assertEqual((endpoint.netloc, endpoint.path), ("api.github.com", "/search/issues"))
        self.assertEqual(parse_qs(endpoint.query)["q"], ['"dxil" "scratch memory" in:title,body'])
        self.assertEqual(request[1:], ("search", None))
        self.assertNotIn("private", request[0])

    def test_zero_terms_and_failures_have_distinct_states(self):
        with patch("portbridge.global_search._Sync") as transport:
            self.assertEqual(external_search("PB-0001")["state"], "query_needed")
            transport.assert_not_called()
            transport.return_value._request.side_effect = Unavailable("rate limited")
            self.assertEqual(external_search("Vulkan semaphore")["state"], "unavailable")
        self.assertEqual(search_terms("vkCmdPipelineBarrier WINE D3D12"), ["vkcmdpipelinebarrier", "d3d12", "wine"])

    def test_title_phrase_priority_requires_whole_words_and_keeps_github_order_for_weak_matches(self):
        titles = [
            "Vulkan driver setup",
            "Debug timeline-semaphore behavior",
            "Vulkan timeline_semaphores2 counter",
            "Measure Vulkan timeline semaphores on split queues",
            "Report Vulkan timeline semaphore waits",
        ]
        items = [{"html_url": f"https://github.com/example/renderer/issues/{index + 1}",
                  "title": title, "state": "open", "body": "Vulkan timeline semaphore"}
                 for index, title in enumerate(titles)]
        with patch("portbridge.global_search._Sync") as transport:
            transport.return_value._request.return_value = ({"items": items}, {})
            result = external_search("VULKAN timeline-semaphores a private issue summary")
        self.assertEqual(result["terms"], ["vulkan", "timeline semaphore"])
        self.assertEqual([row["title"] for row in result["matches"]],
                         [titles[index] for index in (3, 4, 1, 0, 2)])
        self.assertEqual(search_terms("D3D12 Enhanced Barrier"), ["d3d12", "enhanced barriers"])

    def test_field_queries_keep_barrier_and_texture_terms(self):
        self.assertEqual(search_terms("Vulkan image layout barrier coalescing"),
                         ["vulkan", "image layout", "barrier coalescing"])
        self.assertEqual(search_terms("gfx10 texture detile BC7 local ticket secret"),
                         ["gfx10", "detile", "bc7"])

    def test_frozen_public_github_sample(self):
        fixture = Path(__file__).with_name("fixtures") / "global-search-holdout.json"
        frozen = json.loads(fixture.read_text(encoding="utf-8"))
        expected_top_three = {
            "vulkan scratch buffer": (2, 3),
            "d3d12 pipeline cache": (3, 3),
            "shader compiler register allocation": (1, 1),
            "d3d12 memory aliasing": (3, 3),
            "vulkan timeline semaphore": (0, 3),
            "d3d12 enhanced barriers": (0, 3),
            "vkCmdPipelineBarrier2": (3, 3),
        }
        self.assertEqual(frozen["queries"].keys(), expected_top_three.keys())
        for query, captures in frozen["queries"].items():
            with self.subTest(query=query):
                baseline = captures["baseline"]["items"]
                selected = captures.get("expanded", captures["baseline"])
                with patch("portbridge.global_search._Sync") as transport:
                    request = transport.return_value._request
                    request.return_value = ({"items": selected["items"]}, {})
                    matches = external_search(query)["matches"]

                request.assert_called_once()
                endpoint = urlsplit(request.call_args.args[0])
                self.assertEqual(parse_qs(endpoint.query),
                                 {"q": [selected["github_query"]], "per_page": [str(frozen["per_page"])]})
                selected_grades = {row["html_url"]: row["grade"] for row in selected["items"]}
                urls = [row["url"] for row in matches]
                direct_before = sum(row["grade"] == 2 for row in baseline[:3])
                direct_after = sum(selected_grades[url] == 2 for url in urls[:3])
                self.assertEqual((direct_before, direct_after), expected_top_three[query])
                self.assertCountEqual(urls, selected_grades.keys())
                self.assertTrue(all(row["match_level"] == "candidate" and "grade" not in row for row in matches))
                if query == "vkCmdPipelineBarrier2":
                    self.assertEqual(urls, [row["html_url"] for row in baseline])
