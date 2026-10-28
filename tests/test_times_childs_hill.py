"""Rule 21 for opening times on both auto-apply paths (reviewer blocker, 28 Oct 2026): Child's Hill Food Bank has its own
site (overrides/own_location_pages.json "_food_bank_own_sites"), so times read on its host church page
(allsaintschildshill.com, its listing website) are held, even though that page names the food bank. Controls: the same
times on the food bank's own site still auto-apply, and a host church page still counts when the food bank has no own
site and the page names it.
Dean 28 Oct 13:45: a session held at a church still auto-applies when the food bank's own page (its own site or its own
locations page) gives the times. Only times read on the church or another page are held."""
import json, os, re, shutil, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import discover as D, times_finder as TF
from test_times_crosscheck_gate import FILL, OLD, ON, R1, R2, fetch, pg

FIX = os.path.join(ROOT, "tests", "fixtures", "phone_audit")
CHURCH_URL = "https://allsaintschildshill.com/childs-hill-food-bank/"
OWN_URL = "https://sites.google.com/childshillfoodbank.org/childs-hill-food-bank/about"
TIMES = "Open Saturday 10am - 12pm"
SAT = {"sat": [["10:00", "12:00"]]}
HELD = "host page does not count: the food bank has its own site (%s)" % OWN_URL


def saved(name, before):
    """A saved Child's Hill page with one session line added in its 'where are we' block (NW2 2TJ). Its donations section is left
    out: the refresh path rightly refuses hours under a donations heading, and this test is about whose page it is."""
    h = re.sub(r"(?s)<h3>Donations</h3>.*?</p>", "", open(os.path.join(FIX, name), encoding="utf-8").read())
    return h.replace(before, before + "</p><p>" + TIMES + ".</p><p>", 1).replace("</body>", "<p>%s</p></body>" % FILL)

CHURCH = saved("childshill_church.saved", "operates out of All Saints' Church, Child's Hill.")
OWN = saved("childshill_own.saved", "NW2 2TJ")
ITEM = {"id": "childs-hill", "type": "foodbank", "name": "Child's Hill Food Bank", "postcode": "NW2 2TJ", "website": CHURCH_URL}


class Config(unittest.TestCase):
    def test_childs_hill_own_site_is_listed(self):
        self.assertEqual(D.food_bank_own_sites().get("childs-hill"), [OWN_URL])
        self.assertTrue(D.on_site(OWN_URL, OWN_URL))
        self.assertTrue(D.on_site("https://sites.google.com/childshillfoodbank.org/childs-hill-food-bank/opening-times", OWN_URL))
        self.assertFalse(D.on_site(CHURCH_URL, OWN_URL))
        self.assertFalse(D.on_site("https://sites.google.com/view/another-org/about", OWN_URL))   # same shared host, another site


class Finder(unittest.TestCase):
    def setUp(self):
        cwd = os.getcwd(); d = tempfile.mkdtemp(); os.chdir(d); self.addCleanup(os.chdir, cwd); self.addCleanup(shutil.rmtree, d, True)
        for x in ("logs", "reports", "overrides"): os.makedirs(x)
        orig = (TF.polite, TF.known); self.addCleanup(lambda: (setattr(TF, "polite", orig[0]), setattr(TF, "known", orig[1])))
        TF.known = lambda: {"pages": {}, "skip": {}}

    def twice(self, item, html):
        TF.polite = lambda u, tries=3: (200, u, html) if not u.endswith(".xml") else (404, u, "")
        for now in ("2026-10-28T04:29:00+00:00", "2026-10-28T12:29:00+00:00"):
            ot, why = TF.generic([item], item["website"])[item["id"]]
            self.assertIsNotNone(ot, why); self.assertEqual(ot["structured"], SAT)
            log = {"found": {item["id"]: ot}}; TF.decide(log, [dict(item)], False, rules={"times_auto_apply": True}, now=now)
        cur = json.load(open("overrides/opening_times.json")) if os.path.exists("overrides/opening_times.json") else {}
        return log, cur

    def test_church_page_times_are_held(self):
        log, cur = self.twice(dict(ITEM), CHURCH)
        self.assertEqual(log["applied"], [])
        self.assertEqual(log["review"][0]["why"], [HELD])
        self.assertNotIn("childs-hill", cur)

    def test_church_venue_times_on_the_food_banks_own_site_auto_apply(self):
        self.assertIn("All Saints Church", OWN)   # the session is held at the church; the food bank's own page gives it
        log, cur = self.twice(dict(ITEM, website=OWN_URL), OWN)
        self.assertEqual(log["applied"], ["childs-hill"])
        self.assertEqual(cur["childs-hill"]["structured"], SAT)

    def test_control_church_page_counts_when_there_is_no_own_site(self):
        log, cur = self.twice(dict(ITEM, id="all-saints-fb"), CHURCH)
        self.assertEqual(log["applied"], ["all-saints-fb"])
        self.assertEqual(cur["all-saints-fb"]["structured"], SAT)


class RefreshGate(unittest.TestCase):
    def setUp(self): self.root = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.root, True)

    def twice(self, item, url, html):
        f = fetch({url: pg(html, final=url)})
        D.cross_check_times([dict(item)], "fb", "opening_times", f, state_root=self.root, rules=ON, run_at=R1)
        it = [dict(item)]
        return it, D.cross_check_times(it, "fb", "opening_times", f, state_root=self.root, rules=ON, run_at=R2)

    def test_church_page_times_are_held(self):
        it, log = self.twice(dict(ITEM, opening_times=dict(OLD)), CHURCH_URL, CHURCH)
        k = "childs-hill"
        self.assertEqual(log[k]["status"], "held_for_dean"); self.assertEqual(log[k]["held"], [HELD])
        self.assertEqual(it[0]["opening_times"], OLD)
        al = os.path.join(self.root, "reports", "times_auto_applied.json")
        self.assertFalse(os.path.exists(al) and json.load(open(al)))

    def test_church_venue_times_on_the_food_banks_own_site_auto_apply(self):
        it, log = self.twice(dict(ITEM, website=OWN_URL, opening_times=dict(OLD)), OWN_URL, OWN)
        self.assertEqual(log["childs-hill"]["status"], "changed"); self.assertTrue(log["childs-hill"]["auto_applied"])
        self.assertEqual(it[0]["opening_times"]["structured"], SAT)

    def test_control_church_page_counts_when_there_is_no_own_site(self):
        it, log = self.twice(dict(ITEM, id="all-saints-fb", opening_times=dict(OLD)), CHURCH_URL, CHURCH)
        self.assertEqual(log["all-saints-fb"]["status"], "changed")
        self.assertEqual(it[0]["opening_times"]["structured"], SAT)



RS_OWN = "https://riversidefoodbank.org.uk/"
RS_LOC = "https://riverside.foodbank.org.uk/locations/"
RS_CHURCH = "https://stmarys-riverside.example.org/foodbank/"
RS_PAGE = ("<html><body><h1>Riverside Foodbank: where we are</h1><p>St Mary's Church, 1 High St, AB1 2CD. Thursday 2pm - 4pm.</p>%s</body></html>" % FILL)
RS_PIN = {"id": "riverside/st-marys", "type": "location", "name": "Riverside Foodbank at St Mary's Church", "foodbank": "Riverside Foodbank",
          "postcode": "AB1 2CD", "opening_times": dict(OLD)}


class OwnLocationsPage(unittest.TestCase):
    """A food bank with its own site and its own locations page (on another host); a centre pin at a church."""
    def setUp(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True); self.root = os.path.join(d, "state"); os.makedirs(self.root)
        cfg = os.path.join(d, "own_location_pages.json")
        json.dump({"_food_bank_own_sites": {"riverside": RS_OWN}, "riverside": {"url": RS_LOC, "min_centres": 1}}, open(cfg, "w"))
        orig = D.FB_OWN_SITES; D.FB_OWN_SITES = cfg; self.addCleanup(setattr, D, "FB_OWN_SITES", orig)

    def test_own_pages_are_the_own_site_then_the_locations_page(self):
        own = D.food_bank_own_sites()
        self.assertEqual(own, {"riverside": [RS_OWN, RS_LOC]})
        for src in (RS_OWN + "opening-times", RS_LOC, RS_LOC + "st-marys/"):
            self.assertEqual(D.not_own_site_reason("riverside/st-marys", src, own), "", src)
            self.assertEqual(D.not_own_site_reason("riverside", src, own), "", src)
        self.assertEqual(D.not_own_site_reason("riverside/st-marys", RS_CHURCH, own),
                         "host page does not count: the food bank has its own site (%s)" % RS_OWN)

    def twice(self, website):
        f = fetch({website: pg(RS_PAGE, final=website)}); item = dict(RS_PIN, website=website)
        D.cross_check_times([dict(item)], "fb", "opening_times", f, state_root=self.root, rules=ON, run_at=R1)
        it = [dict(item)]
        return it, D.cross_check_times(it, "fb", "opening_times", f, state_root=self.root, rules=ON, run_at=R2)["riverside/st-marys"]

    def test_church_venue_times_on_the_own_locations_page_auto_apply(self):
        it, rec = self.twice(RS_LOC)
        self.assertEqual(rec["status"], "changed", rec); self.assertTrue(rec["auto_applied"])
        self.assertEqual(it[0]["opening_times"]["structured"], {"thu": [["14:00", "16:00"]]})

    def test_the_same_times_on_the_church_page_are_held(self):
        it, rec = self.twice(RS_CHURCH)
        self.assertEqual(rec["status"], "held_for_dean", rec)
        self.assertEqual(rec["held"], ["host page does not count: the food bank has its own site (%s)" % RS_OWN])
        self.assertEqual(it[0]["opening_times"], OLD)


if __name__ == "__main__": unittest.main()
