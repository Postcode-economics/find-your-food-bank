"""Listings batch #239, 28 Oct 2026 09:30: own-site fixes, same on both reads, each with its source URL and an undo entry.
- margate (reports/unknown-phones.csv): phone 01843 793838 -> 07948 439002, website -> https://mifood.co.uk/ (site moved).
- salisbury/tidworth (reports/unsure-resolved.csv): St Michael's Church Hall, St Michael's Avenue, Tidworth SP9 7EA, pin on SP9 7EA, Wed 14:30-16:30.
- selby-centre (reports/unsure-resolved.csv): Thursday 2pm-4pm, ticket from Reception on the day (old times were reception hours).
Nothing else from those reports is applied: Wareham, Risca, Stretham, Southend, West Cheshire and West Northumberland are held for Dean."""
import csv, json, os, re, sys, unittest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
dg = lambda s: re.sub(r"\D", "", s or "")
def items():
    t = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
    return {i["id"]: i for i in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}
def log(i, kind):
    return [c for c in J("logs/listings_batch_28oct.json")["changes"] if c["id"] == i and c["kind"] == kind and c["at"] == "2026-10-28T09:30Z"]

class Margate(unittest.TestCase):
    def test_phone_and_website(self):
        x = items()["margate"]
        self.assertEqual((x["phone"], x["tel"]), ("07948439002", "07948439002")); self.assertEqual(x["website"], "https://mifood.co.uk/")
        self.assertNotIn("01843793838", json.dumps(x)); self.assertNotIn("mifoodbank.org", x["website"])
        self.assertEqual(J("overrides/phones.json")["margate"], "07948439002")
        self.assertEqual(J("overrides/phone_baseline.json")["listings"]["margate"]["phone"], "07948439002")
        src = J("overrides/phone_sources.json")["margate"]
        self.assertEqual((dg(src["phone"]), src["source"]), ("07948439002", "https://mifood.co.uk/")); self.assertTrue(src["own_page"])
        self.assertEqual(J("overrides/foodbank_websites.json")["margate"]["url"], "https://mifood.co.uk/")
        import phone_rule
        self.assertEqual(phone_rule.phones_to_apply(J("overrides/phones.json"), J("overrides/phone_sources.json"), J("overrides/phone_holds.json")).get("margate"), "07948439002")
    def test_logged_with_undo(self):
        p, = log("margate", "phone"); w, = log("margate", "website")
        self.assertEqual((p["old"], p["new"], p["source"]), ("01843793838", "07948439002", "https://mifood.co.uk/"))
        self.assertEqual(p["undo"]["set"]["phone"], "01843793838")
        self.assertEqual((w["new"], w["undo"]["set"]["website"]), ("https://mifood.co.uk/", "https://www.mifoodbank.org"))
    def test_exports(self):
        r = {x["id"]: x for x in csv.DictReader(open(os.path.join(ROOT, "export", "foodbanks.csv"), encoding="utf-8", newline=""))}["margate"]
        self.assertEqual((r["phone"], r["website"]), ("07948439002", "https://mifood.co.uk/"))
        self.assertIn("07948439002", open(os.path.join(ROOT, "data.js"), encoding="utf-8").read())

class Tidworth(unittest.TestCase):
    def test_new_address_pin_and_times(self):
        x = items()["salisbury/tidworth"]
        self.assertEqual(x["address"], "St Michael's Church Hall, St Michael's Avenue, Tidworth, SP9 7EA"); self.assertEqual(x["postcode"], "SP9 7EA")
        self.assertEqual((x["lat"], x["lng"]), (51.233938, -1.670096))  # SP9 7EA postcode centre (postcodes.io)
        self.assertEqual(x["opening_times"]["structured"], {"wed": [["14:30", "16:30"]]})
        f = J("overrides/foodbank_address_fixes.json")["salisbury/tidworth"]
        self.assertEqual((f["address"], f["postcode"], f["lat"], f["lng"]), (x["address"], "SP9 7EA", x["lat"], x["lng"]))
        self.assertNotIn("Nadder Road", json.dumps(x))
    def test_logged_with_undo(self):
        e, = log("salisbury/tidworth", "address")
        self.assertEqual(e["source"], "https://salisbury.foodbank.org.uk/locations/")
        self.assertEqual(e["undo"]["set"]["address"]["postcode"], "SP9 7QN"); self.assertEqual(e["new"]["postcode"], "SP9 7EA")
    def test_area_page(self):
        s = open(os.path.join(ROOT, "food-banks", "wiltshire", "index.html"), encoding="utf-8").read()
        self.assertIn("St Michael&#x27;s Church Hall, St Michael&#x27;s Avenue, Tidworth, SP9 7EA", s); self.assertNotIn("Nadder Road", s)

class Selby(unittest.TestCase):
    def test_thursday_times_and_ticket_notice(self):
        x = items()["selby-centre"]
        self.assertEqual(x["opening_times"]["structured"], {"thu": [["14:00", "16:00"]]}); self.assertEqual(x["opening_times"]["status"], "TIMES_FOUND")
        self.assertEqual(x["opening_times"]["source_url"], "https://www.selbytrust.co.uk/selby-foodhub")
        self.assertIn("ticket from Reception on the day", x["notice"]); self.assertEqual(x["times_status"], "confirmed")
        o = J("overrides/opening_times.json")["selby-centre"]
        self.assertEqual((o["status"], o["structured"]), ("TIMES_FOUND", {"thu": [["14:00", "16:00"]]}))
        from times import normalise
        self.assertEqual(normalise(o)["structured"], {"thu": [["14:00", "16:00"]]})  # what build.py publishes on the next refresh
        self.assertIn("ticket from Reception on the day", J("overrides/foodbank_notices.json")["selby-centre"]["notice"])
    def test_logged_with_undo(self):
        h, = log("selby-centre", "hours"); n, = log("selby-centre", "notice")
        self.assertEqual(h["source"], "https://www.selbytrust.co.uk/selby-foodhub")
        self.assertEqual(h["undo"]["set"]["opening_times"]["raw"], "Monday to Friday: 8.30am to 5pm | Saturday: 9am to 3pm")
        self.assertIsNone(n["undo"]["set"]["notice"])
    def test_area_page(self):
        s = open(os.path.join(ROOT, "food-banks", "haringey", "index.html"), encoding="utf-8").read()
        i = s.index('<div class="n">Selby Centre Foodbank</div>'); card = s[i:s.index("</li>", i)]
        self.assertIn("<td>Thu</td><td>14:00–16:00</td>", card); self.assertNotIn("08:30", card)

class NothingElseFromTheReports(unittest.TestCase):
    def test_held_rows_untouched(self):
        L = [c for c in J("logs/listings_batch_28oct.json")["changes"] if c["at"] == "2026-10-28T09:30Z"]
        self.assertEqual({c["id"] for c in L}, {"margate", "salisbury/tidworth", "selby-centre"})
        d = items()
        self.assertEqual(dg(d["southend"]["phone"]), "07926530327")
        for i in ("wareham", "risca", "southend", "west-cheshire", "west-northumberland"):
            self.assertFalse([c for c in L if c["id"] == i], i)

if __name__ == "__main__": unittest.main()
