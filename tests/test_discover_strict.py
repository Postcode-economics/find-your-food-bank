import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover as D
OK = "<html>House The Homeless night shelter, emergency accommodation for homeless people. 1 Main St BN1 1AA " + "x " * 200 + "</html>"
def fetch(u): return {"http": 200, "final_url": u, "html": OK, "etag": "", "last_modified": "", "sha256": "h"}
class T(unittest.TestCase):
    def go(self, c, kind="sh"):
        import tempfile; unv = {}
        add, log = D.discover_layer([c], [], kind, "2026-10-21", unv, os.path.join(tempfile.mkdtemp(), "l.json"), fetcher=fetch, threads=1, geocoder=lambda pcs: {p: (c["lat"], c["lng"]) for p in pcs})
        return add, log, unv
    def test_osm_only_never_added(self):
        add, log, unv = self.go({"id": "osm-node-7257703002", "name": "House The Homeless", "postcode": "BN1 1AA", "lat": 50.8, "lng": -0.1,
                                 "website": "https://housethehomeless.example/", "source": "OpenStreetMap"})
        self.assertFalse(add); self.assertFalse(unv); self.assertIn("OpenStreetMap-only", log["flagged"][0]["reasons"][0])
    def test_council_page_not_own_site(self):
        add, log, _ = self.go({"id": "hl-centrepoint-bradford-foyer", "name": "Centrepoint - Bradford Foyer", "postcode": "BN1 1AA", "lat": 53.8, "lng": -1.75,
                               "website": "https://www.bradford.gov.uk/housing/", "directory": "Homeless Link"})
        self.assertFalse(add); r = log["flagged"][0]["reasons"]
        self.assertTrue(any("council page" in x for x in r)); self.assertTrue(any("foyer" in x for x in r))
    def test_directory_with_own_site_still_added(self):
        add, _, unv = self.go({"id": "hl-house", "name": "House The Homeless", "postcode": "BN1 1AA", "lat": 50.8, "lng": -0.1,
                               "website": "https://housethehomeless.example/", "directory": "Homeless Link"})
        self.assertEqual(len(add), 1); self.assertIn("hl-house", unv)
    def test_2xx_label(self):
        r = D.own_site_check({"name": "X", "postcode": "BN1 1AA", "website": "https://x.example/"}, "sh",
                             fetcher=lambda u: {"http": 202, "final_url": u, "html": ""})
        self.assertIn("did not return the page (HTTP 202", r["reasons"][0])
if __name__ == "__main__": unittest.main()
