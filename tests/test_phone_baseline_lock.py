"""Frozen listing numbers (Dean, 27 Oct 2026). A baselined number stays byte-identical.
A new id may take one valid first number, and the next change is held. Council lines
without a verified out-of-hours number stay hidden. Hand edits are the baseline file."""
import json, os, shutil, sys, tempfile, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import phone_lock, phone_baseline, full_check, learning

FROZEN = "023 9282 4244"  # Portsmouth homelessness emergency line, spacing included

def _tree(listings=None):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "overrides"))
    os.makedirs(os.path.join(d, "reports"))
    if listings is not None:
        phone_lock.save({"_about": "test", "listings": listings}, d)
    return d

class Lock(unittest.TestCase):
    def tearDown(self):
        if getattr(self, "d", None):
            shutil.rmtree(self.d, ignore_errors=True)

    def test_frozen_number_survives_feed_change_byte_identical(self):
        self.d = _tree({"ww-1": {"layer": "warmspaces", "phone": FROZEN, "tel": "02392824244"}})
        item = {"id": "ww-1", "name": "Lounge", "phone": "023 9282 2251", "tel": "02392822251"}
        n = phone_lock.guard([item], self.d, via="refresh", source="https://feed.example/lounge", layer="warmspaces", persist_new=True)
        self.assertGreaterEqual(n, 1)
        self.assertEqual(item["phone"], FROZEN)
        self.assertEqual(item["phone"].encode("utf-8"), FROZEN.encode("utf-8"))
        self.assertEqual(item["tel"], "02392824244")
        text = open(os.path.join(self.d, "reports", "pending_dean.md"), encoding="utf-8").read()
        brake = open(os.path.join(self.d, "reports", "anomaly_brake.md"), encoding="utf-8").read()
        for blob in (text, brake):
            self.assertIn("blocked", blob)
            self.assertIn("held for Dean", blob)
            self.assertIn(FROZEN, blob)
            self.assertIn("https://feed.example/lounge", blob)
        self.assertNotEqual(item["phone"], "023 9282 2251")

    def test_blank_feed_does_not_wipe_frozen_number(self):
        self.d = _tree({"ww-1": {"layer": "warmspaces", "phone": FROZEN}})
        item = {"id": "ww-1", "phone": "", "tel": ""}
        phone_lock.guard([item], self.d, via="refresh", source="feed refresh", layer="warmspaces")
        self.assertEqual(item["phone"], FROZEN)
        self.assertEqual(item["phone"].encode("utf-8"), FROZEN.encode("utf-8"))
        self.assertIn("held for Dean", open(os.path.join(self.d, "reports", "pending_dean.md"), encoding="utf-8").read())
        missing = {"id": "ww-1"}
        phone_lock.guard([missing], self.d, via="refresh", source="feed refresh", layer="warmspaces")
        self.assertEqual(missing["phone"], FROZEN)

    def test_new_listing_first_number_is_published_and_then_frozen(self):
        self.d = _tree({})
        item = {"id": "ww-new", "name": "New", "phone": "01234 567890"}
        self.assertFalse(phone_lock.uk_ok("12"))  # too short to publish
        bad = {"id": "ww-bad", "phone": "12"}
        phone_lock.guard([item, bad], self.d, via="refresh", source="feed refresh", layer="warmspaces", persist_new=True)
        self.assertEqual(item["phone"], "01234 567890")
        self.assertEqual(bad.get("phone"), "")
        frozen = phone_lock.frozen("ww-new", self.d)
        self.assertEqual(frozen["phone"], "01234 567890")
        self.assertIsNone(phone_lock.frozen("ww-bad", self.d))
        daily = open(os.path.join(self.d, "reports", "daily_review.md"), encoding="utf-8").read()
        self.assertIn("new listing number", daily)
        self.assertIn("ww-new", daily)
        # the next automatic change is held and the first number stays byte-identical
        item["phone"] = "09876 543210"
        phone_lock.guard([item], self.d, via="learning", source="auto-apply", layer="warmspaces", persist_new=True)
        self.assertEqual(item["phone"], "01234 567890")
        self.assertEqual(item["phone"].encode("utf-8"), b"01234 567890")
        self.assertIn("held for Dean", open(os.path.join(self.d, "reports", "anomaly_brake.md"), encoding="utf-8").read())

    def test_second_change_to_new_listing_is_held(self):
        self.d = _tree({})
        item = {"id": "fb-new", "phone": "0161 236 7537"}
        self.assertTrue(learning.try_auto_phone(item, "0161 236 7537", "https://own.example", root=self.d, via="learning"))
        self.assertEqual(phone_lock.frozen("fb-new", self.d)["phone"], "0161 236 7537")
        self.assertIn("new listing number", open(os.path.join(self.d, "reports", "daily_review.md"), encoding="utf-8").read())
        again = learning.try_auto_phone(item, "0161 000 0000", "https://own.example/2", root=self.d, via="auto-apply")
        self.assertFalse(again)
        self.assertEqual(item["phone"], "0161 236 7537")
        self.assertEqual(item["phone"].encode("utf-8"), "0161 236 7537".encode("utf-8"))
        held = open(os.path.join(self.d, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertIn("blocked", held)
        self.assertIn("held for Dean", held)
        self.assertIn("https://own.example/2", held)

    def test_council_line_follows_freeze_and_hides_until_ooh_found(self):
        daytime = {"id": "ww-day", "phone": "01234 567890", "tel": "01234567890",
                   "council": "Example Council", "council_phone": "01234 000000", "council_label": "Council main number"}
        self.assertTrue(phone_lock.settle_council(daytime))
        self.assertNotIn("council_phone", daytime)  # hidden until a verified out-of-hours number is found
        self.assertNotIn("council_label", daytime)
        self.assertEqual(daytime["phone"], "01234 567890")
        kept = {"id": "ww-ooh", "phone": "01234 567890", "council_phone": FROZEN, "council_ooh": FROZEN,
                "council_label": "Council homelessness emergency line"}
        self.assertFalse(phone_lock.settle_council(kept))
        self.assertEqual(kept["council_phone"], FROZEN)
        self.assertEqual(kept["council_ooh"].encode("utf-8"), FROZEN.encode("utf-8"))
        self.d = _tree({"ww-ooh": {"layer": "warmspaces", "phone": "01234 567890", "council_phone": FROZEN,
                                   "council_ooh": FROZEN, "council_label": "Council homelessness emergency line"}})
        kept["council_phone"] = "023 9282 2251"
        kept["council_ooh"] = "023 9282 2251"
        phone_lock.guard([kept], self.d, via="publish", source="publish gate", layer="warmspaces")
        self.assertEqual(kept["council_phone"], FROZEN)
        self.assertEqual(kept["council_ooh"], FROZEN)
        self.assertEqual(kept["council_label"], "Council homelessness emergency line")
        log = open(os.path.join(self.d, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertIn("blocked", log)
        self.assertIn("held for Dean", log)
        self.assertIn(FROZEN, log)

    def test_phone_fix_holds_baselined_listing(self):
        self.d = _tree({"x": {"layer": "foodbanks", "phone": "01234 567890", "tel": "01234567890"}})
        fixes = {"https://a.org": dict(old=full_check.norm_phone("01234 567890"), new="09876543210", since="2026-10-27", source="https://a.org/c")}
        item = dict(id="x", name="A", phone="01234 567890", tel="01234567890")
        flags = {}
        n = full_check.apply_phone_fixes({"https://a.org": [item]}, fixes, lambda k, c, **x: flags.__setitem__(c + "|" + k, x), root=self.d)
        self.assertEqual(n, 0)
        self.assertEqual(item["phone"], "01234 567890")
        self.assertEqual(item["tel"], "01234567890")
        self.assertEqual(item["phone"].encode("utf-8"), b"01234 567890")
        text = open(os.path.join(self.d, "reports", "anomaly_brake.md"), encoding="utf-8").read()
        self.assertIn("blocked", text)
        self.assertIn("held for Dean", text)
        self.assertIn("https://a.org/c", text)
        self.assertIn("phone fix", text)

    def test_change_rejected_unless_recorded_in_reviewed_baseline(self):
        diffs = phone_baseline.unreviewed(ROOT)
        self.assertEqual(diffs, [], diffs[:8])
        self.d = _tree({"ww-1": {"layer": "warmspaces", "council_phone": FROZEN, "council_ooh": FROZEN,
                                 "council_label": "Council homelessness emergency line"}})
        os.makedirs(os.path.join(self.d, "overrides"), exist_ok=True)
        for name in ("shelters_contacts.json", "warmspaces_contacts.json"):
            json.dump({}, open(os.path.join(self.d, "overrides", name), "w"))
        entry = {"council_phone": "023 9282 2251", "council_ooh": "023 9282 2251",
                 "council_label": "Council homelessness emergency line"}
        json.dump({"ww-1": entry}, open(os.path.join(self.d, "overrides", "warmspaces_contacts.json"), "w"))
        drifted = phone_baseline.unreviewed(self.d)
        self.assertTrue(drifted)
        self.assertEqual(drifted[0][0], "ww-1")
        # a deliberate hand edit recorded in the baseline is accepted
        data = phone_lock.load(self.d)
        data["listings"]["ww-1"]["council_phone"] = "023 9282 2251"
        data["listings"]["ww-1"]["council_ooh"] = "023 9282 2251"
        phone_lock.save(data, self.d)
        self.assertEqual(phone_baseline.unreviewed(self.d), [])

    def test_compare_lists_differences_and_regenerate_is_documented(self):
        rows = phone_baseline.diff_maps(
            {"ww-55473691": {"council_phone": "023 9282 4244"}},
            {"ww-55473691": {"council_phone": "023 9282 2251"}},
            "origin/batch-2b-content")
        self.assertEqual(rows, [("ww-55473691", "council_phone", "023 9282 4244", "023 9282 2251", "origin/batch-2b-content")])
        note = open(os.path.join(ROOT, "scripts", "phone_baseline.py"), encoding="utf-8").read()
        self.assertIn("python3 scripts/phone_baseline.py generate", note)
        self.assertIn("207", note)
        self.assertIn("208", note)
        self.assertIn("Perth", note)
        self.assertIn("Bolton", note)

if __name__ == "__main__":
    unittest.main()
