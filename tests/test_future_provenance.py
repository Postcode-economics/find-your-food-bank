"""An automatic edit keeps a log line. The log cannot allow a change the rules refuse."""
import os, sys, json, unittest, tempfile
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, full_check as F, auto_rules
from test_learning_guards import assert_schedule_and_guards

class Provenance(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        rules = json.load(open(os.path.join(R, "overrides", "auto_apply_rules.json"), encoding="utf-8"))
        self.assertFalse(rules["remove_confirmed_closures"])
        self.assertNotIn("remove_place", rules["automatic"])
    def test_the_log_cannot_grant_a_change(self):
        rules = auto_rules.load()
        for kind in rules["automatic"]:
            row = learning.provenance(kind, None, "https://example.test/page", rules)
            self.assertEqual(row["rule"], kind)
            self.assertFalse(row["decides"])
            self.assertIsNone(row["confidence"])
            self.assertNotIn("html", row)
        low = learning.provenance("opening times", 0.5, "https://example.test/page", rules)
        self.assertIsNone(low)
        ok = learning.provenance("opening times", 0.8, "https://example.test/page", rules)
        self.assertFalse(ok["decides"])
        self.assertIsNone(learning.provenance("remove_place", 1, "https://example.test/page", rules))
        self.assertIsNone(learning.provenance("new_place", 1, "https://example.test/page", rules))
        self.assertIsNone(learning.provenance("voucher/walk-in flips", 0.0, "https://example.test/page", rules))
    def test_an_applied_phone_is_logged_and_a_held_one_is_not(self):
        clear, held = "https://clear.example/home", "https://held.example/home"
        items = [
            dict(id="c", type="foodbank", name="Clear", foodbank="Clear", website=clear, phone="01000000000", tel="01000000000"),
            dict(id="h", type="foodbank", name="Held", foodbank="Held", website=held, phone="01000000000", tel="01000000000"),
        ]
        phone = ["02000000000"]
        store = {"full_check_state.json": {"sites": {
            clear: {"phones": phone, "checked_at": "x", "access": "unclear"},
            held: {"phones": phone, "checked_at": "x", "access": "unclear"},
        }, "ids": ["c", "h"]}}
        written = {}; rep = tempfile.mkdtemp()
        import learning_signals
        sig = {"conflicts": [{"website": held}]}
        os.makedirs(os.path.join(rep, "reports"))
        # learning_signals.rj joins ROOT; point it at a dir whose reports file names the conflict
        root = tempfile.mkdtemp(); os.makedirs(os.path.join(root, "reports"))
        json.dump(sig, open(os.path.join(root, "reports", "learning_signals.json"), "w"))
        orig = (F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site, learning_signals.ROOT)
        F.rj = lambda n, d: store.get(n, d); F.wj = lambda n, o: written.__setitem__(n, o)
        F.load_data = lambda: ("x=", {"items": items}); F.load_access = lambda: {}
        F.write_md = lambda *a: None; F.REP = rep
        def fake(u):
            return dict(url=u, ok=True, final_url=u + "/contact", access="unclear", hours_hash="h", hours_sample=["Mon 9-5"],
                        seasonal=None, closed=None, perm_closed=None, phones=phone, tel=phone, needs=None, checked_at="y", http=200)
        F.check_site = fake; learning_signals.ROOT = root
        os.environ["DRY_RUN"] = "1"
        try: F.main()
        finally:
            F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site, learning_signals.ROOT = orig
            os.environ.pop("DRY_RUN", None)
        self.assertEqual(items[0]["phone"], "02000000000")
        fc = open(os.path.join(R, "scripts", "full_check.py"), encoding="utf-8").read()
        # The hold that leaves a conflicted number unchanged is PR 204's. This branch only refuses to log it.
        if "allow_under_rules('clear single new phone on own site'" in fc:
            self.assertEqual(items[1]["phone"], "01000000000")
        else:
            self.assertEqual(items[1]["phone"], "02000000000")
        rows = written["provenance.json"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rule"], "clear single new phone on own site")
        self.assertFalse(rows[0]["decides"])
        self.assertEqual(rows[0]["source"], clear + "/contact")
        self.assertNotIn("html", rows[0])
        self.assertNotIn("remove_place", json.dumps(rows))

if __name__ == "__main__":
    unittest.main()
