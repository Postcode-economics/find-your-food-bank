"""HUG Safe Space, Bexhill (bexhillhug.org.uk).

The cross-check used to keep only the 'Saturday New Opening Hours' line (Sat 13:00-15:00)
and drop the Monday and Thursday breakfast in the earlier opening-hours block. Verified
hours are Mon and Thu 08:30-11:30 plus Sat 13:00-15:00. Only that wrong Sat-only table
is blocked, not the whole page.
"""
import json, os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import discover as D

ID = "man-hug-safe-space-bexhill-rother-homelessness-unity-g"
KEY = "sh:" + ID
URL = "https://bexhillhug.org.uk/"
PC = "TN40 1JG"
# Two blocks, as on the live page: the breakfast line is not touching its clock times,
# and a later 'Saturday New Opening Hours' block repeats Saturday only. A broken footer
# time (the phone widget splits 11:30) must not replace the breakfast.
PAGE = (
    "Please pop in when we are open or email us at bexhillhug@gmail.com "
    "Opening Hours Monday and Thursday mornings 8:30 - 11:30 am for a delicious hot breakfast "
    "Saturday 1 pm - 3 pm for lunch We are located at: St Barnabas Church, Sea Road, Bexhill, TN40 1JG "
    "Charity No. 1182306 56a Haslam Crescent Bexhill-on-Sea East Sussex TN40 2QH Tel: 07881-642331 "
    "Opening Hours at HUG Monday and Thursday mornings for a delicious hot breakfast 8: 30 - 11 :30 am "
    "Saturday New Opening Hours 1pm to 3pm Get directions"
)
SAT = {"sat": [["13:00", "15:00"]]}
FULL = {"mon": [["08:30", "11:30"]], "thu": [["08:30", "11:30"]], "sat": [["13:00", "15:00"]]}
HOURS = {"Mon": "08:30 - 11:30", "Thu": "08:30 - 11:30", "Sat": "13:00 - 15:00"}


def _sig(st):
    return json.dumps(st, sort_keys=True)


def _published():
    text = open(os.path.join(ROOT, "shelters.js"), encoding="utf-8").read()
    items = json.loads(text[text.index("{"): text.rindex("}") + 1])["items"]
    return next(i for i in items if i["id"] == ID)


class HugBexhillHours(unittest.TestCase):
    def test_every_hours_block_is_read(self):
        """The Saturday heading on its own is Sat 13:00-15:00. The place's page also has the breakfast block."""
        sat_only = D.extract_times("Saturday New Opening Hours 1pm to 3pm. St Barnabas Church, Bexhill, TN40 1JG.", PC)
        self.assertEqual(sat_only["structured"], SAT)
        got = D.extract_times(PAGE, PC, name="HUG Safe Space")
        self.assertEqual(got["status"], "TIMES_FOUND")
        self.assertEqual(got["structured"], FULL)
        self.assertEqual(D.source_open_days([PAGE]), set(FULL))
        self.assertTrue(D.day_same_line(FULL, [PAGE]))
        ok, quote = D.live_hours_ok(FULL, PAGE, PC)
        self.assertTrue(ok, quote)
        self.assertIn("Monday and Thursday", quote)
        self.assertFalse(D.live_hours_ok(SAT, PAGE, PC)[0])
        st, new, why = D.confirm_times({"Sat": "13:00 - 15:00"}, [PAGE], PC, pages=[(URL, PAGE)])
        self.assertEqual(st, "changed", why)
        self.assertEqual(new["structured"], FULL)
        st, _, why = D.confirm_times(dict(HOURS), [PAGE], PC, pages=[(URL, PAGE)])
        self.assertEqual(st, "confirmed", why)

    def test_published_hours_and_exact_sat_only_lock(self):
        self.assertEqual(_published()["hours"], HOURS)
        self.assertFalse(_published().get("hours_protected"))
        manual = next(i for i in json.load(open(os.path.join(ROOT, "overrides", "shelters_manual.json"))) if i["id"] == ID)
        self.assertEqual(manual["hours"], HOURS)
        blocked = json.load(open(os.path.join(ROOT, "overrides", "times_auto_undone.json")))
        self.assertEqual(blocked[KEY], _sig(SAT))
        self.assertNotEqual(blocked.get(KEY), _sig(FULL))
        ks = json.load(open(os.path.join(ROOT, "overrides", "known_sources.json")))
        self.assertNotIn(ID, ks.get("skip") or {})
        self.assertNotIn(URL, ks.get("skip") or {})
        item = {"id": ID, "name": "HUG Safe Space", "postcode": PC, "website": URL, "hours": dict(HOURS)}
        home = {"final_url": URL}
        seen_sat = {KEY: {"sig": _sig(SAT), "source_url": URL, "run_at": "2026-11-01T03:43:22+00:00"}}
        why = D.times_gate_reasons(item, "sh", "hours",
                                   {"status": "TIMES_FOUND", "structured": dict(SAT), "raw": "Saturday 1pm to 3pm"},
                                   [PAGE], home, seen_sat, blocked, True, "2026-11-02T12:00:00+00:00")
        self.assertIn("this change was undone by Dean; not re-applied", why)
        self.assertFalse(any("known skip" in w for w in why), why)
        seen_full = {KEY: {"sig": _sig(FULL), "source_url": URL, "run_at": "2026-11-01T03:43:22+00:00"}}
        why_full = D.times_gate_reasons(item, "sh", "hours",
                                        {"status": "TIMES_FOUND", "structured": dict(FULL), "raw": "Monday and Thursday 8:30 - 11:30 am | Saturday 1pm to 3pm"},
                                        [PAGE], home, seen_full, blocked, True, "2026-11-02T12:00:00+00:00")
        self.assertNotIn("this change was undone by Dean; not re-applied", why_full)
        self.assertFalse(any("known skip" in w for w in why_full), why_full)


if __name__ == "__main__":
    unittest.main()
