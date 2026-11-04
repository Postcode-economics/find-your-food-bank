"""FINAL lock (Dean 4 Nov 2026): a simulated refresh may not change address, postcode, lat/lng or phone
without a matching hand value; a hand edit does go live; no_pin cards never carry pin fields. Temp data only."""
import copy, os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import place_lock

PUB = {"id": "s1", "name": "S", "address": "1 High St, Town", "postcode": "AB1 2CD", "lat": 51.5, "lng": -0.1,
       "phone": "01234 567890", "phone_label": "", "hours": ""}

def run(item, hand=None, pub=PUB, guarded=None):
    return place_lock.final_lock([item], [copy.deepcopy(pub)], hand or {}, "shelters", guarded=guarded)

class FinalLock(unittest.TestCase):
    def test_feed_change_blocked_for_every_locked_field(self):
        item = dict(PUB, address="9 Feed Rd", postcode="ZZ9 9ZZ", lat=53.0, lng=-2.0)
        b = run(item)
        self.assertEqual({f for _, f, _, _ in b}, {"address", "postcode", "lat", "lng"})
        for f in ("address", "postcode", "lat", "lng"):
            self.assertEqual(item[f], PUB[f], f)

    def test_later_overwrite_after_protect_is_restored_to_guarded(self):
        # protect() left the card as published; a later step (kept copy / normaliser) overwrote it
        item = copy.deepcopy(PUB)
        guarded = place_lock.snapshot([item])
        item.update(address="9 Feed Rd", postcode="ZZ9 9ZZ", lat=53.0, lng=-2.0)
        b = run(item, guarded=guarded)
        self.assertEqual({f for _, f, _, _ in b}, {"address", "postcode", "lat", "lng"})
        for f in ("address", "postcode", "lat", "lng"):
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

    def test_rule50_value_protect_let_through_is_not_frozen(self):
        # rule 50: a pin/address value that protect() accepted is never put back to the published one
        item = dict(PUB, address="5 Moved St, Town", postcode="AB1 9XY", lat=51.7, lng=-0.3)
        guarded = place_lock.snapshot([item])
        b = run(item, guarded=guarded)
        self.assertEqual(b, [])
        self.assertEqual((item["address"], item["postcode"], item["lat"], item["lng"]), ("5 Moved St, Town", "AB1 9XY", 51.7, -0.3))

    def test_rule45_final_lock_never_touches_phone_or_council_lines(self):
        # rule 45: phones and council lines belong to phone_lock alone; final_lock neither freezes nor undoes them
        self.assertFalse(hasattr(place_lock, "LOCKED_CONTACT"))
        pub = dict(PUB, phone_label="Office", tel="01234567890", council_phone="0300 000 0000", council_ooh="0300 111 1111",
                   council_label="Council out of hours", council_label_cy="Cyngor")
        item = dict(pub, phone="01999 333333", phone_label="Main", tel="01999333333", council_phone="0300 222 2222",
                    council_ooh="0300 333 3333", council_label="X", council_label_cy="Y")
        want = copy.deepcopy(item)
        b = run(item, {"s1": {"phone": "01999 111111"}}, pub=pub)
        self.assertEqual(b, [])
        for f in ("phone", "phone_label", "tel", "council_phone", "council_ooh", "council_label", "council_label_cy"):
            self.assertEqual(item[f], want[f], f)

    def test_build_still_runs_phone_lock_before_final_lock(self):
        src = open(os.path.join(ROOT, "scripts", "build_shelters.py"), encoding="utf-8").read()
        self.assertLess(src.index("phone_lock.guard("), src.index("place_lock.final_lock("))
        self.assertIn("guarded=_guarded", src)
        self.assertLess(src.index("place_lock.protect("), src.index("place_lock.snapshot(items)"))

    def test_no_pin_never_carries_pin_fields(self):
        pub = {"id": "s1", "name": "S", "no_pin": True, "card_type": "referral_hostel", "address": "Leeds", "phone": "0113 000 0000"}
        item = dict(pub, postcode="LS1 1AA", lat=53.8, lng=-1.5)
        run(item, {"s1": {"address": "1 Office Rd, Leeds", "postcode": "LS1 1AA", "lat": 53.8, "lng": -1.5}}, pub=pub)
        for f in ("postcode", "lat", "lng"):
            self.assertIn(f, item); self.assertIn(item[f], ("", None), f)  # empty, never a value, never missing
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
