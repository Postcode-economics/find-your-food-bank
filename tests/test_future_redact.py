"""Old phone and address text is dropped after 90 days. The label stays."""
import os, sys, json, tempfile, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import entry_history as E
from test_learning_guards import assert_schedule_and_guards

class Redact(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
    def test_old_values_go_and_the_label_stays(self):
        hist = {"a": [
            {"id": "a", "when": "2026-07-01T00:00:00+00:00", "change": "phone", "label": "website/feed update", "old": "01000000000", "new": "01000000001"},
            {"id": "a", "when": "2026-10-20T00:00:00+00:00", "change": "address", "label": "website/feed update", "old": "1 Road", "new": "2 Road"},
        ]}
        E.redact(hist, "2026-10-26")
        self.assertNotIn("old", hist["a"][0]); self.assertNotIn("new", hist["a"][0])
        self.assertEqual(hist["a"][0]["label"], "website/feed update")
        self.assertEqual(hist["a"][0]["change"], "phone")
        self.assertEqual(hist["a"][1]["new"], "2 Road")
    def test_update_redacts_a_stale_row_and_keeps_a_new_phone(self):
        d = tempfile.mkdtemp(); P = lambda n: os.path.join(d, n)
        open(P("d.js"), "w").write("var D=" + json.dumps({"items": [{"id": "b", "name": "B", "phone": "01000000000"}]}) + ";")
        E.update(P("d.js"), P("s.json"), P("h.json"), P("missing.json"), when="2026-10-01T00:00:00+00:00")
        json.dump({"b": [{"id": "b", "when": "2026-07-01T00:00:00+00:00", "change": "phone", "label": "website/feed update", "old": "01000000009", "new": "01000000008"}]}, open(P("h.json"), "w"))
        open(P("d.js"), "w").write("var D=" + json.dumps({"items": [{"id": "b", "name": "B", "phone": "01000000001"}]}) + ";")
        E.update(P("d.js"), P("s.json"), P("h.json"), P("missing.json"), when="2026-10-26T00:00:00+00:00")
        rows = json.load(open(P("h.json")))["b"]
        old = [c for c in rows if c["when"].startswith("2026-07-01")][0]
        new = [c for c in rows if c["when"].startswith("2026-10-26")][0]
        self.assertNotIn("old", old); self.assertEqual(old["label"], "website/feed update")
        self.assertEqual(new["new"], "01000000001")

if __name__ == "__main__":
    unittest.main()
