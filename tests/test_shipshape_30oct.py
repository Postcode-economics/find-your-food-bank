"""Dean 30 Oct 2026: ShipShape as warm space at S2 4UR; IFAN food-bank candidate rejected."""
import json, os, sys, tempfile, unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

WS_ID = "sheff-shipshape-community-hub"
FB_ID = "ifan-b595a2208802ba38bef45d-0"
HOURS = {"Tue": "11:00 - 13:00", "Wed": "09:30 - 11:00"}


def J(name):
    return json.load(open(os.path.join(ROOT, "overrides", name), encoding="utf-8"))


def fb_items():
    t = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
    return {i["id"]: i for i in json.loads(t[t.index("=") + 1 :].strip().rstrip(";"))["items"]}


def after_refresh(rows=None):
    from times import normalise
    import classify

    rows = (
        list(json.loads(open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read().split("=", 1)[1].strip().rstrip(";"))["items"])
        if rows is None
        else rows
    )
    times = J("opening_times.json")
    for i in rows:
        if i["id"] in times:
            i["opening_times"] = normalise(times[i["id"]])
    classify.classify(rows, ROOT)
    excl = J("foodbank_exclude.json").get("foodbanks", [])

    def excluded(i):
        host = (i.get("website") or "").split("//")[-1].split("/")[0].lower().removeprefix("www.")
        return any(
            i["id"] == e["slug"]
            or (not e.get("exact") and (i["id"].startswith(e["slug"] + "/") or (e.get("host") and host == e["host"])))
            for e in excl
        )

    return [i for i in rows if not excluded(i)]


class ShipShapeWarmSpace(unittest.TestCase):
    def test_manual_and_approval_overrides(self):
        man = {m["id"]: m for m in J("warmspaces_manual.json")}
        self.assertIn(WS_ID, man)
        hub = man[WS_ID]
        self.assertEqual(hub["name"], "ShipShape Community Hub")
        self.assertEqual(hub["postcode"], "S2 4UR")
        self.assertIn("Highfield Trinity Church", hub["address"])
        self.assertEqual(hub["hours"], HOURS)
        self.assertIn("Drop in, no referral needed", hub["notes"])
        self.assertEqual(hub["website"], "https://www.shipshape.website/service/food-hub")
        ver = J("warmspaces_verified.json")[WS_ID]
        self.assertTrue(ver.get("day_time_quote"))
        self.assertEqual(ver["hours"], hub["hours"])
        self.assertIn(WS_ID, J("approved_new_places.json")["warmspaces"])
        base = J("phone_baseline.json")["listings"][WS_ID]
        self.assertEqual(base["phone"], "0114 250 0222")
        self.assertEqual(base["tel"], "01142500222")
        self.assertEqual(base["layer"], "warmspaces")

    def test_build_verification_gate_publishes_from_overrides(self):
        """Same gate build_warmspaces.py uses: manual row + verified allowlist -> published item."""
        import common
        import place_lock

        man = next(m for m in J("warmspaces_manual.json") if m["id"] == WS_ID)
        ver = J("warmspaces_verified.json")
        pending = os.path.join(tempfile.mkdtemp(), "warmspaces_pending.json")
        pub, _, _ = common.verification_gate([dict(man)], None, ver, "2026-10-30", pending, recheck=False)
        self.assertEqual(len(pub), 1)
        i = pub[0]
        self.assertEqual(i["id"], WS_ID)
        self.assertEqual(i["hours"], HOURS)
        self.assertTrue(i.get("verified"))
        hands = place_lock.hands(ROOT, "warmspaces")
        self.assertEqual(hands[WS_ID]["hours"], HOURS)


class ShipShapeFoodBankReject(unittest.TestCase):
    REASON = "Dean 30 Oct 2026: listed as warm space at S2 4UR instead; IFAN S11 8AE address outdated"

    def test_not_on_food_bank_map(self):
        self.assertNotIn(FB_ID, fb_items())

    def test_stays_off_after_exclude_filter(self):
        self.assertNotIn(FB_ID, {i["id"] for i in after_refresh()})

    def test_exclude_rule(self):
        rule = next(e for e in J("foodbank_exclude.json")["foodbanks"] if e["slug"] == FB_ID)
        self.assertTrue(rule.get("exact"))
        self.assertEqual(rule["reason"], self.REASON)
        self.assertEqual(rule.get("host"), "shipshape.org.uk")

    def test_not_held_as_new_food_bank(self):
        pending = json.load(open(os.path.join(ROOT, "logs", "pending_dean.json"), encoding="utf-8"))
        ids = [x["id"] for x in pending.get("foodbanks", [])]
        self.assertNotIn(FB_ID, ids)


if __name__ == "__main__":
    unittest.main()
