"""Hermetic tests for day-centre candidate sources. No network. Nothing is published."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import day_centres as D
import follow_through as F

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "day_centres")


def read(name):
    return open(os.path.join(FIX, name), encoding="utf-8").read()


class Parse(unittest.TestCase):
    def test_day_centre_page_keeps_the_day_centre_not_the_hostel(self):
        rows = D.parse_council_page(read("listing.html"), "https://example.gov.uk/housing/day-centres", "Lambeth")
        names = [r["name"] for r in rows]
        self.assertTrue(any("Spires" in n for n in names))
        self.assertFalse(any("Night shelter" in n or "hostel" in n.lower() for n in names))
        self.assertTrue(rows[0]["day_time_quote"])
        self.assertFalse(rows[0]["publish"])
        for k in F.PHONE_KEYS:
            self.assertNotIn(k, rows[0])

    def test_rough_sleeping_page_only_keeps_day_centre_blocks(self):
        rows = D.parse_council_page(read("rough.html"), "https://example.gov.uk/housing/rough-sleeping", "Southwark")
        self.assertEqual(len(rows), 1)
        self.assertIn("Manna", rows[0]["name"])
        self.assertIn("SE1 3QP", rows[0]["postcode"])

    def test_unrelated_page_is_ignored(self):
        self.assertEqual(D.parse_council_page(read("listing.html"), "https://example.gov.uk/council-tax"), [])

    def test_sitemap_filter(self):
        locs = D.filter_urls(D.sitemap_locs(read("sitemap.xml")))
        self.assertEqual(locs, ["https://example.gov.uk/housing/day-centres-rough-sleepers"])

    def test_homeless_link_search_slugs(self):
        self.assertEqual(D.parse_homeless_link_search(read("hl_search.html")), ["spires-day-centre"])

    def test_homeless_link_service_is_a_held_candidate(self):
        row = D.candidate_from_service("spires-day-centre", read("hl_service.html"), "https://homeless.org.uk/homeless-england/service/spires-day-centre/")
        self.assertEqual(row["source"], "Homeless Link day centre category")
        self.assertFalse(row["publish"])
        self.assertTrue(row["day_time_quote"])
        self.assertNotIn("phone", row)


class Hold(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "logs"))
        os.makedirs(os.path.join(self.d, "reports"))
        os.makedirs(os.path.join(self.d, "overrides"))
        open(os.path.join(self.d, "shelters.js"), "w").write('x={"items":[{"id":"keep"}]};')

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_held_until_the_label_exists_and_shelters_untouched(self):
        doc = D.collect_pages(
            [{"url": "https://example.gov.uk/housing/day-centres", "html": read("listing.html"), "council": "Lambeth"}],
            self.d, "2026-10-31", label_ready_fn=lambda: False,
            hl_services=[("spires-day-centre", read("hl_service.html"), "https://homeless.org.uk/homeless-england/service/spires-day-centre/")])
        self.assertFalse(doc["label_ready"])
        self.assertGreaterEqual(len(doc["candidates"]), 2)
        self.assertTrue(all(c["publish"] is False and c["label"] == "" for c in doc["candidates"]))
        md = open(os.path.join(self.d, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertIn("Day centre candidates", md)
        self.assertIn("Spires", md)
        self.assertFalse(os.path.exists(os.path.join(self.d, "reports", "verified_new_places.json")))
        self.assertIn('"id":"keep"', open(os.path.join(self.d, "shelters.js"), encoding="utf-8").read().replace(" ", ""))

    def test_label_ready_still_does_not_publish(self):
        D.collect_pages(
            [{"url": "https://example.gov.uk/housing/day-centres", "html": read("listing.html"), "council": "Lambeth"}],
            self.d, "2026-10-31", label_ready_fn=lambda: True)
        doc = json.load(open(os.path.join(self.d, "logs", "day_centre_candidates.json")))
        self.assertTrue(all(c["publish"] is False for c in doc["candidates"]))
        self.assertTrue(all(c["label"] == "Day centre" for c in doc["candidates"]))
        prop = json.load(open(os.path.join(self.d, "reports", "verified_new_places.json")))
        self.assertTrue(prop["places"])
        self.assertTrue(all(p["layer"] == "day_centres" for p in prop["places"]))
        for p in prop["places"]:
            for k in F.PHONE_KEYS:
                self.assertNotIn(k, p)
        self.assertFalse(os.path.exists(os.path.join(self.d, "overrides", "shelters_verified.json")))
        self.assertIn('"id":"keep"', open(os.path.join(self.d, "shelters.js"), encoding="utf-8").read().replace(" ", ""))

    def test_collect_uses_the_fixture_fetcher_only(self):
        calls = []
        sitemap = "https://example.gov.uk/sitemap.xml"
        page_url = "https://example.gov.uk/housing/day-centres-rough-sleepers"
        hl = "https://homeless.org.uk/homeless-england/?query=day+centre&service_types=day-centre&page=1"
        service = "https://homeless.org.uk/homeless-england/service/spires-day-centre/"
        pages = {
            sitemap: {"http": 200, "final_url": sitemap, "html": read("sitemap.xml")},
            page_url: {"http": 200, "final_url": page_url, "html": read("listing.html")},
            hl: {"http": 200, "final_url": hl, "html": read("hl_search.html")},
            service: {"http": 200, "final_url": service, "html": read("hl_service.html")},
        }

        def f(u):
            calls.append(u)
            return pages.get(u, {"http": 404, "final_url": u, "html": ""})
        doc = D.collect(self.d, fetcher=f, day="2026-10-31",
                        councils=[{"name": "Example", "site": "https://example.gov.uk"}],
                        page_cap=5, council_cap=1, hl_pages=1, label_ready_fn=lambda: False, gap=0)
        self.assertTrue(any("day-centres" in u for u in calls))
        self.assertTrue(any("service_types=day-centre" in u for u in calls))
        self.assertTrue(any(c["source"].startswith("Homeless Link") for c in doc["candidates"]))
        self.assertTrue(any(c["source"].startswith("council") for c in doc["candidates"]))
        self.assertTrue(all(c["publish"] is False for c in doc["candidates"]))


class Slice(unittest.TestCase):
    def test_rotates_and_caps(self):
        councils = [{"name": "A"}, {"name": "B"}, {"name": "C"}, {"name": "D"}]
        self.assertEqual([c["name"] for c in D.council_slice(councils, "2026-01-01", 2)], ["A", "B"])
        self.assertEqual(len(D.council_slice(councils, "2026-01-02", 2)), 2)


if __name__ == "__main__":
    unittest.main()
