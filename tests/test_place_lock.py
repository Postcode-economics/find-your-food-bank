"""A refresh must not move a pin or rewrite an address. Hand-set values may. Mismatches are flagged, not applied."""
import json, os, shutil, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import place_lock
import times_finder as TF

PUB = {"id": "riverside", "name": "Riverside", "address": "1 High St, AB1 2CD", "postcode": "AB1 2CD", "lat": 51.5, "lng": -0.1}

class Protect(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "reports"))

    def test_a_feed_address_and_pin_are_put_back_and_flagged(self):
        item = dict(PUB, address="99 Other Road, ZZ9 9ZZ", postcode="ZZ9 9ZZ", lat=53.0, lng=-2.0)
        n = place_lock.protect([item], [PUB], {}, self.root, "foodbanks")
        self.assertEqual(n, 4)
        self.assertEqual(item["address"], PUB["address"])
        self.assertEqual(item["postcode"], PUB["postcode"])
        self.assertEqual((item["lat"], item["lng"]), (PUB["lat"], PUB["lng"]))
        text = open(os.path.join(self.root, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertIn("address mismatch, held for Dean", text)
        self.assertIn("riverside", text)
        self.assertIn("unchanged", text)
        self.assertNotIn("99 Other Road", item["address"])

    def test_a_hand_set_address_is_kept(self):
        hand = {"riverside": {"address": "Rear hall, 1 High St, AB1 2CD", "postcode": "AB1 2CD", "lat": 51.6, "lng": -0.5}}
        item = dict(PUB, address=hand["riverside"]["address"], lat=51.6, lng=-0.5)
        n = place_lock.protect([item], [PUB], hand, self.root, "foodbanks")
        self.assertEqual(item["address"], hand["riverside"]["address"])
        self.assertEqual(item["lat"], 51.6)
        self.assertEqual(n, 0)
        path = os.path.join(self.root, "reports", "pending_dean.md")
        if os.path.exists(path):
            self.assertNotIn("| address |", open(path, encoding="utf-8").read())

    def test_rounding_inside_20m_keeps_the_published_bytes_and_is_not_a_move(self):
        item = dict(PUB, lat=51.50001, lng=-0.10001)
        n = place_lock.protect([item], [PUB], {}, self.root, "foodbanks")
        self.assertEqual(n, 0)
        self.assertEqual((item["lat"], item["lng"]), (51.5, -0.1))
        self.assertFalse(os.path.exists(os.path.join(self.root, "reports", "pending_dean.md")))

    def test_directory_hours_are_put_back_unless_the_gate_applied_them(self):
        old = dict(PUB, hours={"Tue": "10:00 - 12:00"})
        item = dict(old, hours={"Thu": "14:00 - 16:00"})
        n = place_lock.protect([item], [old], {}, self.root, "warmspaces")
        self.assertGreater(n, 0)
        self.assertEqual(item["hours"], {"Tue": "10:00 - 12:00"})
        text = open(os.path.join(self.root, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertIn("times kept, not auto-applied", text)
        gated = dict(old, hours={"Thu": "14:00 - 16:00"})
        place_lock.protect([gated], [old], {}, self.root, "warmspaces", keep_times={"riverside"})
        self.assertEqual(gated["hours"], {"Thu": "14:00 - 16:00"})
        fb = dict(PUB, opening_times={"structured": {"thu": [["14:00", "16:00"]]}})
        place_lock.protect([fb], [dict(PUB, opening_times={"structured": {"tue": [["10:00", "12:00"]]}})], {}, self.root, "foodbanks")
        self.assertEqual(fb["opening_times"]["structured"], {"thu": [["14:00", "16:00"]]})

    def test_a_checked_date_bump_is_not_counted_as_new_hours(self):
        old = dict(PUB, opening_times={"structured": {"tue": [["10:00", "12:00"]]}, "checked_date": "2026-10-01"})
        new = dict(PUB, opening_times={"structured": {"tue": [["10:00", "12:00"]]}, "checked_date": "2026-10-28"})
        diff = place_lock.changes([old], [new])
        self.assertEqual(diff["opening_times"], 0)
        self.assertEqual(diff["checked_date_only"], 1)
        moved = dict(PUB, opening_times={"structured": {"wed": [["09:00", "11:00"]]}, "checked_date": "2026-10-28"})
        self.assertEqual(place_lock.changes([old], [moved])["opening_times"], 1)

    def test_a_new_id_is_not_treated_as_a_moved_pin(self):
        item = dict(PUB, id="brand-new", lat=53.0)
        n = place_lock.protect([item], [PUB], {}, self.root, "foodbanks")
        self.assertEqual(n, 0)
        self.assertEqual(item["lat"], 53.0)

    def test_build_and_own_locations_do_not_assign_a_new_pin(self):
        build = open(os.path.join(ROOT, "scripts", "build.py"), encoding="utf-8").read()
        own = open(os.path.join(ROOT, "scripts", "own_locations.py"), encoding="utf-8").read()
        self.assertNotIn("moved_to_postcode", build)
        self.assertNotIn("orig_latlng", build)
        self.assertNotIn('hit["lat"]', own)
        self.assertNotIn("hit.update(", own)

    def test_hand_set_times_cannot_pass_the_finder(self):
        ot = {"structured": {"mon": [["10:00", "12:00"]]}, "status": "TIMES_FOUND", "source_url": "https://x.org/",
              "raw": "Monday 10:00 - 12:00", "pc_seen": ["AB12CD"], "fb_mention": True, "reader": "times_finder"}
        why = TF.strict_checks("west", ot, {"id": "west", "postcode": "AB1 2CD", "website": "https://x.org/", "name": "West", "foodbank": "West"},
                                {"west": {"protected": True, "reader": "hand-set 2026-10-24", "structured": {"tue": [["09:00", "10:00"]]}, "status": "TIMES_FOUND"}},
                                {"west": {"sig": json.dumps(ot["structured"]), "source_url": "https://x.org/", "run_at": "a"}},
                                1, {"skip": {}}, {}, {})
        self.assertTrue(any("hand-checked" in w for w in why), why)


if __name__ == "__main__":
    unittest.main()
