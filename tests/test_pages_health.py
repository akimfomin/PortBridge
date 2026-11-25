from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import unittest

from portbridge.export import VERSIONED_SNAPSHOTS
from portbridge.pages_health import FILES, publication_freshness, verify_linked_snapshots, verify_publication


class PagesHealthTest(unittest.TestCase):
    def test_freshness_tracks_the_previous_published_snapshot(self):
        now = datetime(2026, 11, 25, 7, 0, tzinfo=timezone.utc)
        for timestamp, expected in (
            ("2026-11-25T05:30:01Z", "fresh"),
            ("2026-11-25T08:30:00+03:00", "stale"),
            ("2026-11-25T07:05:01Z", "unavailable"),
            ("2026-11-25T06:00:00", "unavailable"),
            ("", "unavailable"),
        ):
            with self.subTest(timestamp=timestamp):
                self.assertEqual(publication_freshness(timestamp, now)[0], expected)

    def test_public_verification_retries_until_both_files_match(self):
        answers = iter([b"old-site", OSError(), b"site", b"lab"])
        delayed = []

        def request(_name):
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return BytesIO(answer)

        hashes = {name: sha256(name.encode()).hexdigest() for name in FILES}
        self.assertEqual(verify_publication(hashes, request=request, pause=delayed.append), ())
        self.assertEqual(delayed, [2])

    def test_public_verification_identifies_a_stale_lab_snapshot(self):
        def request(name):
            return BytesIO(b"site" if name == "site" else b"old-lab")

        hashes = {name: sha256(name.encode()).hexdigest() for name in FILES}
        self.assertEqual(verify_publication(hashes, request=request, pause=lambda _seconds: None), ("lab",))

    def test_checks_every_immutable_view_and_the_browse_generation(self):
        generation = "b" * 24
        verified = b'{"valid": true}'
        suffix = sha256(verified).hexdigest()[:24]
        site = {"snapshots": {name: f"{name}-{suffix}.json" for name in VERSIONED_SNAPSHOTS},
                "browse_index": {"version": 1, "generation": generation}}
        data = json.dumps(site).encode()
        expected = sha256(data).hexdigest()

        def request(name):
            if name == "site":
                return BytesIO(data)
            if name == f"browse-{generation}-index":
                return BytesIO(json.dumps({"version": 1, "generation": generation,
                                           "kinds": {"matches": {}, "sources": {}}}).encode())
            return BytesIO(b"wrong" if name == f"activity-{suffix}" else verified)

        self.assertEqual(verify_linked_snapshots(expected, request), ("activity",))
