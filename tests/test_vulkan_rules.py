from unittest import TestCase

from portbridge import code_search, vulkan_rules


class VulkanSharedRuleTests(TestCase):
    def test_shared_rule_matches_only_its_documented_callers(self):
        common = "chapters/commonvalidity/shared.adoc"
        bridge = "chapters/commonvalidity/bridge.adoc"
        main = "chapters/synchronization.adoc"
        root = {"repo": vulkan_rules.REPO, "revision": "a" * 40, "license": "CC-BY-4.0",
                "license_url": "https://github.com/" + vulkan_rules.REPO + "/blob/" + "a" * 40 + "/LICENSE.adoc"}
        texts = {
            common: (b"  * [[VUID-{refpage}-oldLayout-01197]]\n    Check the current layout.\n"
                     b"include::{chapters}/commonvalidity/bridge.adoc[]"),
            bridge: b"include::{chapters}/commonvalidity/shared.adoc[]",
            main: (b"[open,refpage='VkImageMemoryBarrier',type='structs']\n"
                   b"--\n:refpage: VkImageMemoryBarrier\n"
                   b"include::{chapters}/commonvalidity/bridge.adoc[]\n--\n\n"
                   b"[open,refpage='VkMemoryBarrier',type='structs']\n--\n:refpage: VkDifferentBarrier\n"
                   b"include::{chapters}/commonvalidity/shared.adoc[]\n--"),
        }
        rows = []
        for path, body in texts.items():
            row = code_search.index_file({**root, "path": path}, body)
            row["_vulkan_rules"] = vulkan_rules.extract(body)
            rows.append(row)
        vulkan_rules.resolve(rows)
        index = {"version": code_search.SCHEMA_VERSION, "files": rows}
        hits = code_search.lookup(index, "VUID-VkImageMemoryBarrier-oldLayout-01197")
        self.assertEqual(len(hits), 1)
        self.assertEqual((hits[0]["path"], hits[0]["line"], hits[0]["source_role"]),
                         (common, 1, "normative_rule"))
        self.assertTrue(hits[0]["context_url"].endswith(f"{main}#L4"))
        self.assertEqual(hits[0]["rule_id"], "VUID-VkImageMemoryBarrier-oldLayout-01197")
        self.assertFalse(code_search.lookup(index, "VUID-VkMemoryBarrier-oldLayout-01197"))
        self.assertFalse(any("_vulkan_rules" in row for row in rows))
