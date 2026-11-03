"""A SWEP page that confirms a shelter or emergency provision is open puts that place on the map.

The existing wording check still decides 'active'. Each place on a page is judged on its own.
No verified phone stays held. A hold is not a skip list and not a freeze: the next run can publish it.
The pin is the blue shelter house pin, labelled Severe weather shelter (SWEP).
"""
import datetime, json, os, shutil, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import swep_live as L
import common

NOW = "2026-11-03"
URL = "https://www.arun.gov.uk/swep"
PAGE = (
    "SWEP is currently active in Arun. "
    "Emergency accommodation is open tonight at St Mary's Church, 1 High Street, Littlehampton, BN17 5AA, "
    "from 8pm to 8am, for people sleeping rough. Walk-in, no referral needed. Wheelchair accessible. Call 01903 737500. "
    "The night shelter at River Hall, 2 Quay Street, BN17 6BB, is also open from 8pm to 8am. "
    "The day centre at Clock Tower, 3 Sea Road, BN17 7CC, is open in the daytime from 9am to 4pm. "
)


def geo(pc):
    return {"BN17 5AA": (50.81, -0.54), "BN17 6BB": (50.82, -0.53), "BN17 7CC": (50.83, -0.52)}.get(pc)


def page(text=PAGE, status="active", http=200, url=URL, **kw):
    base = {"council": "Arun District Council", "url": url, "http": http, "status": status,
            "_text": text, "site": "https://www.arun.gov.uk", "code": "ARU"}
    base.update(kw)
    return base


class Publish(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "logs"))
        os.makedirs(os.path.join(self.d, "scripts"))
        json.dump({"councils": [{"code": "ARU", "name": "Arun District Council", "site": "https://www.arun.gov.uk"}]},
                  open(os.path.join(self.d, "scripts", "sweep_sources.json"), "w"))
        common.write_js(os.path.join(self.d, "shelters.js"), "SHELTERS",
                        {"updated": "2026-11-02", "items": [{"id": "keep-me", "name": "Already here", "phone": "01903 000000", "tel": "01903000000"}],
                         "recently_closed": [], "sources": {}})

    def tearDown(self):
        shutil.rmtree(self.d, True)

    def items(self):
        return common.load_js(os.path.join(self.d, "shelters.js"), "SHELTERS")["items"]

    def test_confirmed_place_goes_live_with_details_pin_and_checked_date(self):
        r = L.apply([page()], run_day=NOW, root=self.d, geocoder=geo)
        self.assertEqual(r["live"], ["swep-arun-district-council-bn17-5aa"])
        row = next(i for i in self.items() if i["id"].startswith("swep-"))
        self.assertEqual(row["name"], "St Mary's Church")
        self.assertEqual(row["postcode"], "BN17 5AA")
        self.assertEqual((row["lat"], row["lng"]), (50.81, -0.54))
        self.assertEqual(row["tel"], "01903737500")
        self.assertEqual(row["phone"], "01903 737500")
        self.assertIn("People sleeping rough", row["groups"])
        self.assertEqual(row["wheelchair"], "yes")
        self.assertEqual(row["access_type"], "open_access")
        self.assertTrue(row["hours"])
        self.assertEqual(row["kind"], "severe_weather")
        self.assertEqual(row["label"], L.LABEL)
        self.assertEqual(row["badge"], L.BADGE)
        self.assertEqual(row["verified_on"], NOW)
        self.assertEqual(row["last_verified"], NOW)
        self.assertEqual(row["checked_on"], NOW)
        self.assertIn("keep-me", [i["id"] for i in self.items()])
        held = json.load(open(os.path.join(self.d, L.HELD_LOG)))
        reasons = {h["name"]: h["reason"] for h in held["held"]}
        self.assertEqual(reasons.get("River Hall"), "no verified phone")
        self.assertEqual(reasons.get("Clock Tower"), "day centre")
        self.assertNotIn("swep-arun-district-council-bn17-6bb", [i["id"] for i in self.items()])

    def test_no_phone_stays_held_and_the_sibling_still_publishes(self):
        text = (
            "SWEP is currently active. Emergency accommodation is open tonight at St Mary's Church, "
            "1 High Street, BN17 5AA, for people sleeping rough. Call 01903 737500. "
            "Emergency accommodation is also open at River Hall, 2 Quay Street, BN17 6BB, for people sleeping rough."
        )
        r = L.apply([page(text)], run_day=NOW, root=self.d, geocoder=geo)
        ids = [i["id"] for i in self.items() if i.get("swep_live")]
        self.assertEqual(ids, ["swep-arun-district-council-bn17-5aa"])
        self.assertTrue(any(h["reason"] == "no verified phone" and h["postcode"] == "BN17 6BB" for h in r["held"]))

    def test_conditional_wording_does_not_publish(self):
        import swep
        text = "SWEP is activated when the temperature falls below zero. Emergency accommodation at St Mary's Church, BN17 5AA. Call 01903 737500."
        self.assertNotEqual(swep.classify(text)[0], "active")
        r = L.apply([page(text, status="unknown")], run_day=NOW, root=self.d, geocoder=geo)
        self.assertEqual(r["live"], [])
        self.assertFalse(any(i.get("swep_live") for i in self.items()))

    def test_third_party_page_does_not_publish(self):
        r = L.apply([page(url="https://www.bbc.co.uk/news/swep", site="https://www.arun.gov.uk")], run_day=NOW, root=self.d, geocoder=geo)
        self.assertEqual(r["live"], [])
        self.assertTrue(any("own page" in h["reason"] for h in r["held"]))

    def test_provider_own_page_publishes(self):
        url = "https://www.stmaryshelter.org.uk/swep"
        r = L.apply([page(url=url, site="https://www.stmaryshelter.org.uk")], run_day=NOW, root=self.d, geocoder=geo)
        self.assertEqual(len(r["live"]), 1)
        row = next(i for i in self.items() if i.get("swep_live"))
        self.assertEqual(row["source_url"], url)

    def test_stood_down_removes_the_pin_and_a_later_run_can_put_it_back(self):
        L.apply([page()], run_day=NOW, root=self.d, geocoder=geo)
        self.assertTrue(any(i.get("swep_live") for i in self.items()))
        off = "SWEP has been stood down in Arun. St Mary's Church, BN17 5AA, is not open tonight."
        r = L.apply([page(off, status="not active")], run_day="2026-11-04", root=self.d, geocoder=geo)
        self.assertEqual(r["live"], [])
        self.assertFalse(any(i.get("swep_live") for i in self.items()))
        again = L.apply([page()], run_day="2026-11-05", root=self.d, geocoder=geo)
        self.assertEqual(again["live"], ["swep-arun-district-council-bn17-5aa"])
        row = next(i for i in self.items() if i.get("swep_live"))
        self.assertEqual(row["verified_on"], "2026-11-05")

    def test_unreachable_keeps_the_pin_and_the_checked_date(self):
        L.apply([page()], run_day=NOW, root=self.d, geocoder=geo)
        r = L.apply([page("ignored", status="unreachable", http=403)], run_day="2026-11-04", root=self.d, geocoder=geo)
        self.assertEqual(r["live"], [])
        row = next(i for i in self.items() if i.get("swep_live"))
        self.assertEqual(row["verified_on"], NOW)
        self.assertEqual(row["name"], "St Mary's Church")

    def test_hold_is_not_a_permanent_freeze(self):
        quiet = (
            "SWEP is currently active. Emergency accommodation is open tonight at St Mary's Church, "
            "1 High Street, BN17 5AA, for people sleeping rough."
        )
        first = L.apply([page(quiet)], run_day=NOW, root=self.d, geocoder=geo)
        self.assertEqual(first["live"], [])
        self.assertTrue(any(h["reason"] == "no verified phone" for h in first["held"]))
        self.assertFalse(os.path.exists(os.path.join(self.d, "overrides", "known_sources.json")))
        spoken = quiet + " Call 01903 737500."
        second = L.apply([page(spoken)], run_day="2026-11-04", root=self.d, geocoder=geo)
        self.assertEqual(second["live"], ["swep-arun-district-council-bn17-5aa"])

    def test_a_shop_number_is_not_a_verified_phone(self):
        text = (
            "SWEP is currently active. Emergency accommodation is open tonight at St Mary's Church, "
            "1 High Street, BN17 5AA, for people sleeping rough. Charity shop 01903 737500."
        )
        r = L.apply([page(text)], run_day=NOW, root=self.d, geocoder=geo)
        self.assertEqual(r["live"], [])
        self.assertTrue(any(h["reason"] == "no verified phone" for h in r["held"]))

    def test_refuge_and_foyer_stay_off(self):
        text = (
            "SWEP is currently active. The women's refuge at Harbour House, 9 Lane, BN17 5AA, is open. Call 01903 737500. "
            "The foyer at Young House, 4 Road, BN17 6BB, is housing for ages 16-25. Call 01903 737501."
        )
        r = L.apply([page(text)], run_day=NOW, root=self.d, geocoder=geo)
        self.assertEqual(r["live"], [])
        reasons = sorted(h["reason"] for h in r["held"])
        self.assertIn("women's refuge", reasons)
        self.assertIn("young people's housing", reasons)

    def test_checked_date_uses_the_card_format(self):
        L.apply([page()], run_day=NOW, root=self.d, geocoder=geo)
        row = next(i for i in self.items() if i.get("swep_live"))
        import subprocess
        node = r'''
const fs=require('fs'); const vm=require('vm');
const ctx={window:{}, document:{documentElement:{lang:'en'}}}; ctx.window=ctx; ctx.global=ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'), ctx);
const item=JSON.parse(process.argv[2]);
process.stdout.write(ctx.UFacts.checked(item)+'\n'+ctx.UFacts.typeOf('sh', item).join('|')+'\n'+ctx.UFacts.block('sh', item));
'''
        out = subprocess.run(["node", "-e", node, os.path.join(ROOT, "facts.js"), json.dumps(row)],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("Last checked", out.split("\n")[0])
        self.assertIn("3 Nov 2026", out.split("\n")[0])
        self.assertIn("Severe weather shelter (SWEP)", out)
        self.assertIn("People sleeping rough", out)
        self.assertIn("Walk-in", out)
        self.assertIn("Yes", out)


class WordingStaysStrict(unittest.TestCase):
    def test_general_description_still_not_active(self):
        import swep
        text = "The Severe Weather Emergency Protocol (SWEP) is in place to support people at risk of rough sleeping."
        self.assertNotEqual(swep.classify(text)[0], "active")


class MapPin(unittest.TestCase):
    def test_card_uses_the_shelter_house_pin_not_the_red_rest_centre(self):
        layers = open(os.path.join(ROOT, "layers.js"), encoding="utf-8").read()
        self.assertIn("i.kind==='severe_weather')return false", layers)
        self.assertIn("Severe weather shelter (SWEP)", layers)
        self.assertNotIn("open tonight", layers.lower())
        self.assertNotIn("#FF3B30", layers)
        emergency = open(os.path.join(ROOT, "emergency.js"), encoding="utf-8").read()
        self.assertIn("#FF3B30", emergency)
        self.assertIn("Rest centre (council-run)", emergency)
