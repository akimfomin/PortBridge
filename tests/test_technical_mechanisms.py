"""Scoped, unlinked comparisons remain hypotheses and ignore symptom-only hits."""

import unittest

from portbridge.github import _technical
from portbridge.matching import RelatedIndex, canonical_url
from portbridge.technical_mechanisms import mechanisms


def observation(project, number, title, body="", *, signals=(), old=False):
    url = f"https://github.com/{project}/runtime/pull/{number}"
    metadata = _technical({"title": title, "body": body}, [], {})
    if old:
        metadata.pop("mechanisms")
    metadata["signals"].extend(signals)
    return {"url": url, "project": project, "kind": "pr", "title": title, "metadata": {"technical": metadata}}


class TechnicalMechanismTests(unittest.TestCase):
    def test_extracts_contextual_metadata_without_raw_text_or_url_signals(self):
        body = (
            "The pipeline cache uses the driver version. The command list is removed before final release. "
            "This unrelated sentence mentions Vendor ID. "
            "https://example.org/BVH/skip-second-half"
        )
        metadata = _technical({"title": "Track cached state and lifetime", "body": body}, [], {})
        self.assertEqual(metadata["mechanisms"], [
            "command-list/final-release", "pipeline-cache/device-identity",
        ])
        self.assertNotIn("unrelated", str(metadata))
        self.assertEqual(mechanisms("Command lists are live. The image needs final release."), set())

    def test_indexes_body_and_reads_title_in_old_snapshots_without_an_external_request(self):
        source = observation("renderer", 1, "Reject pipeline cache with a different driver version", old=True)
        target = observation("compat", 2, "Check startup persistence",
                             "Saved pipeline library entries are accepted only with the original cache UUID.")
        decoy = observation("other", 3, "Pipeline cache compile fallback",
                            "A stale blob triggers a second attempt in the pipeline cache.")
        index = RelatedIndex([source, target, decoy])
        hits = list(index.candidates(canonical_url(target["url"])))
        self.assertIn((canonical_url(source["url"]), 0.92, "shared_mechanism", ["pipeline-cache/device-identity"]), hits)
        self.assertNotIn(canonical_url(decoy["url"]), [url for url, _, basis, _ in hits if basis == "shared_mechanism"])

    def test_distinguishes_shared_errors_from_a_specific_match_without_a_citation(self):
        signal = ("vk_error_device_lost",)
        origin = observation("target", 1, "Guard aliased pages instead of copying them each submission", signals=signal)
        source = observation("source", 2, "Remember unmapped guarded view blocks before re-copying them", signals=signal)
        symptom = observation("symptom", 3, "Wait on submission lock during texture upload", signals=signal)
        index = RelatedIndex([origin, source, symptom])
        hit, = index.candidates(canonical_url(origin["url"]))
        self.assertEqual(hit[0], canonical_url(source["url"]))
        self.assertEqual(hit[2], "shared_mechanism")
        self.assertEqual(set(hit[3]), {"memory-copy/mapping-change", "memory-copy/selective-refresh",
                                       "memory-copy/write-tracking"})

    def test_mechanism_candidate_does_not_turn_a_common_fingerprint_into_ancestry(self):
        origin = observation("first", 1, "Remove command list tracking before final release")
        source = observation("second", 2, "Remove command list tracking before final release")
        index = RelatedIndex([origin, source])
        matched, = index.matches({}, origin=canonical_url(origin["url"]))
        self.assertEqual(matched["state"], "suggested")
        self.assertEqual(matched["basis"], "shared_mechanism")
        source["metadata"]["head_sha"] = origin["metadata"]["head_sha"] = "a" * 40
        exact, = RelatedIndex([origin, source]).matches({}, origin=canonical_url(origin["url"]))
        self.assertEqual(exact["basis"], "shared_revision")


if __name__ == "__main__":
    unittest.main()
