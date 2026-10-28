"""A clear single new food-bank phone is held when the listing is frozen.

The baseline file (PR 211) locks the ids it lists. Until that file exists, every existing listing is locked.
The stored number stays, and the proposal is logged for Dean with its source.
"""
import json, os, sys, tempfile, unittest
R = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(R, "scripts"))
import full_check as F

NEW = "07700900123"
SOURCE = "https://riverside.example/contact"

def listing(iid="riverside"):
    return {"id": iid, "name": "Riverside Food Bank", "phone": "01234 567890", "tel": "01234567890"}

def baseline(root, ids):
    os.makedirs(os.path.join(root, "overrides"), exist_ok=True)
    json.dump({"listings": {i: {"layer": "foodbanks", "phone": "01234 567890"} for i in ids}},
              open(os.path.join(root, "overrides", "phone_baseline.json"), "w", encoding="utf-8"))

class PhoneBaselineHold(unittest.TestCase):
    def held(self, root, item):
        text = open(os.path.join(root, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertIn("held for Dean", text)
        self.assertIn(item["id"], text)
        self.assertIn("source " + SOURCE, text)
        brake = open(os.path.join(root, "reports", "anomaly_brake.md"), encoding="utf-8").read()
        self.assertIn("source " + SOURCE, brake)
        self.assertEqual(item["phone"], "01234 567890")
        self.assertEqual(item["tel"], "01234567890")

    def test_listing_in_the_baseline_is_held_and_not_applied(self):
        root = tempfile.mkdtemp(); item = listing()
        baseline(root, ["riverside"])
        apply_to = F.record_clear_phones([item], NEW, SOURCE, root)
        self.assertEqual(apply_to, [])
        self.held(root, item)
        fixes = {"https://x.org": dict(old=F.norm_phone(item["phone"]), new=NEW, since="2026-10-27", source=SOURCE)}
        n = F.apply_phone_fixes({"https://x.org": [item]}, fixes, lambda *a, **k: None, root)
        self.assertEqual(n, 0)
        self.assertEqual(item["phone"], "01234 567890")
        self.assertEqual(item["tel"], "01234567890")
        self.assertNotIn("phone_source", item)

    def test_missing_baseline_holds_every_existing_listing(self):
        root = tempfile.mkdtemp()
        self.assertFalse(os.path.isfile(F.phone_baseline_path(root)))
        items = [listing("riverside"), listing("hilltop")]
        items[1]["id"] = "hilltop"; items[1]["name"] = "Hilltop Pantry"
        apply_to = F.record_clear_phones(items, NEW, SOURCE, root)
        self.assertEqual(apply_to, [])
        for item in items:
            self.assertTrue(F.listing_phone_frozen(item["id"], root))
            self.held(root, item)
        fixes = {"https://x.org": dict(old=F.norm_phone(items[0]["phone"]), new=NEW, since="2026-10-27", source=SOURCE)}
        # A fix recorded before this rule still must not be invented here: the clear-phone path returned nothing to write.
        self.assertEqual(F.record_clear_phones(items, NEW, SOURCE, root), [])

    def test_id_absent_from_an_existing_baseline_is_still_not_applied(self):
        root = tempfile.mkdtemp(); item = listing("brand-new")
        baseline(root, ["riverside"])
        self.assertFalse(F.listing_phone_frozen("brand-new", root))
        apply_to = F.record_clear_phones([item], NEW, SOURCE, root)
        self.assertEqual(apply_to, [item])
        self.assertEqual(item["phone"], "01234 567890")
        self.assertEqual(item["tel"], "01234567890")
        fixes = {"https://x.org": dict(old=F.norm_phone(item["phone"]), new=NEW, since="2026-10-27", source=SOURCE)}
        n = F.apply_phone_fixes({"https://x.org": [item]}, fixes, lambda *a, **k: None, root)
        self.assertEqual(n, 0)
        self.assertEqual(item["phone"], "01234 567890")
        self.assertEqual(item["tel"], "01234567890")
        self.assertNotIn("phone_source", item)
        text = open(os.path.join(root, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertIn("held for Dean", text)
        self.assertIn("brand-new", text)
        self.assertIn(NEW, text)
        self.assertIn("unchanged (byte-identical)", text)

if __name__ == "__main__": unittest.main()
