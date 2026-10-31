"""Hermetic tests: same-site follow-through and the verified-place proposal. No network."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover
import follow_through as F

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "follow_through")


def read(name):
    return open(os.path.join(FIX, name), encoding="utf-8").read()


def page(html, url, http=200):
    return {"http": http, "final_url": url, "html": html, "etag": "", "last_modified": "", "sha256": "x"}


class Quote(unittest.TestCase):
    def test_weekday_and_time_on_the_venue_page(self):
        q = F.quote_for_venue(discover.text_of(read("venue.html")), "Central Library", "G1 1AB")
        self.assertIsNotNone(q)
        self.assertIn("10:00", q.replace(" ", "") if False else q)
        self.assertRegex(q, r"Tue")

    def test_office_hours_are_not_evidence(self):
        self.assertIsNone(F.quote_for_venue(discover.text_of(read("office.html")), "Central Library", "G1 1AB"))

    def test_multi_venue_page_is_not_guessed(self):
        text = discover.text_of(read("council_index.html"))
        self.assertIsNone(F.quote_for_venue(text, "Central Library", "G1 1AB"))

    def test_generic_council_page_needs_follow(self):
        text = discover.text_of(read("council_index.html"))
        self.assertTrue(F.needs_follow("https://example.gov.uk/warm-spaces", text, "Central Library", "G1 1AB"))

    def test_own_site_without_times_is_not_crawled(self):
        text = "Reading Room, 1 High Street, AB1 2CD. Welcome."
        self.assertFalse(F.needs_follow("https://reading-room.example/visit", text, "Reading Room", "AB1 2CD"))


class Follow(unittest.TestCase):
    def fetcher(self, extra=None):
        home = "https://example.gov.uk/warm-spaces"
        venue = "https://example.gov.uk/libraries/central-library"
        pages = {
            home: page(read("council_index.html"), home),
            "https://example.gov.uk/sitemap.xml": page(read("sitemap.xml"), "https://example.gov.uk/sitemap.xml"),
            venue: page(read("venue.html"), venue),
        }
        if extra:
            pages.update(extra)
        calls = []

        def f(u):
            calls.append(u)
            return pages.get(u.rstrip("/"), page("", u, 404))
        f.calls = calls
        return f

    def test_link_or_sitemap_reaches_the_venue_page(self):
        bud = F.Budget(self.fetcher(), per_host=8, gap=0, sleep=lambda s: None, render=False)
        c = {"id": "ww-1", "name": "Central Library", "postcode": "G1 1AB", "website": "https://example.gov.uk/warm-spaces", "lat": 55.86, "lng": -4.25}
        hit = F.follow(c, "ws", bud, "2026-10-31")
        self.assertTrue(hit.get("passed"))
        self.assertEqual(hit["evidence_url"], "https://example.gov.uk/libraries/central-library")
        self.assertIn(hit["found_via"], ("link", "sitemap"))
        self.assertTrue(hit.get("day_time_quote"))
        for k in F.PHONE_KEYS:
            self.assertNotIn(k, hit)

    def test_search_form_on_the_same_site(self):
        home = "https://example.gov.uk/venues"
        found = "https://example.gov.uk/search?q=Central+Library"
        pages = {
            home: page(read("search_home.html"), home),
            "https://example.gov.uk/sitemap.xml": page("<urlset></urlset>", "https://example.gov.uk/sitemap.xml"),
            found: page(read("venue.html"), "https://example.gov.uk/libraries/central-library"),
        }

        def f(u):
            return pages.get(u, page("", u, 404))
        bud = F.Budget(f, per_host=8, gap=0, sleep=lambda s: None, render=False)
        hit = F.follow({"id": "ww-2", "name": "Central Library", "postcode": "G1 1AB", "website": home}, "ws", bud, "2026-10-31")
        self.assertTrue(hit.get("passed"))
        self.assertEqual(hit["found_via"], "search")

    def test_render_used_when_the_html_is_empty(self):
        home = "https://example.gov.uk/warm-spaces"
        venue = "https://example.gov.uk/libraries/central-library"
        rendered = {}

        def f(u):
            if u.rstrip("/") == home:
                return page(read("thin.html"), home)
            if u.endswith("sitemap.xml"):
                return page(read("sitemap.xml"), u)
            if u.rstrip("/") == venue:
                return page(read("thin.html"), venue)
            return page("", u, 404)

        def render(u):
            rendered[u] = True
            if u.rstrip("/") == venue:
                return (200, venue, read("venue.html"))
            return (200, u, read("thin.html"))
        bud = F.Budget(f, per_host=8, gap=0, sleep=lambda s: None, render=render)
        hit = F.follow({"id": "ww-3", "name": "Central Library", "postcode": "G1 1AB", "website": home}, "ws", bud, "2026-10-31")
        self.assertTrue(rendered.get(venue))
        self.assertTrue(hit.get("passed"))

    def test_host_budget_stops_and_asks_for_a_retry(self):
        bud = F.Budget(self.fetcher(), per_host=1, gap=0, sleep=lambda s: None, render=False)
        hit = F.follow({"id": "ww-4", "name": "Central Library", "postcode": "G1 1AB", "website": "https://example.gov.uk/warm-spaces"}, "ws", bud, "2026-10-31")
        self.assertFalse(hit.get("passed"))
        self.assertTrue(hit.get("retry"))
        self.assertLessEqual(bud.counts.get("example.gov.uk", 0), 1)

    def test_off_site_redirect_is_not_evidence(self):
        home = "https://example.gov.uk/warm-spaces"
        def f(u):
            if "sitemap" in u:
                return page("<urlset></urlset>", u)
            return page(read("venue.html"), "https://other.example/central-library")
        bud = F.Budget(f, per_host=8, gap=0, sleep=lambda s: None, render=False)
        hit = F.follow({"id": "ww-5", "name": "Central Library", "postcode": "G1 1AB", "website": home}, "ws", bud, "2026-10-31")
        self.assertFalse(hit.get("passed"))


class Proposal(unittest.TestCase):
    def test_discovery_records_a_proposal_and_does_not_publish(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "logs"))
            os.makedirs(os.path.join(d, "reports"))
            home = "https://example.gov.uk/warm-spaces"
            venue = "https://example.gov.uk/libraries/central-library"
            pages = {
                home: page(read("council_index.html"), home),
                "https://example.gov.uk/sitemap.xml": page(read("sitemap.xml"), "https://example.gov.uk/sitemap.xml"),
                venue: page(read("venue.html"), venue),
            }
            def f(u):
                return pages.get(u.rstrip("/"), page("<html><body>" + ("x " * 80) + "</body></html>", u, 404))
            c = {"id": "ww-lib", "name": "Central Library", "postcode": "G1 1AB", "lat": 55.86, "lng": -4.25,
                 "website": home, "directory": "Warm Welcome", "source_url": "https://www.warmwelcome.uk/space?l=1"}
            unv = {}
            log_path = os.path.join(d, "logs", "warmspaces_discovery.json")
            add, log = discover.discover_layer([c], [], "ws", "2026-10-31", unv, log_path, fetcher=f, threads=1,
                                               geocoder=lambda pcs: {p: (55.86, -4.25) for p in pcs})
            self.assertEqual(add, [])
            self.assertEqual(unv, {})
            prop = json.load(open(os.path.join(d, "reports", "verified_new_places.json"), encoding="utf-8"))
            self.assertEqual(len(prop["places"]), 1)
            place = prop["places"][0]
            self.assertEqual(place["id"], "ww-lib")
            self.assertEqual(place["evidence_url"], venue)
            self.assertTrue(place["day_time_quote"])
            for k in F.PHONE_KEYS:
                self.assertNotIn(k, place)
            self.assertFalse(os.path.exists(os.path.join(d, "overrides", "warmspaces_verified.json")))
            self.assertIn("ww-lib", log.get("verified_proposals") or [])
        finally:
            shutil.rmtree(d)

    def test_merge_keeps_earlier_places_and_drops_phone_fields(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "reports"))
            json.dump({"generated": "2026-10-30", "places": [{"id": "old", "name": "Old", "evidence_url": "https://a.example/", "day_time_quote": "Monday 9am - 10am"}]},
                      open(os.path.join(d, "reports", "verified_new_places.json"), "w"))
            F.merge_proposal([{"passed": True, "id": "new", "name": "New", "layer": "warmspaces", "evidence_url": "https://b.example/",
                               "day_time_quote": "Tuesday 10am - 12pm", "phone": "07000000000", "council_phone": "01000000000"}], d, "2026-10-31")
            places = json.load(open(os.path.join(d, "reports", "verified_new_places.json")))["places"]
            self.assertEqual([p["id"] for p in places], ["new", "old"])
            self.assertNotIn("phone", places[0])
            self.assertNotIn("council_phone", places[0])
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
