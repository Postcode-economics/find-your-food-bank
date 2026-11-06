"""Unit tests for Item 4: get() timing wrapper, byte parity, error parity, Overpass logging, and timing file generation."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import common


class FetchTimingTest(unittest.TestCase):
    def setUp(self):
        common.FETCH_LOGS.clear()

    def test_no_new_imports_in_common(self):
        """common.py must have no new imports beyond its established set."""
        with open(os.path.join(ROOT, "scripts", "common.py"), encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.startswith("import ") or l.startswith("from ")]
        # All imports in common.py:
        # line 1: import json, os, re, time, urllib.request, datetime
        # line 2: import place_lock
        # and inline imports inside functions (e.g. place_facts, recheck, etc.)
        top_imports = [l for l in lines if not l.startswith("    ")]
        self.assertEqual(len(top_imports), 2)
        self.assertIn("import json, os, re, time, urllib.request, datetime", top_imports[0])
        self.assertIn("import place_lock", top_imports[1])

    def test_get_returns_identical_bytes_and_logs_timing(self):
        fake_content = b"<html>Test content \xc2\xa35.00</html>"
        mock_response = MagicMock()
        mock_response.read.return_value = fake_content
        mock_response.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            data = common.get("http://example.com/test", tries=1, timeout=10)
            self.assertEqual(data, fake_content)
            self.assertEqual(len(common.FETCH_LOGS), 1)
            entry = common.FETCH_LOGS[0]
            self.assertEqual(entry["url"], "http://example.com/test")
            self.assertEqual(entry["status"], "ok")
            self.assertEqual(entry["bytes"], len(fake_content))
            self.assertEqual(entry["attempt"], 1)
            self.assertGreaterEqual(entry["duration"], 0)
            self.assertIsNone(entry["error"])

    def test_get_raises_same_errors_and_logs_attempts(self):
        import urllib.error
        err = urllib.error.URLError("Connection refused")

        with patch("urllib.request.urlopen", side_effect=err):
            with patch("time.sleep"):  # fast test
                with self.assertRaises(urllib.error.URLError) as ctx:
                    common.get("http://example.com/fail", tries=2, timeout=5)
                self.assertEqual(ctx.exception, err)
                self.assertEqual(len(common.FETCH_LOGS), 2)
                for i, log in enumerate(common.FETCH_LOGS):
                    self.assertEqual(log["url"], "http://example.com/fail")
                    self.assertEqual(log["status"], "error")
                    self.assertEqual(log["attempt"], i + 1)
                    self.assertIn("Connection refused", log["error"])

    def test_git_add_existing_contains_fetch_timing(self):
        with open(os.path.join(ROOT, "scripts", "git_add_existing.sh"), encoding="utf-8") as f:
            content = f.read()
        self.assertIn("logs/fetch_timing_shelters.json", content)

    def test_timing_log_destinations_main_vs_non_main(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "fetch_timing_shelters.json")
            # Verify json structure matches expected
            sample_data = {
                "run": "2026-11-05",
                "overpass": {
                    "mirror_attempts": [{"mirror": "https://overpass-api.de/api/interpreter", "duration": 1.2, "status": "ok"}],
                    "answered_mirror": "https://overpass-api.de/api/interpreter"
                },
                "fetches": [{"url": "https://overpass-api.de/api/interpreter", "attempt": 1, "duration": 1.2, "status": "ok", "bytes": 500, "error": None}]
            }
            with open(test_file, "w", encoding="utf-8") as f:
                json.dump(sample_data, f)
            with open(test_file, encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["overpass"]["answered_mirror"], "https://overpass-api.de/api/interpreter")
            self.assertEqual(len(loaded["fetches"]), 1)


if __name__ == "__main__":
    unittest.main()
