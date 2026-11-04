"""Scoped card patch: only named cards change, phones never change, no adds, no_pin rule, whole-file guard."""
import json, os, shutil, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import patch_cards
from common import write_js, load_js

A = {"id": "a", "name": "A", "address": "1 Old Rd", "postcode": "AB1 2CD", "lat": 51.5, "lng": -0.1, "phone": "01234 567890", "hours": ""}
B = {"id": "b", "name": "B", "address": "2 Rd", "postcode": "AB1 3CD", "lat": 51.4, "lng": -0.2, "phone": "01234 000000", "hours": ""}
N = {"id": "n", "name": "N", "no_pin": True, "card_type": "referral_hostel", "address": "Leeds", "phone": "0113 000 0000"}

class Patch(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "overrides"))
        write_js(os.path.join(self.root, "shelters.js"), "SHELTERS", {"updated": "2026-11-01", "items": [dict(A), dict(B), dict(N)]})
        self.man = [dict(A, address="1 Old Road, Town", hours="Staffed 24/7", phone="0800 999 999", who_for=["Adults 18+"]),
                    dict(B, address="2 Changed Rd"), dict(N, address="1 Office Rd, Leeds", postcode="LS1 1AA", lat=53.8, lng=-1.5)]
        self.write()

    def write(self, ver=None):
        json.dump(self.man, open(os.path.join(self.root, "overrides", "shelters_manual.json"), "w"))
        json.dump(ver or {}, open(os.path.join(self.root, "overrides", "shelters_verified.json"), "w"))

    def test_only_named_card_changes_and_phone_kept(self):
        data, changed, _ = patch_cards.patch(["a"], self.root, today="2026-11-04")
        by = {x["id"]: x for x in data["items"]}
        self.assertEqual(changed, ["a"])
        self.assertEqual(by["a"]["address"], "1 Old Road, Town")
        self.assertEqual(by["a"]["hours"], "Staffed 24/7")
        self.assertEqual(by["a"]["who_for"], ["Adults 18+"])
        self.assertEqual(by["a"]["phone"], A["phone"])
        self.assertEqual(by["b"]["address"], "2 Rd")  # not named: untouched even though its hand value differs

    def test_unknown_id_refused(self):
        with self.assertRaises(patch_cards.PatchError):
            patch_cards.patch(["zzz"], self.root)

    def test_no_pin_card_gets_no_pin_fields(self):
        data, changed, _ = patch_cards.patch(["n"], self.root)
        n = [x for x in data["items"] if x["id"] == "n"][0]
        for f in ("postcode", "lat", "lng"):
            self.assertNotIn(f, n)
        self.assertEqual(n["address"], "Leeds")

    def test_main_writes_file_and_dry_run_does_not(self):
        p = os.path.join(self.root, "shelters.js"); before = open(p).read()
        self.assertEqual(patch_cards.main(["a", "--root", self.root, "--dry-run"]), 0)
        self.assertEqual(open(p).read(), before)
        self.assertEqual(patch_cards.main(["a", "--root", self.root]), 0)
        self.assertEqual({x["id"]: x for x in load_js(p, "SHELTERS")["items"]}["a"]["address"], "1 Old Road, Town")

if __name__ == "__main__":
    unittest.main()
