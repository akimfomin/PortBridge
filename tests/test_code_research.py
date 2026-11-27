from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from portbridge import code_research


class CodeResearchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "research.sqlite3"
        self.group = {"repo": "example/validator", "revision": "1" * 40, "license": "MIT",
                      "license_path": "LICENSE", "directories": ["test"]}
        self.diagnostic = "VUID-StandaloneSpirv-OpExample-12345"
        self.content = f'EXPECT_THAT(error, AnyVUID("{self.diagnostic}"));\n'.encode()
        self.patcher = patch.object(code_research, "scopes", return_value=[self.group])
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def tree(self, group):
        blob = hashlib.sha1(b"blob " + str(len(self.content)).encode() + b"\0" + self.content).hexdigest()
        return {"truncated": False, "tree": [
            {"path": "test/validator.cpp", "type": "blob", "mode": "100644", "sha": blob,
             "size": len(self.content)},
            {"path": "private/secret.cpp", "type": "blob", "mode": "100644", "sha": blob,
             "size": len(self.content)},
        ]}

    def test_single_exact_diagnostic_finds_test_without_fuzzy_fallback(self):
        paths = []

        def fetch(row):
            paths.append(row["path"])
            if len(paths) == 1:
                raise URLError("transient")
            return self.content

        with patch.object(code_research, "sleep"):
            result = code_research.refresh(self.path, tree_fetch=self.tree, fetch=fetch)
        self.assertEqual(result, {"indexed": 1, "expected": 1, "cached": 0, "errors": []})
        self.assertEqual(paths, ["test/validator.cpp", "test/validator.cpp"])
        origin = "https://github.com/receiver/backend/issues/1"
        matches = code_research.lookup(self.path, self.diagnostic, origin_url=origin)
        self.assertEqual([(x["path"], x["line"]) for x in matches], [("test/validator.cpp", 1)])
        self.assertFalse(code_research.lookup(self.path, self.diagnostic,
                                              origin_url="https://github.com/example/validator/issues/1"))
        self.assertFalse(code_research.lookup(self.path, "Generic shader regression", origin_url=origin))

        def unexpected(*args):
            self.fail("Warm refresh of immutable pins tried to use the network")

        self.assertEqual(code_research.refresh(self.path, tree_fetch=unexpected, fetch=unexpected)["cached"], 1)

    def test_incomplete_refresh_keeps_previous_generation_and_rejects_other_databases(self):
        code_research.refresh(self.path, tree_fetch=self.tree, fetch=lambda _: self.content)
        origin = "https://github.com/receiver/backend/issues/1"
        with patch.object(code_research.code_search, "CACHE_PREFIX", "parser-changed:"):
            with self.assertRaisesRegex(ValueError, "Refresh"):
                code_research.lookup(self.path, self.diagnostic, origin_url=origin)
            result = code_research.refresh(self.path, tree_fetch=self.tree, fetch=lambda _: b"corrupted")
            self.assertEqual(result["indexed"], 0)
            self.assertEqual(len(result["errors"]), 1)
        self.assertTrue(code_research.lookup(self.path, self.diagnostic, origin_url=origin))

        catalog = self.path.with_name("catalog.sqlite3")
        with closing(sqlite3.connect(catalog)) as db, db:
            db.execute("CREATE TABLE settings (key TEXT)")
        with self.assertRaisesRegex(ValueError, "dedicated"):
            code_research.refresh(catalog, tree_fetch=self.tree, fetch=lambda _: self.content)
