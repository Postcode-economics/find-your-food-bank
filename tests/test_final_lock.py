"""FINAL lock (Dean 4 Nov 2026): a simulated refresh may not change address, postcode, lat/lng or phone
without a matching hand value; a hand edit does go live; no_pin cards never carry pin fields. Temp data only."""
import copy, os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import place_lock

PUB = {"id": "s1", "name": "S", "address": "1 High St, Town", "postcode": "AB1 2CD", "lat": 51.5, "lng": -0.1,
       "phone": "01234 567890", "phone_label": "", "hours": ""}

def run(item, hand=None, baseline=None, pub=PUB):
    return place_lock.final_lock([item], [copy.deepcopy(pub)], hand or {}, "shelters", baseline=baseline)

class FinalLock(unittest.TestCase):
    def test_feed_change_blocked_for_every_locked_field(self):
        item = dict(PUB, address="9 Feed Rd", postcode="ZZ9 9ZZ", lat=53.0, lng=-2.0, phone="0800 000 000")
        b = run(item)
        self.assertEqual({f for _, f, _, _ in b}, {"address", "postcode", "lat", "lng", "phone"})
        for f in ("address", "postcode", "lat", "lng", "phone"):
            self.assertEqual(item[f], PUB[f], f)

    def test_kept_copy_with_stale_values_gets_hand_values(self):
        # blocked-fetch kept copy carries the old published values; the hand file has new ones
        item = copy.deepcopy(PUB)
        hand = {"s1": {"address": "1 High Street, Town", "postcode": "AB1 2CE", "lat": 51.6, "lng": -0.2}}
        run(item, hand)
        self.assertEqual((item["address"], item["postcode"], item["lat"], item["lng"]), ("1 High Street, Town", "AB1 2CE", 51.6, -0.2))

    def test_verified_record_path_hand_value_goes_live(self):
        item = dict(PUB, address="2 New Rd, Town")
        run(item, {"s1": {"address": "2 New Rd, Town"}})
        self.assertEqual(item["address"], "2 New Rd, Town")

    def test_phone_change_only_to_hand_or_baseline(self):
        item = dict(PUB, phone="01999 111111")
        run(item, {"s1": {"phone": "01999 111111"}})
        self.assertEqual(item["phone"], "01999 111111")
        item = dict(PUB, phone="01999 222222")
        run(item, baseline={"s1": {"phone": "01999 222222"}})
        self.assertEqual(item["phone"], "01999 222222")
        item = dict(PUB, phone="01999 333333")
        run(item, {"s1": {"phone": "01999 111111"}})
        self.assertEqual(item["phone"], PUB["phone"])

    def test_no_pin_never_carries_pin_fields(self):
        pub = {"id": "s1", "name": "S", "no_pin": True, "card_type": "referral_hostel", "address": "Leeds", "phone": "0113 000 0000"}
        item = dict(pub, postcode="LS1 1AA", lat=53.8, lng=-1.5)
        run(item, {"s1": {"address": "1 Office Rd, Leeds", "postcode": "LS1 1AA", "lat": 53.8, "lng": -1.5}}, pub=pub)
        for f in ("postcode", "lat", "lng"):
            self.assertNotIn(f, item)
        self.assertEqual(item["address"], "Leeds")

    def test_blank_hand_value_keeps_published(self):
        item = dict(PUB, address="9 Feed Rd")
        run(item, {"s1": {"address": "", "postcode": "Not stated"}})
        self.assertEqual(item["address"], PUB["address"])

    def test_hours_untouched(self):
        item = dict(PUB, hours={"Mon": "09:00 - 17:00"})
        run(item)
        self.assertEqual(item["hours"], {"Mon": "09:00 - 17:00"})

    def test_build_calls_final_lock_last_before_write(self):
        src = open(os.path.join(ROOT, "scripts", "build_shelters.py"), encoding="utf-8").read()
        i, w = src.index("place_lock.final_lock("), src.index('write_js(OUT, "SHELTERS"')
        self.assertLess(i, w)
        between = src[i:w]
        for later in ("verification_gate(", "hours_norm.apply(", "protect(", "phone_lock.guard(", "fill_referral_routes("):
            self.assertNotIn(later, between, later)

if __name__ == "__main__":
    unittest.main()
