"""27 Oct council-line fixes (cards_report.csv): checked numbers survive every refresh via overrides.
Rule 37 (Dean, 27 Oct 2026): every council line is the council's own out-of-hours/emergency number."""
import json, os, re, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import shelter_contacts as sc

def items():
    t = open(os.path.join(ROOT, "warmspaces.js")).read(); d = json.loads(t[t.index("{"):t.rindex("}") + 1])
    sc.apply(d["items"], sc.load(sc.WS)); return {x["id"]: x for x in d["items"]}

class CouncilLines(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.it = items(); cls.ov = sc.load(sc.WS)
    def chk(self, i, phone, url, ooh=None):
        for src in (self.it[i], self.ov[i]):
            self.assertEqual(src.get("council_phone"), phone, i); self.assertEqual(src.get("council_url"), url, i)
            self.assertEqual(src.get("council_ooh"), ooh, i)
    def test_salford(self):
        self.chk("ww-57990409", "0161 794 8888", "https://www.salford.gov.uk/contacts/how-to-contact-us/how-to-phone-us/", "0161 794 8888")
        self.assertIn("out-of-hours", self.it["ww-57990409"]["council_label"])
    def test_south_cambs(self):
        for i in ("ww-63057583", "ww-63058939"):
            self.chk(i, "01253 501117", "https://www.scambs.gov.uk/contact-us", "01253 501117")
            self.assertIn("out-of-hours", self.it[i]["council_label"])
    def test_eastleigh(self):
        self.chk("ww-68923940", "023 8068 8000", "https://www.eastleigh.gov.uk/housing/housing-and-homelessness/homelessness-advice", "023 8068 8000")
    def test_bradford_not_complaints(self):
        self.chk("ww-57952231", "01274 381999", "https://www.bradford.gov.uk/housing/homelessness/i-have-nowhere-to-sleep-tonight/", "01274 381999")
    def test_stockton(self):
        self.chk("ww-55474433", "01642 524552", "https://www.stockton.gov.uk/homelessness", "01642 524552")
    def test_no_old_numbers_or_bad_spacing(self):
        bad = {"01617 933993", "01642 393939", "01164 541004", "01912 787878", "01179 222050", "01132 224444",
               "01312 002000", "01612 535000", "01619 122000", "01189 373787",
               # daytime lines (rule 37): never shown as the council line
               "0161 793 2500", "0161 793 3993", "01954 713000", "023 8068 8165", "01642 528389", "01274 432111"}
        for x in self.it.values():
            for f in ("council_phone", "council_ooh"):
                self.assertNotIn(x.get(f), bad, x["id"])
                # 01xx1 / 011x area codes must use 0xxx xxx xxxx spacing
                if x.get(f) and re.match(r"^01\d1|^011", x[f].replace(" ", "")):
                    self.assertRegex(x[f], r"^01\d\d \d{3} \d{4}$", x["id"])
        self.assertFalse(any("staff-email" in (x.get("council_url") or "") or "make-a-complaint" in (x.get("council_url") or "") for x in self.it.values()))

if __name__ == "__main__": unittest.main()
