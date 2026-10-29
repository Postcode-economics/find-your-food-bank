"""Regression: nine cross_check auto-applies from refresh bd388de (29 Oct 2026 12:45 UTC) must stay held."""
import hashlib, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover as D

R1, R2 = "2026-10-29T08:00:47+00:00", "2026-10-29T13:12:04+00:00"
ON = {"times_auto_apply": True}
FILL = " lorem ipsum" * 40
SIG = lambda st: json.dumps(st, sort_keys=True) if st else None


def gate(item, new, texts, url, old=None, run_at=R2):
    old = old if old is not None else item.get("opening_times")
    item = dict(item, opening_times=old)
    seen = {("fb:" + item["id"]): {"sig": SIG((new or {}).get("structured")), "source_url": url, "run_at": R1}}
    return D.times_gate_reasons(item, "fb", "opening_times", new, texts, {"final_url": url}, seen, {}, True, run_at, own_sites={})


def pg(html, url="https://example.org/"):
    return {"http": 200, "final_url": url, "html": html, "etag": "e", "last_modified": "",
            "sha256": hashlib.sha256(html.encode()).hexdigest()}


def fetch(pages):
    def f(u):
        for k, v in pages.items():
            if u.rstrip("/") == k.rstrip("/"):
                return v
        return {"http": 404, "final_url": u, "html": ""}
    return f


class NineGateReasons(unittest.TestCase):
    def test_bridgwater_skip_or_shrink(self):
        old = {"status": "TIMES_FOUND", "structured": {"mon": [["13:00", "15:30"]], "wed": [["13:00", "15:30"]], "fri": [["13:00", "15:30"]]},
               "raw": "Mon 13:00 - 15:30", "source_url": "https://bridgwater.foodbank.org.uk/locations/"}
        new = {"status": "TIMES_FOUND", "structured": {"mon": [["10:30", "13:30"]], "wed": [["10:30", "13:30"]], "fri": [["10:30", "13:30"]]},
               "raw": "Mon 10:30 - 13:30 Wed 10:30 - 13:30 Fri 10:30 - 13:30"}
        item = {"id": "bridgwater", "name": "Bridgwater Foodbank", "postcode": "TA6 4AB", "website": "https://bridgwater.foodbank.org.uk/"}
        why = gate(item, new, ["Bridgwater Foodbank TA6 4AB " + new["raw"]], "https://bridgwater.foodbank.org.uk/locations/", old)
        self.assertTrue(any("known skip" in w for w in why), why)

    def test_hereford_and_godalming_office_pattern(self):
        for iid, name, pc, raw in (
            ("hereford", "Hereford Foodbank", "HR4 9BX", "Monday to Friday 10:00 am - 12pm"),
            ("godalming-villages-community-store", "Godalming & Villages Community Store Foodbank", "GU7 1AB", "Monday - Friday 10am-12:30pm"),
        ):
            st = {d: [["10:00", "12:00" if iid == "hereford" else "12:30"]] for d in ("mon", "tue", "wed", "thu", "fri")}
            new = {"status": "TIMES_FOUND", "structured": st, "raw": raw}
            item = {"id": iid, "name": name, "postcode": pc, "website": "https://example.org/"}
            why = gate(item, new, [name + " " + pc + " food bank. " + raw], "https://example.org/contact")
            self.assertTrue(any("office/shop hours" in w or "known skip" in w for w in why), (iid, why))

    def test_weymouth_fewer_sessions(self):
        old = {"status": "TIMES_TEXT_ONLY", "structured": None, "raw": "TUESDAY: 6-30 pm | WEDNESDAY: 10 am - 12",
               "lines": ["TUESDAY: 6-30 pm", "WEDNESDAY: 10 am - 12"]}
        new = {"status": "TIMES_FOUND", "structured": {"thu": [["10:00", "12:00"]]}, "raw": "THURSDAY : 10 am - 12pm"}
        item = {"id": "salvation-army/weymouth", "name": "Weymouth", "postcode": "DT4 7PG", "website": "https://www.salvationarmy.org.uk/weymouth"}
        why = gate(item, new, ["Weymouth DT4 7PG food bank. " + new["raw"]], "https://www.salvationarmy.org.uk/weymouth", old)
        self.assertTrue(any("fewer sessions" in w for w in why), why)

    def test_sunderland_fewer_sessions_and_multi_centre(self):
        old = {"status": "TIMES_TEXT_ONLY", "structured": None,
               "raw": "Monday: 15:00-16:30 | Monday: 10:00-12:00",
               "lines": ["Monday: 15:00-16:30", "Monday: 10:00-12:00"]}
        new = {"status": "TIMES_FOUND", "structured": {"thu": [["09:00", "10:30"]]}, "raw": "Thursday 09:00-10:30"}
        item = {"id": "sunderland", "name": "Sunderland Foodbank", "postcode": "SR1 1AA", "website": "https://sunderlandfoodbank.org.uk/"}
        text = "Sunderland Foodbank SR1 1AA SR2 2BB SR3 3CC. " + new["raw"]
        why = gate(item, new, [text], "https://sunderlandfoodbank.org.uk/locations/", old)
        self.assertTrue(any("fewer sessions" in w for w in why), why)
        self.assertTrue(any("several centres" in w for w in why), why)

    def test_purley_fewer_sessions(self):
        old = {"status": "TIMES_FOUND", "structured": {"wed": [["10:00", "11:30"]], "thu": [["09:15", "12:45"]], "fri": [["09:00", "12:00"]]},
               "raw": "Wed | Thu | Fri"}
        new = {"status": "TIMES_FOUND", "structured": {"fri": [["09:00", "12:00"]]}, "raw": "Fridays 9am-12pm"}
        item = {"id": "purley/old-lodge-lane-baptist-church", "name": "Old Lodge Lane Baptist Church", "postcode": "CR8 3ND",
                "website": "https://www.purleyfoodhub.net/"}
        why = gate(item, new, ["Purley food hub CR8 1AA CR8 2BB CR8 3ND food bank. " + new["raw"]], "https://www.purleyfoodhub.net/get-help/", old)
        self.assertTrue(any("fewer sessions" in w or "fewer days" in w or "known skip" in w or "several centres" in w for w in why), why)

    def test_crescent_corsham_salford_blocked(self):
        cases = (
            ("crescent", "Crescent Foodbank", "BH8 8AA", {"sun": [["10:00", "11:00"]]}, "Sunday 10AM -11AM | Sundays 10am-11:00am"),
            ("corsham-churches", "Corsham Churches Foodbank", "SN13 0AA", {"tue": [["10:00", "12:00"]], "sat": [["10:00", "12:00"]]}, "Tuesday and Saturday 10am - 12pm"),
            ("salford-food-parcels", "Salford Food Parcels Foodbank", "M6 5AA", {"wed": [["10:00", "11:30"]]}, "Wednesday 10-11.30am"),
        )
        for iid, name, pc, st, raw in cases:
            new = {"status": "TIMES_FOUND", "structured": st, "raw": raw}
            item = {"id": iid, "name": name, "postcode": pc, "website": "https://example.org/"}
            why = gate(item, new, [name + " " + pc + " food bank. " + raw], "https://example.org/")
            self.assertTrue(any("known skip" in w for w in why), (iid, why))


class NineCrossCheckEndToEnd(unittest.TestCase):
    def test_weymouth_two_runs_stays_held(self):
        old = {"status": "TIMES_TEXT_ONLY", "structured": None, "raw": "TUESDAY: 6-30 pm | WEDNESDAY: 10 am - 12",
               "lines": ["TUESDAY: 6-30 pm", "WEDNESDAY: 10 am - 12"]}
        html = "<html><body><h1>Salvation Army Weymouth food bank</h1><p>DT4 7PG. THURSDAY : 10 am - 12pm.%s</body></html>" % FILL
        url = "https://www.salvationarmy.org.uk/weymouth"
        item = {"id": "salvation-army/weymouth", "name": "Weymouth", "postcode": "DT4 7PG", "website": url, "opening_times": dict(old)}
        root = tempfile.mkdtemp()
        f = fetch({url: pg(html, url)})
        D.cross_check_times([dict(item)], "fb", "opening_times", f, state_root=root, rules=ON, run_at=R1)
        log = D.cross_check_times([item], "fb", "opening_times", f, state_root=root, rules=ON, run_at=R2)
        self.assertEqual(log["salvation-army/weymouth"]["status"], "held_for_dean")
        self.assertEqual(item["opening_times"], old)


if __name__ == "__main__":
    unittest.main()
