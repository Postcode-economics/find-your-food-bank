"""Regression (31 Oct 2026): four wrong auto-applied food bank times and the gates that let them through."""
import hashlib, json, os, shutil, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import discover as D

R1, R2 = "2026-10-31T08:00:00+00:00", "2026-10-31T16:00:00+00:00"
ON = {"times_auto_apply": True}
FILL = " lorem ipsum" * 40

STOREHOUSE = (
    "Volunteer with us Foodbank open for anyone in need We are open on Monday, Wednesday and Friday from 10.30am – 12.30pm. "
    "Our cafe is located in the Access Centre & open Monday, Tuesday, Wednesday and Friday 10am-1pm. " + FILL
)
WELLINGBOROUGH = (
    "Opening Hours: Monday through to Friday, 9am-12pm Delivery Service: We operate a delivery service, we do not offer walk-in's. "
    + FILL
)
BURGESS = (
    "OUR LOCATIONS BURGESS HILL 85 Church Walk, Burgess Hill Tuesday and Thursday 11am - 1pm, Saturday 10am - 12pm "
    "HASSOCKS Powell House, 21 Keymer Road Open on Fridays 10am - 12pm HURSTPIERPOINT " + FILL
)
COMMUNITY = (
    "West Kingsdown Details Mon, Wed & Fri: 10am 12 noon Tues & Thur 12 -2pm Sat - Sun: Closed "
    "Address: The Community Cupboard, Gamecock Meadow, London Road, West Kingsdown, TN15 6EL " + FILL
)


def pg(body, url="https://example.org/"):
    return {"http": 200, "final_url": url, "html": "<html><body><p>%s</p></body></html>" % body,
            "etag": "e", "last_modified": "", "sha256": hashlib.sha256(body.encode()).hexdigest()}


class ExtractGates(unittest.TestCase):
    def test_storehouse_foodbank_not_cafe_and_not_volunteer_false_positive(self):
        rej = []
        ot = D.extract_times(STOREHOUSE, None, rejected=rej)
        self.assertEqual(ot["structured"], {"mon": [["10:30", "12:30"]], "wed": [["10:30", "12:30"]], "fri": [["10:30", "12:30"]]})
        self.assertTrue(any("caf" in r["reason"] for r in rej))
        self.assertFalse(any("volunteer" in r["reason"] for r in rej if "Foodbank" in r.get("text", "")))

    def test_wellingborough_mon_to_fri_not_friday_only(self):
        ot = D.extract_times(WELLINGBOROUGH, None)
        days = sorted((ot or {}).get("structured") or {})
        self.assertEqual(days, ["fri", "mon", "thu", "tue", "wed"])

    def test_burgess_hill_drops_hassocks_friday(self):
        ot = D.extract_times(BURGESS, None, name="Burgess Hill Foodbank")
        self.assertNotIn("fri", (ot or {}).get("structured") or {})
        self.assertEqual(set((ot or {}).get("structured") or {}), {"tue", "thu", "sat"})

    def test_community_cupboard_keeps_all_five_days(self):
        ot = D.extract_times(COMMUNITY, None)
        self.assertEqual(set((ot or {}).get("structured") or {}), {"fri", "mon", "thu", "tue", "wed"})

    def test_drops_source_days_blocks_friday_only_table(self):
        new = {"structured": {"fri": [["09:00", "12:00"]]}, "status": "TIMES_FOUND"}
        why = D.drops_source_days_reason(new, [WELLINGBOROUGH])
        self.assertIn("drops Mon", why)


class CrosscheckHeld(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        for d in ("logs", "reports", "overrides"):
            os.makedirs(os.path.join(self.root, d))
        json.dump({}, open(os.path.join(self.root, "overrides", "opening_times.json"), "w"))

    def twice(self, item, body, site):
        it = [item]

        def fetch(u):
            return pg(body, site) if u.rstrip("/") == site.rstrip("/") else {"http": 404, "final_url": u, "html": ""}

        D.cross_check_times([dict(x) for x in it], "fb", "opening_times", fetch, state_root=self.root, rules=ON, run_at=R1)
        return D.cross_check_times(it, "fb", "opening_times", fetch, state_root=self.root, rules=ON, run_at=R2)

    def test_friday_only_table_blocked_by_source_days_gate(self):
        item = {"id": "wellingborough-district", "name": "Wellingborough & District Foodbank", "postcode": "NN8 4HB",
                "website": "https://www.daylightcf.org/foodbank/", "opening_times": None}
        new = {"structured": {"fri": [["09:00", "12:00"]]}, "status": "TIMES_FOUND", "raw": "Friday 9am-12pm"}
        seen = {"fb:wellingborough-district": {"sig": json.dumps(new["structured"], sort_keys=True),
                                               "source_url": "https://www.daylightcf.org/foodbank/", "run_at": R1}}
        why = D.times_gate_reasons(item, "fb", "opening_times", new, [WELLINGBOROUGH],
                                   {"final_url": "https://www.daylightcf.org/foodbank/"}, seen, {}, True, R2)
        self.assertTrue(any("drops Mon" in w for w in why), why)


if __name__ == "__main__":
    unittest.main()
