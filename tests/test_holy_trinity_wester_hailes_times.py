"""Holy Trinity Wester Hailes (ifan-5b9fd1318a04132921a389-0): Play Café Monday nav hours were auto-applied as food bank times.

Hand-checked override: food bank is Tuesday 2pm walk-in (text only). The wrong Monday table is blocked only in
overrides/times_auto_undone.json (exact value). The finder must keep reading the church's own pages."""
import hashlib, json, os, shutil, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import discover as D, times_finder as TF

FX = os.path.join(os.path.dirname(__file__), "fixtures", "holy_trinity_wester_hailes_contact_2026-10-30.html.txt")
KID = "ifan-5b9fd1318a04132921a389-0"
ITEM = {"id": KID, "name": "Holy Trinity Church, Wester Hailes", "postcode": "EH14 2SL",
        "website": "https://www.holytrinitywesterhailes.org.uk"}
RAW = "Tuesdays from 2pm, no appointment needed"
URL = "https://holytrinitywesterhailes.org.uk/contact-supporting-wh/"
QUOTE = ("For our Foodbank, no appointments are needed. You can just come on a Tuesday at 2.00pm "
         "and we'll be happy to speak about any help you need.")
MON_SIG = {"mon": [["09:30", "11:00"]]}
WED_SIG = {"wed": [["13:00", "14:00"]]}
R1, R2 = "2026-10-30T03:00:00+00:00", "2026-10-30T11:00:00+00:00"
ON = {"times_auto_apply": True}


def items():
    s = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
    return {i["id"]: i for i in json.loads(s[s.index("{"): s.rindex("}") + 1])["items"]}


def hand_override():
    return json.load(open(os.path.join(ROOT, "overrides", "opening_times.json")))[KID]


class HolyTrinityWesterHailes(unittest.TestCase):
    def setUp(self):
        self.html = open(FX, encoding="utf-8").read()
        self.ot = json.load(open(os.path.join(ROOT, "overrides", "opening_times.json")))
        self.ks = TF.known()
        self.blocked = json.load(open(os.path.join(ROOT, "overrides", "times_auto_undone.json")))
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        for d in ("logs", "reports", "overrides"):
            os.makedirs(os.path.join(self.root, d))

    def test_no_page_level_skip(self):
        self.assertNotIn(KID, self.ks.get("skip", {}))

    def test_page_carries_play_cafe_nav_and_foodbank_walk_in(self):
        text = TF.fix_text(self.html)
        self.assertIn("Play Café – Mondays at 9.30am – 11.00am", text)
        self.assertIn("For our Foodbank, no appointments are needed", text)
        self.assertIn("Tuesday at 2.00pm", text)

    def test_finder_prefers_foodbank_hours_over_play_cafe(self):
        orig = TF.polite
        self.addCleanup(setattr, TF, "polite", orig)
        TF.polite = lambda u, tries=3: (200, u, self.html) if "holytrinity" in u else orig(u, tries)
        found = TF.run([dict(ITEM)], threads=1)["found"][KID]
        st = (found or {}).get("structured") or {}
        self.assertNotIn("mon", st)
        self.assertNotEqual(st, MON_SIG)

    def test_play_cafe_monday_blocked_by_exact_undone_value_only(self):
        found = {"raw": "Mondays 9.30am – 11.00am", "status": "TIMES_FOUND", "structured": dict(MON_SIG),
                 "source_url": URL, "fb_mention": True, "reader": "times_finder", "pc_seen": ["EH142SL"]}
        seen = {KID: {"sig": json.dumps(MON_SIG, sort_keys=True), "source_url": URL, "run_at": R1}}
        why = TF.strict_checks(KID, found, ITEM, {KID: hand_override()}, seen, 1, self.ks, self.blocked, {})
        self.assertTrue(any("undone by Dean" in w for w in why), why)
        self.assertFalse(any("known skip" in w for w in why), why)
        self.assertFalse(any("protected" in w for w in why), why)

    def test_wednesday_foodbank_change_auto_applies_after_two_runs(self):
        """When the org's own page reads a new table on two runs, protected blocks only the old stored table."""
        stored = hand_override()
        json.dump({KID: stored}, open(os.path.join(self.root, "overrides", "opening_times.json"), "w"))
        ks = dict(self.ks)
        ks["skip"] = {k: v for k, v in (ks.get("skip") or {}).items() if k != KID}
        json.dump(ks, open(os.path.join(self.root, "overrides", "known_sources.json"), "w"))
        fill = " lorem ipsum" * 40
        html = ("<html><body><h1>Foodbank</h1><p>Emergency food parcels. EH14 2SL. "
                "For our Foodbank, no appointments are needed. You can just come on a Wednesday 1.00pm - 2.00pm "
                "and we'll be happy to speak about any help you need.</p>" + fill + "</body></html>")

        def pg(h):
            u = "https://holytrinitywesterhailes.org.uk/contact-supporting-wh/"
            return {"http": 200, "final_url": u, "html": h, "etag": "e", "last_modified": "",
                    "sha256": hashlib.sha256(h.encode()).hexdigest()}

        def fetch(site_map):
            def f(u):
                for k, v in site_map.items():
                    if u.rstrip("/") == k.rstrip("/"):
                        return v
                return {"http": 404, "final_url": u, "html": ""}
            return f

        f = fetch({"https://holytrinitywesterhailes.org.uk/": pg(html),
                   "https://holytrinitywesterhailes.org.uk/contact-supporting-wh/": pg(html)})
        it = [{"id": KID, "name": ITEM["name"], "postcode": ITEM["postcode"],
               "website": ITEM["website"] + "/", "opening_times": dict(stored)}]
        D.cross_check_times([dict(x) for x in it], "fb", "opening_times", f, state_root=self.root, rules=ON, run_at=R1)
        log = D.cross_check_times(it, "fb", "opening_times", f, state_root=self.root, rules=ON, run_at=R2)
        self.assertEqual(log[KID]["status"], "changed")
        self.assertTrue(log[KID].get("auto_applied"))
        self.assertEqual(it[0]["opening_times"]["structured"], WED_SIG)
        self.assertEqual(it[0]["times_status"], "updated")
        auto = json.load(open(os.path.join(self.root, "reports", "times_auto_applied.json")))
        self.assertTrue(any(e.get("id") == KID and e.get("path") == "cross_check" for e in auto))
        ot = json.load(open(os.path.join(self.root, "overrides", "opening_times.json")))
        self.assertEqual(ot[KID]["structured"], WED_SIG)
        self.assertTrue(ot[KID]["protected"])

        wed = {"raw": "Wednesday 1pm - 2pm", "status": "TIMES_FOUND", "structured": dict(WED_SIG),
               "source_url": URL, "fb_mention": True, "reader": "times_finder", "pc_seen": ["EH142SL"], "_run_at": R2}
        seen = {KID: {"sig": json.dumps(WED_SIG, sort_keys=True), "source_url": URL, "run_at": R1}}
        why = TF.strict_checks(KID, wed, ITEM, {KID: ot[KID]}, seen, 1, ks, self.blocked, {})
        self.assertIn("hand-checked times are protected; finder only flags differences", why)

    def test_protected_text_only_on_map(self):
        e = self.ot[KID]
        self.assertTrue(e["protected"] and e["status"] == "TIMES_TEXT_ONLY" and e["structured"] is None)
        self.assertEqual(e["raw"], RAW)
        self.assertEqual(e["source_url"], URL)
        self.assertIn("Tuesday at 2.00pm", e["quote"][0])
        card = items()[KID]["opening_times"]
        self.assertEqual(card["raw"], RAW)
        self.assertEqual(card["lines"], [RAW])
        self.assertIsNone(card.get("structured"))
        self.assertNotIn("mon", json.dumps(card))
        self.assertEqual(items()[KID]["times_status"], "confirmed_by_hand")

    def test_refresh_treats_as_hand_checked(self):
        ix = items()[KID]
        self.assertTrue(D.hand_checked(ix, "opening_times"))
        why = TF.strict_checks(KID, {"raw": "Mondays 9.30am – 11.00am", "source_url": URL}, ix, self.ot, {}, 1, self.ks, {}, {})
        self.assertIn("hand-checked times are protected; finder only flags differences", why)


if __name__ == "__main__":
    unittest.main()
