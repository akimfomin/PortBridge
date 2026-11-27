"""Scheduling checks use the same durable SQLite rows as the cloud worker."""

from datetime import datetime, timezone
import sqlite3
import unittest

from portbridge import discovery_queue
from portbridge.discovery_scan import SCHEMA, project_priority

NOW = 1795773600


class DiscoveryQueueTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA + discovery_queue.SCHEMA)

    def jobs(self, rows, now):
        current = {url: (None, query, priority) for url, query, priority, _ in self.db.execute(
            "SELECT url, query, priority, queued FROM discovery_jobs")}
        current.update({url: (None, query, priority) for url, query, priority in rows})
        discovery_queue.schedule(self.db, current, now)

    def cache(self, query):
        self.db.execute("INSERT INTO discovery_query VALUES(?,?,?,?,?)",
                        (query, NOW - 1, NOW + 500, "available", "[]"))

    def test_selects_oldest_and_recent_distinct_topics_then_shares_results(self):
        older = [(f"old-{i:02}", f"topic-{i}", 0) for i in range(11)]
        self.jobs(older, NOW - 3600)
        self.jobs([("cache", "cached", 0), ("recent-a", "recent-topic-a", NOW - 10),
                   ("recent-b", "recent-topic-b", NOW - 20), ("recent-b-sibling", "recent-topic-b", NOW - 30)], NOW)
        self.cache("cached")
        rows = discovery_queue.ready(self.db, NOW, max_lookups=3)
        self.assertEqual([row[0] for row in rows], ["cache", "old-00", "recent-a", "recent-b", "recent-b-sibling"])
        self.assertEqual(discovery_queue.metrics(self.db, NOW), {
            "ready_origins": 15, "ready_topics": 14, "remote_topics": 13, "cache_ready_origins": 1,
            "fresh_leading_origins": 3, "fresh_leading_remote_topics": 2,
            "oldest_ready_seconds": 3600, "oldest_remote_ready_seconds": 3600,
        })
        self.assertEqual([row[0] for row in discovery_queue.ready(self.db, NOW, max_lookups=1)], ["cache", "old-00"])

    def test_large_cached_fan_out_leaves_room_for_both_remote_lanes(self):
        self.jobs([("old", "historical", 0)], NOW - 120)
        self.jobs([("fresh", "recent", NOW - 1)] + [(f"hit-{i:03}", "cached", 0) for i in range(140)], NOW)
        self.cache("cached")
        rows = discovery_queue.ready(self.db, NOW, max_lookups=2)
        self.assertEqual(len(rows), discovery_queue.LOCAL_BATCH)
        self.assertEqual([row[0] for row in rows[-2:]], ["old", "fresh"])

    def test_recent_priority_comes_from_source_update(self):
        lead = "https://github.com/TaynanGT/Vice-Tay/pull/1"
        other = "https://github.com/example/project/pull/1"
        def stamp(time):
            return datetime.fromtimestamp(time, timezone.utc).isoformat()

        self.assertEqual(project_priority(lead, stamp(NOW - 300), NOW), NOW - 300)
        self.assertEqual(project_priority(lead, stamp(NOW - 86401), NOW), 1)
        self.assertEqual(project_priority(lead, stamp(NOW + 1), NOW), 1)
        self.assertEqual(project_priority(other, stamp(NOW - 300), NOW), 0)
