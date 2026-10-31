"""Hermetic tests for held-near-cities and the city coverage watch. No network, no GitHub."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import city_watch as C

GLASGOW = {"name": "Glasgow", "lat": 55.8642, "lng": -4.2518}
LONDON = {"name": "London", "lat": 51.5074, "lng": -0.1278}
BRIGHTON = {"name": "Brighton and Hove", "lat": 50.8225, "lng": -0.1372}


class Held(unittest.TestCase):
    def test_outcode_counts_and_main_reason(self):
        codes = C.load_outcodes()
        warm = [
            {"id": "g", "postcode": "G1 1AA", "reason": "not on allowlist"},
            {"id": "g2", "postcode": "G1 2BB", "reason": "not on allowlist"},
            {"id": "e", "postcode": "E1 1AA", "reason": "not on allowlist", "autocheck": {"flags": ["no opening hours"]}},
        ]
        shelters = [{"id": "s", "postcode": "BT1 1AA", "reason": "not on allowlist"}]
        days = [{"id": "d", "postcode": "BN1 1AA", "why": "Day centre label is not on the map yet"}]
        cities = [c for c in C.CITIES if c["name"] in ("Glasgow", "London", "Belfast", "Brighton and Hove")]
        rows, _ = C.held_rows(warm, shelters, days, codes, cities)
        by = {r["city"]: r for r in rows}
        self.assertEqual(by["Glasgow"]["warm"], 2)
        self.assertEqual(by["Glasgow"]["reason"], "not on allowlist")
        self.assertEqual(by["London"]["warm"], 1)
        self.assertIn("no opening hours", by["London"]["reason"])
        self.assertEqual(by["Belfast"]["shelters"], 1)
        self.assertEqual(by["Brighton and Hove"]["day_centres"], 1)
        self.assertEqual(by["Glasgow"]["shelters"], 0)
        text = "\n".join(C.held_lines(rows, 3))
        self.assertIn("Glasgow: 2 warm spaces", text)
        self.assertLessEqual(text.count("\n"), 12)

    def test_section_written_and_replaced(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "logs"))
            os.makedirs(os.path.join(d, "reports"))
            json.dump([{"id": "g", "postcode": "G1 1AA", "reason": "not on allowlist"}], open(os.path.join(d, "logs", "warmspaces_pending.json"), "w"))
            open(os.path.join(d, "reports", "pending_dean.md"), "w").write("# Pending\n\n<!-- phone lock -->\n- kept\n<!-- /phone lock -->\n")
            C.write_held_section(d)
            C.write_held_section(d)
            md = open(os.path.join(d, "reports", "pending_dean.md"), encoding="utf-8").read()
            self.assertEqual(md.count("<!-- held near cities -->"), 1)
            self.assertIn("Glasgow:", md)
            self.assertIn("phone lock", md)
            self.assertIn("- kept", md)
        finally:
            shutil.rmtree(d)

    def test_summary_empty_without_pending(self):
        d = tempfile.mkdtemp()
        try:
            self.assertEqual(C.held_summary(d), "")
        finally:
            shutil.rmtree(d)


class Coverage(unittest.TestCase):
    def test_short_warm_spaces_and_no_shelter(self):
        warm = [{"id": "w", "lat": 55.86, "lng": -4.25, "name": "One"}]
        rows = C.coverage(warm, [], [], [GLASGOW, LONDON])
        by = {r["city"]: r for r in rows}
        self.assertEqual(by["Glasgow"]["warm"], 1)
        self.assertTrue(any("fewer than 5" in g for g in by["Glasgow"]["gaps"]))
        self.assertTrue(any("no shelter" in g for g in by["Glasgow"]["gaps"]))
        self.assertEqual(by["London"]["warm"], 0)

    def test_five_warm_spaces_and_a_shelter_is_ok(self):
        warm = [{"id": "w%d" % i, "lat": 51.51, "lng": -0.12} for i in range(5)]
        shelters = [{"id": "s", "lat": 51.50, "lng": -0.13}]
        rows = C.coverage(warm, shelters, [], [LONDON])
        self.assertEqual(rows[0]["gaps"], [])

    def test_day_centre_label_counts_as_a_day_centre(self):
        day = [{"id": "d", "lat": 50.82, "lng": -0.14, "label": "Day centre"}]
        rows = C.coverage([], [], day, [BRIGHTON])
        self.assertEqual(rows[0]["day_centres"], 1)
        self.assertFalse(any("no shelter" in g for g in rows[0]["gaps"]))
        self.assertTrue(any("fewer than 5" in g for g in rows[0]["gaps"]))

    def test_ended_places_are_not_counted(self):
        warm = [{"id": "old", "lat": 51.51, "lng": -0.12, "ended": True}]
        rows = C.coverage(warm, [], [], [LONDON])
        self.assertEqual(rows[0]["warm"], 0)

    def test_alert_opens_and_a_clear_run_resolves(self):
        opened, resolved = [], []
        rows = C.coverage([{"id": "w", "lat": 55.86, "lng": -4.25}], [], [], [GLASGOW])
        C.notify(rows, opener=lambda *a: opened.append(a), resolver=lambda *a: resolved.append(a))
        self.assertEqual(opened[0][0], "city-coverage")
        self.assertIn("Glasgow", opened[0][2])
        self.assertEqual(resolved, [])
        C.notify([{"city": "London", "warm": 5, "shelters": 1, "day_centres": 0, "gaps": []}],
                 opener=lambda *a: opened.append(a), resolver=lambda *a: resolved.append(a))
        self.assertEqual(resolved, [("city-coverage",)])

    def test_watch_returns_zero_when_the_alert_cannot_be_sent(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "reports"))
            os.makedirs(os.path.join(d, "logs"))
            open(os.path.join(d, "warmspaces.js"), "w").write('x={"items":[]};')
            open(os.path.join(d, "shelters.js"), "w").write('x={"items":[]};')

            def boom(*a, **k):
                raise RuntimeError("no token")
            self.assertEqual(C.run_watch(d, alert=True, opener=boom, resolver=boom), 0)
            self.assertTrue(os.path.exists(os.path.join(d, "reports", "city_coverage.md")))
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
