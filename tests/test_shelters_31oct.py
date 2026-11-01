"""31 Oct 2026: four hand-verified shelters, and three corrections that a refresh must keep.

Cambria House Lifehouse, Union Terrace Hostel, Robinson Court, Howe Hill for Young People.
Harnall Lifehouse postcode CV1 4EZ (postcodes.io pin). Willow House Lifehouse name and sit-up /
emergency beds. Peasholme Centre phone 01904 551901.

Hermetic: no network. Source pages are the quotes stored in shelters_verified.json.
"""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import common, phone_lock, place_lock, publish_gate as pg, recheck as R, shelter_contacts
from hours_fix import apply_phone

OV = os.path.join(ROOT, "overrides")
NEW_IDS = (
    "man-cambria-house-lifehouse",
    "man-union-terrace-hostel",
    "man-robinson-court",
    "man-howe-hill-young-people",
)
YORK_REF = "Referral needed – contact City of York Council Housing Options, the Rough Sleeper Team drop-in, or the Single Access Point"
CAMBRIA_REF = "Referral needed – contact other hostels in Camden, the Safer Streets team in Camden, or Housing Options Camden"
PEASHOLME = "01904 551901"
WILLOW = "osm-way-96032322"


def _manual():
    return {x["id"]: x for x in json.load(open(os.path.join(OV, "shelters_manual.json"), encoding="utf-8"))}


def _verified():
    return json.load(open(os.path.join(OV, "shelters_verified.json"), encoding="utf-8"))


def _published():
    t = open(os.path.join(ROOT, "shelters.js"), encoding="utf-8").read()
    return {i["id"]: i for i in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}


def _page(ov):
    text = " ".join(str(ov.get(k) or "") for k in ("quote", "day_time_quote", "address", "postcode", "name"))
    text = (text + " referral ") * 4
    return {"http": 200, "text": text, "final_url": ov["evidence_url"], "etag": "", "last_modified": "", "sha256": "x"}


class NewShelters(unittest.TestCase):
    def test_manual_verified_approval_and_baseline(self):
        manual, verified = _manual(), _verified()
        approved = json.load(open(os.path.join(OV, "approved_new_places.json"), encoding="utf-8"))["shelters"]
        base = json.load(open(os.path.join(OV, "phone_baseline.json"), encoding="utf-8"))["listings"]
        expect = {
            "man-cambria-house-lifehouse": ("WC1N 1BJ", "020 7841 0230", "02078410230", CAMBRIA_REF, "48"),
            "man-union-terrace-hostel": ("YO31 7ES", "01904 630500", "01904630500", YORK_REF, "35"),
            "man-robinson-court": ("YO1 9TR", "01904 642307", "01904642307", YORK_REF, "18"),
            "man-howe-hill-young-people": ("YO24 4HA", "01904 553141", "01904553141", YORK_REF, "29"),
        }
        for i in NEW_IDS:
            m, v = manual[i], verified[i]
            pc, phone, tel, ref, beds = expect[i]
            self.assertEqual(m["postcode"], pc)
            self.assertEqual(m["phone"], phone)
            self.assertEqual(m["referral"], ref)
            self.assertEqual(v["access"], ref)
            self.assertEqual(m["beds"], beds)
            self.assertEqual(m["source"], "Manual (verified from source pages)")
            self.assertEqual(m["last_verified"], "2026-10-31")
            self.assertFalse(m["flag_closed"])
            self.assertFalse(m["stale"])
            self.assertEqual(m["access_type"], "referral_only")
            self.assertEqual(v["verified_on"], "2026-10-31")
            self.assertEqual(v["access_type"], "referral_only")
            self.assertTrue(v.get("evidence_url") and v.get("quote"))
            self.assertIn(i, approved)
            self.assertEqual(base[i]["layer"], "shelters")
            self.assertEqual(base[i]["phone"], phone)
            self.assertEqual(base[i]["tel"], tel)
            self.assertNotIn("council_phone", base[i])

    def test_york_hours_and_cambria_who(self):
        manual = _manual()
        for i in NEW_IDS[1:]:
            self.assertEqual(manual[i]["hours"], "Staffed 24 hours a day, 7 days a week")
        self.assertEqual(_manual()["man-cambria-house-lifehouse"]["groups"], ["Single men", "Age 18+"])
        self.assertEqual(_manual()["man-howe-hill-young-people"]["groups"], ["Young people 16-25", "Young parents"])

    def test_recheck_accepts_stored_quotes(self):
        manual, verified = _manual(), _verified()
        for i in NEW_IDS:
            r = R.check(manual[i], verified[i], _page(verified[i]), verified[i]["evidence_url"])
            self.assertTrue(r["ok"], (i, r))

    def test_gate_sets_card_referral(self):
        """The card prints i.referral. The gate copies verified access, which is the 'Referral needed – contact …' line."""
        manual, verified = _manual(), _verified()
        pending = os.path.join(tempfile.mkdtemp(), "shelters_pending.json")
        pub, _, n = common.verification_gate([dict(manual[i]) for i in NEW_IDS], None, verified, "2026-10-31", pending, recheck=False)
        self.assertEqual(n, 0)
        by = {p["id"]: p for p in pub}
        self.assertEqual(by["man-cambria-house-lifehouse"]["referral"], CAMBRIA_REF)
        for i in NEW_IDS[1:]:
            self.assertEqual(by[i]["referral"], YORK_REF)
            self.assertTrue(by[i].get("groups"))
        js = open(os.path.join(ROOT, "layers.js"), encoding="utf-8").read()
        self.assertIn("row('ref',esc(i.referral))", js)

    def test_publish_gate_does_not_hold_approved_rows(self):
        d = tempfile.mkdtemp()
        try:
            shutil.copytree(os.path.join(ROOT, "scripts"), os.path.join(d, "scripts"), ignore=shutil.ignore_patterns("__pycache__"))
            for sub in ("logs", "reports", "overrides"):
                os.makedirs(os.path.join(d, sub))
            shutil.copy(os.path.join(OV, "auto_apply_rules.json"), os.path.join(d, "overrides"))
            shutil.copy(os.path.join(OV, "approved_new_places.json"), os.path.join(d, "overrides"))
            ver = _verified()
            items = []
            for i in NEW_IDS:
                pub, _, _ = common.verification_gate([dict(_manual()[i])], None, ver, "2026-10-31", os.path.join(d, "logs", "shelters_pending.json"), recheck=False)
                row = pub[0]
                apply_phone(row)
                items.append(row)
            path = os.path.join(d, pg.FILES["shelters"])
            open(path, "w").write("var SHELTERS=" + json.dumps({"items": []}, separators=(",", ":")) + ";")
            git = lambda *a: subprocess.run(a, cwd=d, check=True, capture_output=True)
            git("git", "init", "-q")
            git("git", "add", "-A")
            git("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "empty")
            open(path, "w").write("var SHELTERS=" + json.dumps({"items": items}, separators=(",", ":")) + ";")
            r = subprocess.run([sys.executable, os.path.join("scripts", "publish_gate.py"), "shelters"], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            left = [x["id"] for x in json.loads(open(path).read().split("=", 1)[1].strip().rstrip(";"))["items"]]
            pending = json.load(open(os.path.join(d, "logs", "pending_dean.json"))).get("shelters", [])
            self.assertEqual(set(left), set(NEW_IDS))
            self.assertEqual(pending, [])
        finally:
            shutil.rmtree(d, True)


class Corrections(unittest.TestCase):
    def test_harnall_postcode_and_pin_are_the_hand_lock(self):
        m = _manual()["sa-harnall-lifehouse"]
        live = _published()["sa-harnall-lifehouse"]
        self.assertEqual(m["postcode"], "CV1 4EZ")
        self.assertEqual(m["lat"], 52.415612)
        self.assertEqual(m["lng"], -1.507892)
        self.assertIn("CV1 4EZ", m["postcode_note"])
        self.assertIn("salvationarmy.org.uk/harnall-lifehouse", m["postcode_note"])
        self.assertEqual(live["postcode"], "CV1 4EZ")
        self.assertEqual(live["lat"], 52.415612)
        self.assertEqual(live["lng"], -1.507892)
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "reports"))
            hand = place_lock.hands(ROOT, "shelters")
            self.assertEqual(hand["sa-harnall-lifehouse"]["postcode"], "CV1 4EZ")
            # A feed that still has CV1 4EY must not overwrite the corrected pin.
            proposed = {"id": "sa-harnall-lifehouse", "name": "Harnall Lifehouse", "address": "Harnall Lifehouse",
                        "postcode": "CV1 4EY", "lat": 52.415804, "lng": -1.5072117, "hours": "By referral, call to arrange"}
            place_lock.protect([proposed], [dict(live)], hand, root=d, source="shelters")
            self.assertEqual(proposed["postcode"], "CV1 4EZ")
            self.assertEqual(proposed["lat"], 52.415612)
            self.assertEqual(proposed["lng"], -1.507892)
        finally:
            shutil.rmtree(d, True)

    def test_willow_name_beds_and_refresh_keeps_manual_row(self):
        m = _manual()[WILLOW]
        v = _verified()[WILLOW]
        live = _published()[WILLOW]
        self.assertEqual(m["name"], "Willow House Lifehouse")
        self.assertEqual(v["name"], "Willow House Lifehouse")
        self.assertEqual(live["name"], "Willow House Lifehouse")
        self.assertIn("2-3 sit up beds (night shelter)", m["beds"])
        self.assertIn("4-8 emergency/assessment beds", m["beds"])
        self.assertEqual(live["beds"], m["beds"])
        self.assertIn("2-3 sit up beds (night shelter), 4-8 emergency/assessment beds", v["quote"])
        self.assertIn("emergency beds for up to 2 weeks", v["quote"])
        self.assertIn("salvationarmy.org.uk/willow-house", v["evidence_url"])
        r = R.check(m, v, _page(v), v["evidence_url"])
        self.assertTrue(r["ok"], r)
        osm = {"id": WILLOW, "name": "Salvation Army", "address": "Willow Street, Reading", "postcode": "RG1 6AB",
               "lat": 51.4515892, "lng": -0.9764353, "last_verified": "2026-10-31", "beds": ""}
        items, _ = common.merge_lifecycle({"items": []}, [osm, dict(m)], "2026-10-31")
        hit = [x for x in items if x["id"] == WILLOW]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0]["name"], "Willow House Lifehouse")
        self.assertIn("sit up beds", hit[0]["beds"])
        src = open(os.path.join(ROOT, "scripts", "build_shelters.py"), encoding="utf-8").read()
        self.assertLess(src.index('fresh.append({"id": f"osm-'), src.index("fresh.append(m)"))

    def test_peasholme_phone_lock(self):
        v = _verified()["osm-node-1533578890"]
        live = _published()["osm-node-1533578890"]
        base = json.load(open(os.path.join(OV, "phone_baseline.json"), encoding="utf-8"))["listings"]["osm-node-1533578890"]
        self.assertEqual(v["phone"], PEASHOLME)
        self.assertIn("01904 551901", v["quote"])
        self.assertIn("01904 554500", v["note"])
        self.assertIn("Housing Options", v["note"])
        self.assertEqual(live["phone"], PEASHOLME)
        self.assertEqual(live["tel"], "01904551901")
        self.assertEqual(base["phone"], PEASHOLME)
        self.assertEqual(base["tel"], "01904551901")
        self.assertIn("01904 551901", base["why"])
        contacts = json.load(open(os.path.join(OV, "shelters_contacts.json"), encoding="utf-8"))["osm-node-1533578890"]
        self.assertEqual(contacts["phone_fix"], PEASHOLME)
        self.assertIn("554500", contacts["phone_fix_why"])
        item = {"id": "osm-node-1533578890", "name": "Peasholme Homeless Hostel", "phone": "01904 554500", "tel": "01904554500"}
        shelter_contacts.apply([item])
        self.assertEqual(item["phone"], PEASHOLME)
        self.assertEqual(item["tel"], "01904551901")
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "overrides"))
            os.makedirs(os.path.join(d, "reports"))
            shutil.copy(os.path.join(OV, "phone_baseline.json"), os.path.join(d, "overrides", "phone_baseline.json"))
            phone_lock._cache.clear()
            same = {"id": "osm-node-1533578890", "name": "Peasholme Homeless Hostel", "phone": PEASHOLME, "tel": "01904551901"}
            phone_lock.guard([same], d, via="refresh", source="feed refresh", layer="shelters")
            self.assertEqual(same["phone"], PEASHOLME)
            held = open(os.path.join(d, "reports", "pending_dean.md"), encoding="utf-8").read() if os.path.exists(os.path.join(d, "reports", "pending_dean.md")) else ""
            self.assertNotIn("osm-node-1533578890", held)
            old = {"id": "osm-node-1533578890", "name": "Peasholme Homeless Hostel", "phone": "01904 554500", "tel": "01904554500"}
            phone_lock.guard([old], d, via="refresh", source="feed refresh", layer="shelters")
            self.assertEqual(old["phone"], PEASHOLME)
            self.assertEqual(old["tel"], "01904551901")
        finally:
            phone_lock._cache.clear()
            shutil.rmtree(d, True)


class BlanketThree(unittest.TestCase):
    """Dean blanket approval 31 Oct 2026: three building-verified hostels publish."""
    IDS = ("man-contact-hostel", "man-one-ymca-bishops-stortford", "man-roundabout-hostel")

    def test_files_and_map(self):
        manual, verified = _manual(), _verified()
        approved = json.load(open(os.path.join(OV, "approved_new_places.json"), encoding="utf-8"))["shelters"]
        base = json.load(open(os.path.join(OV, "phone_baseline.json"), encoding="utf-8"))["listings"]
        live = _published()
        expect = {
            "man-contact-hostel": ("M16 8GL", "0161 861 9806", "01618619806"),
            "man-one-ymca-bishops-stortford": ("CM23 2EX", "01279 838 068", "01279838068"),
            "man-roundabout-hostel": ("S2 4TF", "0114 258 9829", "01142589829"),
        }
        for i in self.IDS:
            pc, phone, tel = expect[i]
            self.assertEqual(manual[i]["postcode"], pc)
            self.assertEqual(manual[i]["phone"], phone)
            self.assertTrue(manual[i]["groups"] or manual[i].get("who_for") == "Not stated")  # 1 Nov: Dean option A, unread groups reset to Not stated
            self.assertEqual(verified[i]["phone"], phone)
            self.assertEqual(verified[i]["postcode"], pc)
            self.assertTrue(verified[i]["evidence_url"] and verified[i]["quote"])
            self.assertIn(i, approved)
            self.assertEqual(base[i]["phone"], phone)
            self.assertEqual(base[i]["tel"], tel)
            self.assertEqual(base[i]["layer"], "shelters")
            self.assertNotIn("council_phone", base[i])
            self.assertEqual(live[i]["postcode"], pc)
            self.assertEqual(live[i]["phone"], phone)
            self.assertEqual(live[i]["tel"], tel)
            self.assertEqual(live[i]["tier"], "verified")
            self.assertTrue(live[i]["verified"])
            r = R.check(manual[i], verified[i], _page(verified[i]), verified[i]["evidence_url"])
            self.assertTrue(r["ok"], (i, r))


if __name__ == "__main__":
    unittest.main()
