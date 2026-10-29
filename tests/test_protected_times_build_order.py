"""29 Oct 2026: build.py applied opening_times.json before IFAN pins existed, so cross_check_times ran without
protected metadata and downgraded hand-checked rows (e.g. St Laurence's Larder) to differs_review. Protected
override rows must stay confirmed_by_hand with override times after every cross-check / refresh build path."""
import hashlib, json, os, shutil, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import discover as D

ON = {"times_auto_apply": True}
R1 = "2026-10-29T20:00:00+00:00"
ST_LAURENCE = "ifan-84cd0bf40986bfc9a427c6-0"
THE_GATE = "the-gate"
BOW = "bow"
FIXTURE_PROTECTED = {
    ST_LAURENCE: {
        "checked_date": "2026-10-29",
        "protected": True,
        "quote": ["Wednesday 10.00am - 2.00pm"],
        "raw": "Wednesday 10am - 2pm (food bags, no referral needed)",
        "reader": "hand-reviewed 2026-10-29 (Dean approved)",
        "source_url": "https://www.laurenceslarder.org.uk",
        "status": "TIMES_TEXT_ONLY",
        "structured": None,
    },
    THE_GATE: {
        "checked_date": "2026-10-29",
        "protected": True,
        "raw": "Monday to Friday 2pm - 3pm (food parcel collection or by arrangement with staff; referral needed for a standard parcel)",
        "reader": "hand-reviewed 2026-10-29",
        "source_url": "https://the-gate-charity.org/contact-us-2/",
        "status": "TIMES_TEXT_ONLY",
        "structured": None,
    },
    BOW: {
        "checked_date": "2026-10-29",
        "protected": True,
        "raw": "Tuesday and Thursday 10am - 12pm (example held for review)",
        "reader": "hand-reviewed 2026-10-29",
        "source_url": "https://example.org/bow",
        "status": "TIMES_TEXT_ONLY",
        "structured": None,
    },
}


def pg(html, url="https://www.laurenceslarder.org.uk/"):
    return {"http": 200, "final_url": url, "html": html, "etag": "e", "last_modified": "", "sha256": hashlib.sha256(html.encode()).hexdigest()}


def fetch404():
    def f(u):
        return {"http": 404, "final_url": u, "html": ""}
    return f


class ProtectedTimesBuildOrder(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "overrides"))
        os.makedirs(os.path.join(self.root, "logs"))
        json.dump(FIXTURE_PROTECTED, open(os.path.join(self.root, "overrides", "opening_times.json"), "w"))

    def _item(self, iid, website, opening_times=None):
        return {
            "id": iid,
            "name": "Test",
            "type": "foodbank",
            "postcode": "BS1 1AA",
            "website": website,
            "opening_times": opening_times,
        }

    def test_cross_check_uses_override_when_item_has_no_times_yet(self):
        """Simulates a new IFAN pin: override is protected but opening_times was not applied on the item yet."""
        it = [self._item(ST_LAURENCE, "https://www.laurenceslarder.org.uk/", opening_times=None)]
        log = D.cross_check_times(it, "fb", "opening_times", fetch404(), state_root=self.root, rules=ON, run_at=R1)
        self.assertEqual(it[0]["times_status"], "confirmed_by_hand", log.get(ST_LAURENCE))
        self.assertTrue(it[0]["opening_times"]["protected"])
        self.assertEqual(it[0]["opening_times"]["raw"], FIXTURE_PROTECTED[ST_LAURENCE]["raw"])
        self.assertEqual(log[ST_LAURENCE]["status"], "differs_from_hand_checked")

    def test_all_fixture_protected_ids_stay_confirmed_after_cross_check(self):
        f = fetch404()
        for iid, ot in FIXTURE_PROTECTED.items():
            site = ot["source_url"].split("//", 1)[1].split("/", 1)[0]
            it = [self._item(iid, "https://" + site + "/", opening_times=None)]
            log = D.cross_check_times(it, "fb", "opening_times", f, state_root=self.root, rules=ON, run_at=R1)
            self.assertEqual(it[0]["times_status"], "confirmed_by_hand", iid)
            self.assertEqual(it[0]["opening_times"]["raw"], ot["raw"], iid)
            self.assertNotEqual(log[iid]["status"], "differs_review", iid)

    def test_build_reapplies_opening_overrides_after_discovery_before_cross_check(self):
        src = open(os.path.join(ROOT, "scripts", "build.py"), encoding="utf-8").read()
        i = src.index("discover.cross_check_times(items, 'fb', 'opening_times'")
        before = src[src.index("if gone:", 0):i]
        self.assertIn("opening_times.json", before)
        self.assertIn("normalise(ot)", before)
        self.assertIn("IFAN discovery", before)

    def test_live_repo_protected_overrides_include_review_list_pins(self):
        ot = json.load(open(os.path.join(ROOT, "overrides", "opening_times.json")))
        for iid in (ST_LAURENCE, THE_GATE):
            self.assertTrue(D._override_hand_protected(ot.get(iid)), iid)


if __name__ == "__main__":
    unittest.main()
