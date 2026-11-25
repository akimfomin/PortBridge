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
