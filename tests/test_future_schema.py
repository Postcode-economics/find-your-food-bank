"""data.full.js carries a schema version. Readers accept that version and the one before."""
import os, sys, json, tempfile, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import schema_version, compact
from test_learning_guards import assert_schedule_and_guards

class SchemaVersion(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        dec = open(os.path.join(R, "scripts", "compact.py"), encoding="utf-8").read()
        self.assertIn("window.FB_DATA={fetched:c.f,source:c.s,items:it}", dec)
        self.assertNotIn("schema_version", open(os.path.join(R, "index.html"), encoding="utf-8").read())
    def test_current_and_previous_are_accepted(self):
        self.assertTrue(schema_version.accepts(None))
        self.assertTrue(schema_version.accepts(0))
        self.assertTrue(schema_version.accepts(1))
        self.assertFalse(schema_version.accepts(2))
        self.assertFalse(schema_version.accepts("soon"))
        stamped = schema_version.stamp({"fetched": "2026-10-26", "items": [{"id": "a"}]})
        self.assertEqual(stamped["schema_version"], 1)
        self.assertEqual(stamped["items"], [{"id": "a"}])
        self.assertTrue(schema_version.accepts(stamped["schema_version"]))
    def test_a_future_version_is_not_compacted(self):
        d = tempfile.mkdtemp()
        full = os.path.join(d, "data.full.js")
        open(full, "w").write("window.FB_DATA=" + json.dumps({"schema_version": 2, "fetched": "2026-10-26", "source": "t", "items": []}) + ";")
        old_full, old_out = compact.FULL, compact.OUT
        compact.FULL = full; compact.OUT = os.path.join(d, "data.js")
        try:
            compact.main()
            self.assertFalse(os.path.exists(compact.OUT))
        finally:
            compact.FULL, compact.OUT = old_full, old_out
    def test_an_unstamped_file_still_compacts(self):
        d = tempfile.mkdtemp()
        full = os.path.join(d, "data.full.js")
        open(full, "w").write("window.FB_DATA=" + json.dumps({"fetched": "2026-10-26", "source": "t", "items": [{"id": "a", "name": "A"}]}) + ";")
        old_full, old_out = compact.FULL, compact.OUT
        compact.FULL = full; compact.OUT = os.path.join(d, "data.js")
        try:
            compact.main()
            text = open(compact.OUT, encoding="utf-8").read()
            self.assertIn("window.FB_DATA=", text)
            self.assertNotIn("schema_version", text)
        finally:
            compact.FULL, compact.OUT = old_full, old_out

if __name__ == "__main__":
    unittest.main()
