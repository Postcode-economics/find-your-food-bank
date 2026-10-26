"""Opening times are one Mon–Sun table, 24-hour, Closed only when the source says so (Dean, 26 Oct 2026).

These checks read the published files. On main they fail: the food-bank table prints Closed for every
unlisted day, warm-space cards print a Not listed row per missing day, Next open uses am/pm, and two
warm spaces keep full day names and am/pm in the day table.
"""
import json, os, re, sys, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import hours_norm as H
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
FULLDAY = re.compile(r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tues|weds|thurs)\b", re.I)
AMPM = re.compile(r"\b(?:a\.?m\.?|p\.?m\.?)\b", re.I)
OLD_CLOSED = "(s[d]||[]).length?s[d].map(x=>x.join('–')).join(', '):'Closed'"

def load_js(name):
    s = open(os.path.join(ROOT, name), encoding="utf-8").read()
    return json.loads(s[s.index("{"):s.rindex("}") + 1])

def R(name):
    return open(os.path.join(ROOT, name), encoding="utf-8").read()

class Convert(unittest.TestCase):
    def test_clear_wording_becomes_a_table(self):
        c, err = H.try_convert("Wednesday morning from 10am – 12pm")
        self.assertIsNone(err)
        self.assertEqual(c["structured"], {"wed": [["10:00", "12:00"]]})
        self.assertEqual(c["closed"], [])
        c, err = H.try_convert("Tues 10am-12pm")
        self.assertEqual(c["structured"], {"tue": [["10:00", "12:00"]]})
        c, err = H.try_convert("Tue, Thu, Mon, Wed, Thu 10am-12pm")
        self.assertEqual(list(c["structured"]), ["mon", "tue", "wed", "thu"])
        self.assertEqual(set(c["structured"]), {"mon", "tue", "wed", "thu"})
        c, err = H.try_convert("Foodbank: Monday, Wednesday and Friday 10.30am - 12.30pm")
        self.assertEqual(list(c["structured"]), ["mon", "wed", "fri"])
        c, err = H.try_convert("Monday to Friday between 11am - 2pm")
        self.assertEqual(list(c["structured"]), DAYS[:5])
        c, err = H.try_convert("Tuesday & Thursday 9 am to 12 pm | Tuesday & Thursday 1 pm to 4 pm")
        self.assertEqual(c["structured"]["tue"], [["09:00", "12:00"], ["13:00", "16:00"]])

    def test_monthly_stays_on_the_row(self):
        c, err = H.try_convert("Wed 10am-12pm monthly")
        self.assertIsNone(err)
        self.assertEqual(c["structured"]["wed"], [["10:00", "12:00"]])
        self.assertEqual(c["notes"], {"wed": "Monthly"})

    def test_unclear_wording_is_not_converted(self):
        for text in (
            "Wednesday’s and 9 am to 3 pm",
            "Tuesday 2-5pm",
            "10 to 12 am",
            "12.30 - 3.30pm",
            "09:00 – 16:00pm",
            "10.00am-12.00am",
            "Monday to Friday between 12.30 - 3.30pm",
            "first Saturday of the month 9:30am - 11:30am",
            "Friday 10am - 12pm (except Good Friday)",
        ):
            conv, reason = H.try_convert(text)
            self.assertIsNone(conv, text)
            self.assertTrue(reason, text)

    def test_closed_only_when_the_word_is_there(self):
        self.assertEqual(H.scan_closed("Tuesdays 2-5pm", {"tue": [["14:00", "17:00"]]}), [])
        self.assertEqual(H.closed_days_for({"structured": {"tue": [["14:00", "17:00"]]}, "raw": "Tuesdays 2-5pm"}), [])
        raw = "Opening times Mon Closed Tue Closed Wed Closed Thu Closed Fri Closed Sat Closed Sun Closed "
        conv, err = H.try_convert(raw)
        self.assertTrue(conv.get("all_closed"))
        self.assertEqual(conv["closed"], DAYS)
        self.assertEqual(H.scan_closed("Mon 10:00-12:00 Tue Closed", {"mon": [["10:00", "12:00"]]}), ["tue"])

    def test_warm_space_cells(self):
        self.assertEqual(H.convert_day_dict({"Monday": "8:45am to 9:30am (Parents Group)"}),
                         {"Mon": "08:45 - 09:30 (Parents Group)"})
        self.assertEqual(H.convert_day_dict({"Monday": "9:30am to midday (Stay and Play)", "Wednesday": "9:30am to midday (Stay and Play)"}),
                         {"Mon": "09:30 - 12:00 (Stay and Play)", "Wed": "09:30 - 12:00 (Stay and Play)"})
        self.assertIsNone(H.try_convert("Open 24 hours, 365 days a year. Call 01642 800311 for a bed (agency referrals Mon-Fri 9am-5pm)")[0])

class Renderers(unittest.TestCase):
    def test_no_fake_closed_or_not_listed_rows(self):
        idx, layers, v3 = R("index.html"), R("layers.js"), R("v3.js")
        self.assertNotIn(OLD_CLOSED, idx)
        self.assertIn("Other days not listed, call before you go", idx)
        self.assertIn("dayClosed", idx)
        self.assertNotIn("'Not listed'", layers)
        self.assertIn("Other days not listed, call before you go", layers)
        self.assertNotIn("?'am':'pm'", v3)
        self.assertIn("st==='unknown'", layers)
        self.assertNotIn("h<12?'am':'pm'", v3)

    def test_unknown_has_no_week_and_no_times_checked(self):
        idx, layers = R("index.html"), R("layers.js")
        self.assertIn("return ''", idx)  # unknown food banks: no week rows from times()
        self.assertIn("const unk=", layers)
        self.assertIn("chk=!unk&&timesChecked", layers)
        self.assertNotIn("Times checked", idx.split("function times")[1].split("function showStamp")[0])

class Published(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fb = load_js("data.full.js")["items"]
        cls.sh = load_js("shelters.js")["items"]
        cls.ws = load_js("warmspaces.js")["items"]

    def _table_problems(self, where, keys, cells):
        problems = []
        order = WDAYS if keys and keys[0][:1].isupper() else DAYS
        if list(keys) != [d for d in order if d in keys]:
            problems.append("days out of order in " + where)
        if len(keys) != len(set(keys)):
            problems.append("duplicated days in " + where)
        blob = " ".join(str(c) for c in cells)
        if FULLDAY.search(blob) or any(FULLDAY.search(str(k)) for k in keys):
            problems.append("full day name in " + where)
        if AMPM.search(blob):
            problems.append("am/pm in " + where)
        return problems

    def test_day_tables_are_uniform(self):
        bad = []
        for it in self.fb:
            ot = it.get("opening_times") or {}
            st = ot.get("structured") or {}
            if ot.get("status") == "TIMES_FOUND" and st:
                bad += self._table_problems(it.get("name", ""), list(st), [x for rows in st.values() for pair in rows for x in pair])
                closed = ot.get("closed") or []
                if any(d not in DAYS for d in closed) or set(closed) & set(st):
                    bad.append("closed list overlaps open days: " + it.get("name", ""))
                derived = H.closed_days_for(ot) or []
                if closed != derived:
                    bad.append("closed days are not what the source says: %s stored %s source %s" % (it.get("name"), closed, derived))
        for label, items in (("shelter", self.sh), ("warm", self.ws)):
            for it in items:
                h = it.get("hours")
                if not isinstance(h, dict) or not h: continue
                bad += self._table_problems("%s %s" % (label, it.get("name")), list(h), list(h.values()))
        self.assertEqual(bad, [])

    def test_known_records(self):
        by = {i["id"]: i for i in self.fb}
        st = by["coventry/st-laurences-church"]["opening_times"]
        self.assertTrue(st.get("all_closed"))
        self.assertIn("sun closed", st.get("raw", "").lower())
        lib = next(i for i in self.fb if i.get("postcode") == "S66 9HR" and "Liberty" in i["name"])
        self.assertEqual(lib["opening_times"]["structured"], {"wed": [["10:00", "12:00"]]})
        self.assertNotIn("closed", lib["opening_times"])
        wind = next(i for i in self.fb if i.get("postcode") == "SL4 5PE")
        self.assertEqual(wind["opening_times"]["status"], "TIMES_TEXT_ONLY")
        marl = next(i for i in self.ws if i.get("postcode") == "B10 9NY" and "Marlborough" in i["name"])
        self.assertEqual(marl["hours"], {"Mon": "08:45 - 09:30 (Parents Group)"})
        greek = next(i for i in self.ws if "Greek" in i["name"])
        self.assertEqual(list(greek["hours"]), ["Mon", "Wed"])
        self.assertNotRegex(json.dumps(greek["hours"]), AMPM)

if __name__ == "__main__":
    unittest.main()
