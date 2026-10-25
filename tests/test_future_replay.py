"""A check can be replayed from the extracted fields. Page text is refused."""
import os, sys, json, tempfile, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import replay
from test_learning_guards import assert_schedule_and_guards

class Replay(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        fc = open(os.path.join(R, "scripts", "full_check.py"), encoding="utf-8").read()
        self.assertIn("replay.cases_from_state", fc)
    def test_page_text_is_refused(self):
        with self.assertRaises(ValueError):
            replay.case_from({"url": "https://a.test/", "http": 200, "html": "<p>secret</p>"})
        with self.assertRaises(ValueError):
            replay.cases_from_state({"sites": {"https://a.test/": {"html": "x", "http": 200}}})
    def test_replay_sees_only_extracted_fields(self):
        seen = {}
        def decision(case):
            seen.update(case); return case.get("http") == 200 and case.get("hours_hash") == "abc"
        self.assertTrue(replay.replay(decision, {"url": "https://a.test/", "http": 200, "hours_hash": "abc", "phones": ["01000000000"], "access": "walkin", "ok": True}))
        self.assertEqual(set(seen), {"url", "http", "hours_hash", "phones", "access", "ok"})
    def test_state_becomes_cases_without_html(self):
        cases = replay.cases_from_state({"sites": {"https://a.test/": {"http": 200, "hours_hash": "abc", "phones": ["01000000000"], "fail_runs": 2, "checked_at": "2026-10-26"}}})
        self.assertEqual(cases, [{"hours_hash": "abc", "http": 200, "phones": ["01000000000"], "url": "https://a.test/"}])
        d = tempfile.mkdtemp(); path = os.path.join(d, "replay_cases.json")
        replay.write(cases, path)
        saved = json.load(open(path))
        self.assertFalse(saved["stores_html"])
        self.assertEqual(set(saved["cases"][0]), {"hours_hash", "http", "phones", "url"})

if __name__ == "__main__":
    unittest.main()
