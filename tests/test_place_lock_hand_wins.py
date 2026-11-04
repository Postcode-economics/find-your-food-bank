"""Hand-checked manual values win over the published copy for address, postcode and hours (Dean, 4 Nov 2026).
Feed-only changes stay blocked, phones are untouched, no_pin cards never get a place field. Temp folders only."""
import os, shutil, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import place_lock

PUB = {"id": "man-ss-x", "name": "X", "address": "104 Denmark Road, Manchester", "postcode": "M15 6JS",
       "lat": 53.46, "lng": -2.23, "phone": "0161 000 0000", "hours": ""}

class HandWins(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "reports"))

    def run_lock(self, item, hand, keep=()):
        return place_lock.protect([item], [dict(PUB)], hand, self.root, "shelters", keep_times=keep)

    def test_reworded_manual_address_beats_published(self):
        hand = {"man-ss-x": {"address": "104 Denmark Road, Hulme"}}
        item = dict(PUB)  # the build still carries the old published wording
        self.run_lock(item, hand)
        self.assertEqual(item["address"], "104 Denmark Road, Hulme")
        item = dict(PUB, address="104 Denmark Road, Hulme")  # already equal: never restored
        self.run_lock(item, hand)
        self.assertEqual(item["address"], "104 Denmark Road, Hulme")

    def test_manual_non_table_hours_are_kept(self):
        hand = {"man-ss-x": {"hours": "Staffed 24/7"}}
        item = dict(PUB, hours="Staffed 24/7")
        self.run_lock(item, hand)
        self.assertEqual(item["hours"], "Staffed 24/7")
        item = dict(PUB)
        self.run_lock(item, hand)
        self.assertEqual(item["hours"], "Staffed 24/7")

    def test_times_gate_confirmed_hours_still_apply(self):
        hand = {"man-ss-x": {"hours": "Staffed 24/7"}}
        new = {"Mon": "09:00 - 17:00"}
        item = dict(PUB, hours=new)
        self.run_lock(item, hand, keep=("man-ss-x",))
        self.assertEqual(item["hours"], new)

    def test_feed_only_change_is_still_blocked(self):
        item = dict(PUB, address="1 Feed Street", postcode="ZZ9 9ZZ", hours={"Mon": "10:00 - 11:00"})
        self.run_lock(item, {})
        self.assertEqual(item["address"], PUB["address"])
        self.assertEqual(item["postcode"], PUB["postcode"])
        self.assertIn(item.get("hours"), (None, ""))

    def test_blank_or_not_stated_manual_keeps_published(self):
        for blank in ("", "Not stated"):
            item = dict(PUB, address="1 Feed Street")
            self.run_lock(item, {"man-ss-x": {"address": blank, "hours": blank}})
            self.assertEqual(item["address"], PUB["address"])

    def test_phone_is_unchanged(self):
        item = dict(PUB, phone="0161 999 9999")
        self.run_lock(item, {"man-ss-x": {"address": "104 Denmark Road, Hulme", "phone": "0800 111 1111"}})
        self.assertEqual(item["phone"], "0161 999 9999")

    def test_no_pin_card_never_gets_place_fields(self):
        item = {"id": "man-ss-x", "name": "X", "no_pin": True, "card_type": "referral_hostel", "phone": "0161 000 0000"}
        place_lock.protect([item], [dict(item)], {"man-ss-x": {"address": "1 Secret Road", "postcode": "M1 1AA",
                                                               "lat": 53.0, "lng": -2.0}}, self.root, "shelters")
        for f in ("address", "postcode", "lat", "lng"):
            self.assertNotIn(f, item)
        kept = dict(item)
        place_lock.apply_hand(kept, place_lock.hand_record({"address": "1 Secret Road"}, {"postcode": "M1 1AA"}))
        for f in ("address", "postcode", "lat", "lng"):
            self.assertNotIn(f, kept)

    def test_kept_copy_path_uses_the_same_function(self):
        src = open(os.path.join(ROOT, "scripts", "common.py"), encoding="utf-8").read()
        self.assertIn("place_lock.apply_hand(", src)

if __name__ == "__main__":
    unittest.main()
