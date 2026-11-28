import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

path = Path(__file__).parent / "any/PrototypeScarlett/emu/shader_cache.py"
spec = importlib.util.spec_from_file_location("shader_cache", path)
cache = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cache
spec.loader.exec_module(cache)


class PublishChecks(unittest.TestCase):
    key = "ab" + "1" * 62
    expected = b"DXBCsynthetic"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.writer = cache.ShaderCache(tmp.name, limit_bytes=4096)
        self.reader = cache.ShaderCache(tmp.name, limit_bytes=4096)
        self.out = self.writer._path(self.key)
        self.out.parent.mkdir(parents=True)
        self.replace = cache.os.replace

    def check_no_temps(self):
        self.assertEqual(list(self.out.parent.glob("*.tmp")), [])

    def test_retry_publishes_bytes_readable_by_a_fresh_instance(self):
        def replace(src, dst):
            if not self.out.exists() and spy.call_count == 1:
                raise PermissionError("synthetic sharing violation")
            return self.replace(src, dst)

        with patch.object(cache.os, "replace", side_effect=replace) as spy:
            self.writer.put(self.key, self.expected)
        self.assertEqual(spy.call_count, 2)
        self.assertEqual(self.reader.get(self.key), self.expected)
        self.check_no_temps()

    def test_identical_peer_is_a_hit(self):
        self.out.write_bytes(self.expected)
        with patch.object(cache.os, "replace", side_effect=PermissionError), patch.object(cache.time, "sleep"):
            self.writer.put(self.key, self.expected)
        self.assertEqual(self.reader.get(self.key), self.expected)
        self.check_no_temps()

    def test_different_peer_is_preserved_and_reported(self):
        peer = b"DXBCother"
        self.out.write_bytes(peer)
        with patch.object(cache.os, "replace", side_effect=PermissionError), patch.object(cache.time, "sleep"):
            with self.assertRaises(PermissionError):
                self.writer.put(self.key, self.expected)
        self.assertEqual(self.reader.get(self.key), peer)
        self.assertNotIn(self.key, self.writer.memory)
        self.check_no_temps()

    def test_sharing_failure_without_peer_does_not_publish(self):
        with patch.object(cache.os, "replace", side_effect=PermissionError), patch.object(cache.time, "sleep"):
            with self.assertRaises(PermissionError):
                self.writer.put(self.key, self.expected)
        self.assertIsNone(self.reader.get(self.key))
        self.check_no_temps()

if __name__ == "__main__":
    unittest.main(verbosity=2)
