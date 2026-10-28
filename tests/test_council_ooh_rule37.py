"""Rule 37 (Dean, 27 Oct 2026): every council line on helpmap.uk is the council's own
out-of-hours/emergency number, for all councils, never a daytime or switchboard line.

Audit: /workspace/today/council_ooh_audit.csv (27 Oct 2026, every council line checked on the
council's own website). KNOWN_DAYTIME holds the daytime/switchboard numbers that audit replaced.
This test fails if any of them comes back as a council line, in the overrides or in the built
shelters.js / warmspaces.js, and if a new council line is added without an out-of-hours label.
"""
import json, os, re, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import shelter_contacts as sc

D = lambda s: re.sub(r"\D", "", s or "")

# number (digits only) -> council it was wrongly shown for (27 Oct audit, status 'fix')
KNOWN_DAYTIME = {
    "02087084002": "Redbridge Council housing (homeless tonight) (020 8708 4002)",
    "02392834989": "Portsmouth City Council Housing Needs (023 9283 4989)",
    "02085475000": "Royal Borough of Kingston upon Thames (020 8547 5000)",
    "01213031111": "Birmingham City Council (0121 303 1111)",
    "01164541004": "Leicester City Council (01164 541004)",
    "03001234212": "Cornwall Council (0300 123 4212)",
    "01179222050": "Bristol City Council (01179 222050)",
    "01204333333": "Bolton Metropolitan Borough Council (01204 333333)",
    "01912787878": "Newcastle City Council (01912 787878)",
    "03001232224": "Somerset Council (0300 123 2224)",
    "08082505705": "London Borough of Harrow (0808 250 5705)",
    "01424451077": "Hastings Borough Council (01424 451077)",
    "01263513811": "North Norfolk District Council (01263 513811)",
    "01226773555": "Barnsley Metropolitan Borough Council (01226 773555)",
    "01536859859": "North Northamptonshire Council (01536 859859)",
    "01332640000": "Derby City (01332 640000)",
    "01312002000": "City of Edinburgh Council (01312 002000)",
    "01274432111": "City of Bradford Metropolitan District Council (01274 432111)",
    "01516062000": "Wirral Council (0151 606 2000)",
    "01706647474": "Rochdale Metropolitan Borough Council (01706 647474)",
    "01634333333": "Medway Council (01634 333333)",
    "03451297777": "High Peak Borough Council (0345 129 7777)",
    "01612535000": "Bury Metropolitan Borough Council (01612 535000)",
    "01617933993": "Salford City Council (01617 933993)",
    "01962840222": "Winchester City Council (01962 840222)",
    "02083146000": "London Borough of Lewisham (020 8314 6000)",
    "01482300300": "Hull City Council (01482 300300)",
    "01483505050": "Guildford Borough Council (01483 505050)",
    "01392277888": "Exeter City Council (01392 277888)",
    "01132224444": "Leeds City Council (01132 224444)",
    "01620827827": "East Lothian Council (01620 827827)",
    "03456789044": "Shropshire Council (0345 678 9044)",
    "01708434343": "London Borough of Havering (01708 434343)",
    "03451400845": "Sefton Metropolitan Borough Council (0345 140 0845)",
    "01189373787": "Reading Borough Council (01189 373787)",
    "01215697474": "Sandwell Metropolitan Borough Council (0121 569 7474)",
    "03001024000": "Dundee City Council (0300 102 4000)",
    "01642393939": "Stockton-on-Tees Borough Council (01642 393939)",
    "02380285000": "New Forest District Council (023 8028 5000)",
    "02476376376": "Nuneaton and Bedworth Borough Council (024 7637 6376)",
    "01512333000": "Liverpool City Council (0151 233 3000)",
    "02076416000": "City of Westminster (020 7641 6000)",
    "08003896109": "South Norfolk District Council (0800 389 6109)",
    "01738476000": "Perth & Kinross Council Housing Options (01738 476000)",
    "03451550033": "Fife Council homeless line (03451 550033)",
    "01784446380": "Spelthorne Council Housing Options (01784 446380)",
    "01619122230": "Trafford Council Housing Options (0161 912 2230)",
    "01617932500": "Salford City Council (0161 793 2500)",
    "01617933993": "Salford City Council (0161 793 3993)",
    "01954713000": "South Cambridgeshire District Council (01954 713000)",
    "02380688165": "Eastleigh Borough Council (023 8068 8165)",
    "01642528389": "Stockton-on-Tees Borough Council (01642 528389)",
    "01612345000": "Manchester City Council (0161 234 5000)",
    "01914333000": "Gateshead Metropolitan Borough Council (0191 433 3000)",
    "01545570881": "Ceredigion County Council (01545 570881)",
    "03000300900": "Armagh City, Banbridge and Craigavon Borough Council (0300 030 0900)",
    "01422288002": "Calderdale Metropolitan Borough Council (01422 288002)"
}

# Cards whose council line is hidden (hide_council) until an out-of-hours number is found. Empty since Dean
# supplied Ceredigion, Armagh Banbridge & Craigavon and Calderdale on 27 Oct 2026; the mechanism stays tested.
HIDDEN = {}
HIDDEN_OLD = set()
UNRESOLVED = {}

OOH_LABEL = re.compile(r"out-of-hours", re.I)
# Exact labels Dean approved in PR 211 (live 27 Oct 17:52 GMT). Only these exact id+label pairs are accepted.
APPROVED_211_LABELS = {
    "ww-55473691": "Council homelessness emergency line",
    "ww-68895885": "Housing Executive (NIHE) out of hours",
    "scni-armagh": "Housing Executive (NIHE) out of hours",
    "scni-portadown": "Housing Executive (NIHE) out of hours",
}

# PR 211 (ooh-number-lock) is live (27 Oct 17:52 GMT). Its out-of-hours numbers must survive this branch.
# Kept as a name so the checks below still run on every other entry; these three are now checked too.
DEFERRED_211 = {}
LANDED_211 = {
    "ww-55473335": "07779 960994",  # Sefton, out-of-hours line for people sleeping rough
    "ww-55473691": "023 9282 4244",  # Portsmouth warm space
    "ww-68895885": "03448 920 908",  # Armagh, Banbridge and Craigavon: Housing Executive (NIHE)
}


def built(layer):
    t = open(os.path.join(ROOT, layer + ".js")).read()
    return json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]


def override_entries():
    for name in ("shelters_contacts.json", "warmspaces_contacts.json"):
        d = json.load(open(os.path.join(ROOT, "overrides", name)))
        for k, v in d.get("_councils", {}).items():
            yield name + ":_councils." + k, v
        for k, v in d.items():
            if isinstance(v, dict) and v.get("council_phone"):
                yield name + ":" + k, v


class Rule37(unittest.TestCase):
    def test_no_known_daytime_number_in_overrides(self):
        for where, e in override_entries():
            if where.split(":")[-1] in DEFERRED_211:
                continue
            for f in ("council_phone", "council_ooh"):
                self.assertNotIn(D(e.get(f)), KNOWN_DAYTIME, f"{where} {f}={e.get(f)} is a daytime/switchboard line")

    def test_no_known_daytime_number_on_cards(self):
        for layer in ("shelters", "warmspaces"):
            items = built(layer)
            sc.apply(items, sc.load(sc.WS if layer == "warmspaces" else sc.PATH))
            for x in items:
                if x["id"] in DEFERRED_211:
                    continue
                for f in ("council_phone", "council_ooh"):
                    self.assertNotIn(D(x.get(f)), KNOWN_DAYTIME, f"{layer}:{x['id']} {f}={x.get(f)} is a daytime/switchboard line")

    def test_every_council_line_is_labelled_out_of_hours(self):
        for where, e in override_entries():
            if where.split(":")[-1] in DEFERRED_211 or D(e["council_phone"]) in UNRESOLVED:
                continue
            if APPROVED_211_LABELS.get(where.split(":")[-1]) == e.get("council_label"):
                self.assertTrue(e.get("council_label_cy"), where)
                continue
            self.assertRegex(e.get("council_label", ""), OOH_LABEL, where)
            self.assertTrue(e.get("council_label_cy"), where)

    def test_armagh_sefton_and_portsmouth_warm_space_keep_211(self):
        d = json.load(open(os.path.join(ROOT, "overrides", "warmspaces_contacts.json")))
        cards = {x["id"]: x for x in built("warmspaces")}
        for i, n in LANDED_211.items():
            self.assertEqual(d[i]["council_phone"], n, i)
            self.assertEqual(d[i]["council_ooh"], n, i)
            self.assertEqual(cards[i]["council_phone"], n, i)
        self.assertEqual(d["ww-68895885"].get("council"), "Housing Executive (NIHE)")
        self.assertNotEqual(d["ww-55473335"]["council_phone"], "0345 140 0845")
        self.assertNotEqual(d["ww-55473691"]["council_phone"], "023 9282 2251")

    def test_hidden_cards_show_no_council_line(self):
        items = built("warmspaces")
        sc.apply(items, sc.load(sc.WS))
        seen = set()
        for x in items:
            if x["id"] in HIDDEN:
                seen.add(x["id"])
                self.assertFalse([k for k in x if k.startswith("council")], f"{x['id']} ({HIDDEN[x['id']]}) still has a council line")
            for f in ("council_phone", "council_ooh"):
                self.assertNotIn(D(x.get(f)), HIDDEN_OLD, f"warmspaces:{x['id']} {f}={x.get(f)}")
        self.assertEqual(seen, set(HIDDEN))
        d = json.load(open(os.path.join(ROOT, "overrides", "warmspaces_contacts.json")))
        for i in HIDDEN:
            self.assertTrue(d[i].get("hide_council"), i)
            self.assertFalse([k for k in d[i] if k.startswith("council_") or k == "council"], i)

    def test_hide_council_survives_a_refresh_with_stale_fields(self):
        x = {"id": "t", "tel": "1", "council": "X", "council_phone": "01422 288002", "council_label": "y"}
        sc.apply([x], {"t": {"hide_council": True}})
        self.assertFalse([k for k in x if k.startswith("council")])

    def test_manchester_gateshead_ooh(self):
        d = json.load(open(os.path.join(ROOT, "overrides", "warmspaces_contacts.json")))
        for i, n in (("ww-68980095", "0161 234 5001"), ("ww-55475981", "0161 234 5001"), ("ww-55473455", "0161 234 5001"), ("ww-69155575", "0191 477 0844"),
                     ("ww-57953124", "0300 456 3554"), ("ww-65437367", "0300 456 3554"), ("ww-65441920", "01422 288000")):
            self.assertEqual(d[i]["council_phone"], n)
            self.assertRegex(d[i]["council_label"], OOH_LABEL)
            self.assertTrue(d[i]["council_url"].startswith("https://www.manchester.gov.uk/") or d[i]["council_url"].startswith("https://www.gateshead.gov.uk/")
                            or d[i]["council_url"].startswith("https://www.ceredigion.gov.uk/") or d[i]["council_url"].startswith("https://www.armaghbanbridgecraigavon.gov.uk/")
                            or d[i]["council_url"].startswith("https://new.calderdale.gov.uk/"))
            self.assertNotIn("Housing Executive", d[i]["council_label"])
        self.assertIn("after 4.30pm weekdays, and weekends", d["ww-68980095"]["council_label"])

    def test_lists_are_consistent(self):
        self.assertFalse(set(KNOWN_DAYTIME) & set(UNRESOLVED))
        self.assertEqual(UNRESOLVED, {})  # every council line has a checked out-of-hours number (27 Oct 2026)
        self.assertGreaterEqual(len(KNOWN_DAYTIME), 40)



class Rule37VenuePhone(unittest.TestCase):
    """Stricter (Dean, 28 Oct 2026): no general council number as a venue's own `phone` either.
    The banned list is KNOWN_DAYTIME plus the council lines removed from venue phones on 28 Oct.
    The only allowances: a number Dean approved on 26 Oct that is waiting on his review list, and a
    current number whose replacement is waiting for his yes or no in PHONES-FOR-DEAN.md (no phone
    change without Dean's approval), and a current number whose replacement Dean has approved but
    another PR applies."""
    BANNED_PHONE = dict(KNOWN_DAYTIME, **{
        "01904554500": "City of York Council Housing Options (01904 554500)",
        "08000232692": "Manchester City Council Cost of Living Advice Line (0800 023 2692)",
    })
    AWAITING_DEAN = {"ww-68618605": "03001232224"}  # Bruton library, Dean-approved 26 Oct; on reports/pending_dean.md
    HELD_FOR_DEAN = {"osm-node-1533578890": "01904554500", "ww-55475981": "08000232692"}
    # James House: Dean approved 01904 553626 (28 Oct 05:35), applied by listings batch #239.
    APPROVED_ELSEWHERE = {"osm-way-169564851": ("01904554500", "01904553626")}

    def test_awaiting_dean_is_on_review_list(self):
        pd = open(os.path.join(ROOT, "reports", "pending_dean.md"), encoding="utf-8").read()
        m = re.search(r"(?s)<!-- council lines review -->.*?<!-- /council lines review -->", pd)
        self.assertTrue(m)
        for iid in self.AWAITING_DEAN:
            self.assertIn(iid, m.group(0))

    def test_held_for_dean_is_in_phones_for_dean(self):
        rows = [l for l in open(os.path.join(ROOT, "PHONES-FOR-DEAN.md"), encoding="utf-8").read().splitlines() if l.startswith("|")]
        for iid, num in self.HELD_FOR_DEAN.items():
            row = [r for r in rows if iid in r]
            self.assertEqual(len(row), 1, iid)
            self.assertIn(num, D(row[0].split("|")[2]), iid)

    def test_approved_elsewhere_shows_old_or_approved_number_only(self):
        sh = {x["id"]: x for x in built("shelters")}
        for iid, nums in self.APPROVED_ELSEWHERE.items():
            for f in ("phone", "tel"):
                self.assertIn(D(sh[iid].get(f)), nums, f"shelters:{iid} {f}={sh[iid].get(f)}")

    def _ok(self, iid, num):
        return (self.AWAITING_DEAN.get(iid) == num or self.HELD_FOR_DEAN.get(iid) == num
                or self.APPROVED_ELSEWHERE.get(iid, ("",))[0] == num)

    def test_no_banned_number_as_venue_phone_in_overrides(self):
        for name in ("shelters_contacts.json", "warmspaces_contacts.json"):
            d = json.load(open(os.path.join(ROOT, "overrides", name), encoding="utf-8"))
            for k, v in d.items():
                if not isinstance(v, dict): continue
                for f in ("phone", "phone_fix"):
                    n = D(v.get(f))
                    if n and not self._ok(k, n):
                        self.assertNotIn(n, self.BANNED_PHONE, f"{name}:{k} {f}={v.get(f)} is a general council number")
        b = json.load(open(os.path.join(ROOT, "overrides", "phone_baseline.json"), encoding="utf-8"))["listings"]
        for k, v in b.items():
            n = D(v.get("phone"))
            if n and not self._ok(k, n):
                self.assertNotIn(n, self.BANNED_PHONE, f"phone_baseline:{k} phone={v.get('phone')} is a general council number")

    def test_no_banned_number_as_venue_phone_on_cards(self):
        for layer in ("shelters", "warmspaces"):
            items = built(layer)
            sc.apply(items, sc.load(sc.WS if layer == "warmspaces" else sc.PATH))
            for x in items:
                for f in ("phone", "tel"):
                    n = D(x.get(f))
                    if n and not self._ok(x["id"], n):
                        self.assertNotIn(n, self.BANNED_PHONE, f"{layer}:{x['id']} {f}={x.get(f)} is a general council number")

if __name__ == "__main__":
    unittest.main()
