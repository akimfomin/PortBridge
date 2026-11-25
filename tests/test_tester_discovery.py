"""Exercise discovery with synthetic GitHub comment payloads and no network."""

from copy import deepcopy
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from portbridge.github import API
from portbridge.tester_discovery import (
    CONTINUED_RECT, INTEL_WAVE32, MAX_REQUESTS, PER_PAGE, REFORGE_PRESENT, THREADS,
    XCL_DISPATCH, XCL_FMA, XCL_GPU, XCL_PERMUTE, XCL_SCRATCH,
    discover_testers,
)


NOW = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
NATIVE = "d3d12-native-wave64"
RDNA4 = "d3d12-native-wave64-rdna4"
PRESENT = "win32-vulkan-1.3"
GEOMETRY = "win32-vulkan-geometry"
AMD_REPORT = """Hardware check of commit aaaaaaa.
**Tested**
- Hardware: AMD Radeon RX 9070 XT (RDNA4, driver 1.2), Windows 11.
- `gpu::recomp::tests::gpu_ds_permute_b32` (native Wave64, Wave32 and split Wave64): **passed**.
"""
ARC_SINGLE_REPORT = """**Tested**

At 3283da481077c1962f13f1b4078841662f7a4ccb, dispatch_chain_payload_skips_middle_piece ran on Intel Arc A770 (driver 32.0.101.9175) and Windows 11.

**1 passed, 0 failed, 0 ignored, 0 GPU skips**. The stock Wave32 fixture issued one whole-shader dispatch and three direct-DXIL chain dispatches.

**Not tested**

Reused-edge-slot stress.
"""
ARC_TABLE_REPORT = """# Arc dispatch-chain parity

**Tested revision**

The assigned checkout was clean at the checked revision.
The original author reported the first result.

**Tested**

- Test station, Windows 11 25H2, Intel(R) Arc(TM) B580 driver 32.0.101.9175.

| Fixture | Wave form | Output parity | Passed / failed / ignored / skips |
| dispatch_chain_wave32_live_loops | one physical Wave32 per group | 96 of 96 words matched | 1 / 0 / 0 / 0 |
"""


def comment(thread, *, login="tester-one", body=AMD_REPORT, ident=17, date="2026-11-24T09:08:40Z"):
    repo, kind, number = thread
    return {"id": ident, "url": f"{API}/repos/{repo}/issues/comments/{ident}",
            "issue_url": f"{API}/repos/{repo}/issues/{number}",
            "html_url": f"https://github.com/{repo}/{kind}/{number}#issuecomment-{ident}",
            "created_at": date, "body": body,
            "user": {"type": "User", "login": login, "html_url": f"https://github.com/{login}"}}


class DiscoveryTests(unittest.TestCase):
    def discover(self, equipment, capability, batches, *, for_review=False):
        requested = []
        def public_get(path):
            requested.append(path)
            for (repo, _, number), rows in batches.items():
                if urlsplit(path).path == f"/repos/{repo}/issues/{number}/comments":
                    return rows, 1
            return [], 1
        return discover_testers(equipment, capability, for_review=for_review, public_get=public_get, now=NOW), requested

    def test_intel_wave32_reports_are_available_only_for_human_review(self):
        single = comment(XCL_SCRATCH, body=ARC_SINGLE_REPORT)
        table = comment(XCL_DISPATCH, login="tester-two", body=ARC_TABLE_REPORT, ident=18)
        batches = {XCL_DISPATCH: [table], XCL_SCRATCH: [single]}
        candidates, paths = self.discover("intel", INTEL_WAVE32, batches, for_review=True)
        self.assertEqual({(row["login"], row["hardware"]) for row in candidates},
                         {("tester-one", "Intel Arc A770"), ("tester-two", "Intel Arc B580")})
        self.assertEqual(candidates[0]["capabilities"], [INTEL_WAVE32])
        self.assertEqual({row["evidence_url"] for row in candidates}, {single["html_url"], table["html_url"]})
        self.assertTrue(all("opt_in" not in row and "body" not in row for row in candidates))
        self.assertEqual(len(paths), 2)
        self.assertEqual(self.discover("intel", (), batches), ([], []))

    def test_intel_reports_need_a_physical_windows_run_with_an_exact_positive_case(self):
        variants = (
            ARC_SINGLE_REPORT.replace("Intel Arc A770", "Intel Arc Graphics"),
            ARC_SINGLE_REPORT.replace("Intel Arc A770", "Intel Arc A770 and NVIDIA RTX 5090"),
            ARC_SINGLE_REPORT.replace("Windows 11", "Linux through Proton on Windows 11"),
            ARC_SINGLE_REPORT.replace("0 GPU skips", "1 GPU skip"),
            ARC_SINGLE_REPORT.replace("ran on", "would run on"),
            ARC_SINGLE_REPORT.replace("Wave32 fixture issued", "Wave32 support is possible"),
            ARC_SINGLE_REPORT.replace("dispatch_chain_payload_skips_middle_piece", "unrelated_test"),
            "\n".join(f"> {line}" for line in ARC_SINGLE_REPORT.splitlines()),
        )
        for body in variants:
            with self.subTest(body=body):
                report = comment(XCL_SCRATCH, body=body)
                self.assertEqual(self.discover("intel", (), {XCL_SCRATCH: [report]}, for_review=True)[0], [])
        table_skip = comment(XCL_DISPATCH, body=ARC_TABLE_REPORT.replace("1 / 0 / 0 / 0", "1 / 0 / 0 / 1"))
        self.assertEqual(self.discover("intel", (), {XCL_DISPATCH: [table_skip]}, for_review=True)[0], [])

    def test_radeon_generation_and_scope(self):
        row = comment(XCL_PERMUTE)
        earlier = comment(XCL_PERMUTE, login="rdna2-owner", ident=18,
                          body=AMD_REPORT.replace("9070 XT (RDNA4", "6800 XT (RDNA2"))
        candidates, paths = self.discover("amd", RDNA4, {XCL_PERMUTE: [row, earlier]})
        self.assertEqual(candidates, [{"login": "tester-one", "equipment": "amd", "hardware": "AMD Radeon RX 9070 XT",
                                       "capabilities": [NATIVE, RDNA4], "evidence_url": row["html_url"],
                                       "reported_at": "2026-11-24T09:08:40Z"}])
        self.assertEqual(len(paths), len(THREADS[RDNA4]))
        generic, _ = self.discover("amd", [NATIVE], {XCL_PERMUTE: [row, earlier]})
        self.assertEqual({r["login"] for r in generic}, {"tester-one", "rdna2-owner"})
        self.assertEqual(next(r for r in generic if r["login"] == "rdna2-owner")["capabilities"], [NATIVE])

    def test_exact_native_pass_is_required(self):
        bodies = [
            AMD_REPORT.replace("**passed**", "did not pass"),
            AMD_REPORT.replace("**passed**", "would pass"),
            AMD_REPORT.replace("**passed**", "skipped; baseline passed"),
            AMD_REPORT.replace("native Wave64, Wave32 and split Wave64", "split Wave64 only"),
            AMD_REPORT.replace("Windows 11", "Linux under Wine (Windows 11 compatibility mode)"),
            AMD_REPORT.replace("gpu_ds_permute_b32", "gpu_ds_permute_b32_control"),
            AMD_REPORT.replace("gpu_ds_permute_b32", "different_test") + "\n`ds_permute_b32` passed.",
            AMD_REPORT.replace("native Wave64, Wave32 and split Wave64", "Wave32") + "\nPlease check native Wave64.",
            AMD_REPORT.replace("gpu_ds_permute_b32", "gpu_wave32_program_in_wave64_hardware")
                .replace("native Wave64, Wave32 and split Wave64", "summary only"),
            AMD_REPORT.replace("Windows 11", "Windows 11 via Wine"),
            AMD_REPORT.replace("RDNA4, driver", "RDNA4, native Wave64 support, driver")
                .replace("native Wave64, Wave32 and split Wave64", "Wave32 only"),
            AMD_REPORT + "**Not tested:** native Wave64.",
            AMD_REPORT.replace("AMD Radeon RX 9070 XT", "AMD Radeon RX 9070 XT and NVIDIA RTX 5090"),
        ]
        for bad in bodies:
            with self.subTest(body=bad):
                candidates, _ = self.discover("amd", NATIVE, {XCL_PERMUTE: [comment(XCL_PERMUTE, body=bad)]})
                self.assertEqual(candidates, [])

    def test_quotes_examples_and_not_tested_sections_do_not_count(self):
        bodies = [
            "Another report is quoted here:\n" + "\n".join("> " + line for line in AMD_REPORT.splitlines()),
            "<blockquote>\n" + AMD_REPORT + "\n</blockquote>",
            "<details>\n" + AMD_REPORT + "\n</details>",
            "Example:\n```text\n" + AMD_REPORT + "\n```",
            "**Not tested:**\n" + AMD_REPORT,
            AMD_REPORT.replace("Hardware:", "Hardware reported by another tester:"),
            AMD_REPORT.replace("**passed**", "passed in their run"),
        ]
        for body in bodies:
            with self.subTest(body=body):
                result, _ = self.discover("amd", RDNA4, {XCL_PERMUTE: [comment(XCL_PERMUTE, body=body)]})
                self.assertEqual(result, [])

    def test_github_author_and_discussion_are_bound(self):
        original = comment(XCL_PERMUTE)
        variants = []
        for field, value in (("issue_url", original["issue_url"] + "0"), ("url", original["url"] + "0"),
                             ("html_url", original["html_url"].replace("github.com", "github.com.example.net")),
                             ("minimized", True), ("created_at", "unknown")):
            variants.append({**original, field: value})
        for field, value in (("type", "Bot"), ("login", "test@groups"), ("html_url", "https://github.com/someone-else")):
            entry = deepcopy(original)
            entry["user"][field] = value
            variants.append(entry)
        result, _ = self.discover("amd", NATIVE, {XCL_PERMUTE: variants})
        self.assertEqual(result, [])

    def test_dedup_uses_newest_bound_report_without_prose(self):
        old = comment(XCL_PERMUTE, login="SameUser")
        new = comment(XCL_FMA, login="sameuser", date="2026-11-24T10:00:00+00:00", ident=22,
                      body=AMD_REPORT.replace("gpu_ds_permute_b32", "gpu_fma_f32_abs_neg_clamp_oracle"))
        result, _ = self.discover("amd", NATIVE, {XCL_PERMUTE: [old], XCL_FMA: [new]})
        self.assertEqual([row["evidence_url"] for row in result], [new["html_url"]])
        self.assertEqual(result[0]["reported_at"], "2026-11-24T10:00:00Z")
        self.assertNotIn("body", result[0])

    def test_vulkan_requires_version_windows_and_exact_present_test(self):
        body = "Machine: Windows 11, GPU NVIDIA GeForce RTX 4070 Ti SUPER, Vulkan 1.3.290.\n`vk_presenter_sync_test`: all six checks passed."
        valid = comment(REFORGE_PRESENT, body=body)
        unversioned = comment(REFORGE_PRESENT, ident=18, body=body.replace("Vulkan 1.3.290", "Vulkan"))
        unrelated = comment(REFORGE_PRESENT, ident=19, body=body.replace("vk_presenter_sync_test", "vk_queue_test"))
        result, _ = self.discover("nvidia", PRESENT, {REFORGE_PRESENT: [valid, unversioned, unrelated]})
        self.assertEqual([row["evidence_url"] for row in result], [valid["html_url"]])
        self.assertEqual(result[0]["hardware"], "NVIDIA GeForce RTX 4070 Ti SUPER")

    def test_geometry_requires_actual_rectangle_pass(self):
        body = "Setup: Windows 11, NVIDIA RTX 4060 Ti.\nThe `d3d12_rect_list` fixture passed."
        right = comment(CONTINUED_RECT, body=body)
        result, _ = self.discover("nvidia", GEOMETRY, {CONTINUED_RECT: [right]})
        self.assertEqual(result[0]["capabilities"], [GEOMETRY])

    def test_generic_nvidia_requires_direct_report_not_card_mention(self):
        body = "Hardware: NVIDIA RTX 3060 Ti, Windows 11.\nI ran cargo test --workspace: 741 passed, 0 failed, 41 ignored."
        report = comment(XCL_GPU, body=body)
        no_test = comment(XCL_GPU, ident=19, body="Could your NVIDIA RTX 3060 Ti run this on Windows 11?")
        result, paths = self.discover("nvidia", (), {XCL_GPU: [report, no_test]})
        self.assertEqual([row["evidence_url"] for row in result], [report["html_url"]])
        self.assertFalse(result[0]["capabilities"])
        self.assertLessEqual(len(paths), 6)

    def test_unavailable_sources_and_unknown_capability(self):
        def blocked(path):
            raise HTTPError(API + path, 403, "Rate limited", None, None)
        self.assertEqual(discover_testers("amd", RDNA4, public_get=blocked, now=NOW), [])
        self.assertEqual(discover_testers("nvidia", "unknown", public_get=self.fail), [])

    def test_date_filter_and_latest_page_respect_request_budget(self):
        stale = comment(XCL_PERMUTE, date="2025-11-24T09:08:40Z")
        latest = comment(XCL_PERMUTE, login="new-reporter", ident=30)
        paths = []

        def get(path):
            paths.append(path)
            query = parse_qs(urlsplit(path).query)
            self.assertEqual(query["since"], ["2026-08-26T12:00:00Z"])
            if "/925/" in path:
                if query.get("page") == ["4"]:
                    return [latest], 4
                return [stale], 4
            return [], 4

        results = discover_testers("amd", RDNA4, public_get=get, now=NOW)
        self.assertEqual([row["login"] for row in results], ["new-reporter"])
        self.assertEqual(len(paths), MAX_REQUESTS)

    def test_real_adapter_builds_only_public_gets_without_credentials(self):
        row = comment(REFORGE_PRESENT, body="Hardware: Windows 11 and RTX 4060, Vulkan 1.3.\nvk_presenter_sync_test passed.")
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.headers = {"Link": '<https://somewhere.invalid/?page=4>; rel="last"'}
        response.read.return_value = json.dumps([row]).encode()
        with patch("portbridge.tester_discovery.build_opener", return_value=opener), patch.dict(
            "os.environ", {"GITHUB_TOKEN": "must-not-leak", "PORTBRIDGE_GITHUB_TOKEN": "also-private"}
        ):
            result = discover_testers("nvidia", PRESENT, now=NOW)
        self.assertEqual(len(result), 1)
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url.split("?")[0], f"{API}/repos/LeonidaReforge/Leonida/issues/86/comments")
        self.assertEqual(parse_qs(urlsplit(request.full_url).query)["per_page"], [str(PER_PAGE)])
        self.assertNotIn("authorization", {key.lower() for key, _ in request.header_items()})


if __name__ == "__main__":
    unittest.main()
