"""Rule 85 (Dean 3 Nov 2026): a place goes on at first listing with its verified hours, checked date,
card fields and type/icon already in the standard formats; nothing verified waits for a later pass."""
import json, os, re, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import common, hours_norm

KINDS = {None, "hostel", "day_centre", "young_people"}  # None = standard hostel/night shelter icon (layers.js)
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def _items(fn):
    t = open(os.path.join(ROOT, fn), encoding="utf-8").read()
    return json.JSONDecoder().raw_decode(t[t.index("{"):])[0]["items"]


class FirstListingPublishesVerifiedHours(unittest.TestCase):
    def test_new_place_with_verified_hours_publishes_them_normalised(self):
        fresh = [{"id": "man-test-new-hostel", "name": "Test House hostel", "hours": "", "postcode": "M1 1AA"}]
        ver = {"man-test-new-hostel": {"evidence_url": "https://example.org/test-house", "quote": "Test House hostel",
                                       "day_time_quote": "Open Monday to Friday 9am to 5pm",
                                       "hours": {"Monday": "9am-5pm", "Tuesday": "9am-5pm"}, "verified_on": "2026-11-03"}}
        pend = os.path.join(tempfile.mkdtemp(), "shelters_pending.json")
        pub, _, _ = common.verification_gate(fresh, None, ver, "2026-11-03", pend, recheck=False)
        self.assertEqual(len(pub), 1)
        self.assertTrue(pub[0]["hours"], "verified hours must go on with the first listing")
        hours_norm.apply(pub, "hours")
        self.assertEqual(pub[0]["hours"], hours_norm.normalise_hours(pub[0]["hours"]))
        self.assertTrue(ISO.match(pub[0]["verified_on"]))


class LiveListingsStandardFormats(unittest.TestCase):
    def test_every_shelter_has_valid_type_hours_format_and_dates(self):
        for x in _items("shelters.js"):
            self.assertIn(x.get("kind"), KINDS, x["id"])
            self.assertEqual(x.get("hours"), hours_norm.normalise_hours(x.get("hours")), x["id"])
            for k in ("verified_on", "last_verified", "checked_on", "last_checked"):
                if x.get(k): self.assertTrue(ISO.match(str(x[k])), (x["id"], k, x[k]))
            self.assertTrue(x.get("name"), x["id"])

    def test_verified_values_are_on_the_live_listing(self):
        """Missing info never blocks a listing, but every verified value is published with it."""
        for lay, fn in (("shelters", "shelters.js"), ("warmspaces", "warmspaces.js")):
            ver = json.load(open(os.path.join(ROOT, "overrides", lay + "_verified.json"), encoding="utf-8"))
            for x in _items(fn):
                v = ver.get(x["id"]) or {}
                for k in ("hours", "phone"):
                    if v.get(k): self.assertTrue(x.get(k), (lay, x["id"], k))

    def test_every_warm_space_hours_in_standard_format(self):
        for x in _items("warmspaces.js"):
            self.assertEqual(x.get("hours"), hours_norm.normalise_hours(x.get("hours")), x["id"])


PARITY = r"""() => [...document.querySelectorAll('#xlist .card.xsh')].map(c => ({id: c.dataset.id,
  rows: [...c.children].map(e => e.tagName + '.' + [...e.classList].filter(k => !['unk','shut','open','soon'].includes(k)).sort().join('.')).join('|'),
  labels: [...c.querySelectorAll('b')].map(e => e.textContent.trim()).filter(t => /:$/.test(t)).join('|'),
  sym: (c.querySelector('.xmkbox') || {dataset: {}}).dataset.sym || '',
  pill: ((c.querySelector('.xtop .utag') || {}).textContent || '').trim(),
  tel: !!c.querySelector('a[href^="tel:"]'), src: !!c.querySelector('.xsrc a'),
  checked: ((c.querySelector('.uchk') || {}).textContent || '').trim()}))"""
NEW = ("man-ss-",)


class FirstListingCardParityBrowser(unittest.TestCase):
    """A first-time listing renders identically in format to an established listing of the same type."""
    def test_new_cards_match_established_cards(self):
        try:
            from playwright.sync_api import sync_playwright
            sys.path.insert(0, os.path.join(ROOT, "tests"))
            import newlook_render as R
        except Exception as e:
            raise unittest.SkipTest(str(e))
        if not R.CHROME: raise unittest.SkipTest("no chrome")
        cards = {}
        with sync_playwright() as pw:
            b, p = R.open_page(pw, "dark", 390)
            try:
                p.click("#v3big [data-l=sh]"); p.wait_for_timeout(800)
                for q in ("M13 0AF", "FY1 2JF", "CB1 1BD", "BD1 1AA", "LS2 7EY", "WF8 1AA"):
                    p.fill("#q", q); p.press("#q", "Enter"); p.wait_for_timeout(1800)
                    p.evaluate("() => { if (window.showMoreX) showMoreX('sh'); }"); p.wait_for_timeout(300)
                    for c in p.evaluate(PARITY): cards[c["id"]] = c
            finally:
                b.close()
        new = [c for c in cards.values() if c["id"].startswith(NEW)]
        old = [c for c in cards.values() if not c["id"].startswith(NEW)]
        self.assertTrue(new and old, (len(new), len(old)))
        for n in new:
            self.assertIn(n["sym"], ("house", "sun", "youth"), n)
            self.assertTrue(n["pill"], n)
            self.assertTrue(n["tel"] and n["src"], n)
            self.assertRegex(n["checked"], r"\d{1,2} [A-Z][a-z]{2} 20\d\d", n)
            same = [o for o in old if o["sym"] == n["sym"]]
            self.assertTrue(same, ("no established card of type", n["sym"]))
            self.assertTrue(any(o["rows"] == n["rows"] and o["labels"] == n["labels"] for o in same),
                            ("new card differs from every established card of its type", n, same[0]))


if __name__ == "__main__":
    unittest.main()
