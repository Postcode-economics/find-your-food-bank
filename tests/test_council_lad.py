"""Council name -> ONS area code for incident rest centres (12 Nov 2026).

A visitor's area comes from postcodes.io codes.admin_district, which is a local authority district code
(for example E07... for a district council). Before this fix only counties and unitary authorities were
searched and the word "council" was kept, so a district council's rest centre got no area code and the
live note and card reached nobody.
"""
import collections, json, os, sys, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import council_lad  # noqa: E402


def _sources():
    return json.load(open(os.path.join(ROOT, "overrides", "rest_centre_sources.json"), encoding="utf-8"))["councils"]


class DistrictCouncils(unittest.TestCase):
    # admin_district codes postcodes.io gives for these councils' own areas (CB1 1PT -> E07000008, EX1 1HS -> E07000041).
    def test_cambridge_city_council_is_its_district(self):
        self.assertEqual(council_lad.lad_for_council("Cambridge City Council"), "E07000008")

    def test_exeter_city_council_is_its_district(self):
        self.assertEqual(council_lad.lad_for_council("Exeter City Council"), "E07000041")

    def test_district_council_wording(self):
        self.assertEqual(council_lad.lad_for_council("Braintree District Council"), "E07000067")
        self.assertEqual(council_lad.lad_for_council("Basingstoke and Deane Borough Council"), "E07000084")

    def test_bare_district_name_from_feeds(self):
        self.assertEqual(council_lad.lad_for_council("Cambridge"), "E07000008")

    def test_unitary_metropolitan_and_devolved_councils(self):
        self.assertEqual(council_lad.lad_for_council("Birmingham City Council"), "E08000025")
        self.assertEqual(council_lad.lad_for_council("Durham County Council"), "E06000047")
        self.assertEqual(council_lad.lad_for_council("Hull City Council"), "E06000010")
        self.assertEqual(council_lad.lad_for_council("Newcastle City Council"), "E08000021")
        self.assertEqual(council_lad.lad_for_council("Borough Council of Kings Lynn and West Norfolk"), "E07000146")
        self.assertEqual(council_lad.lad_for_council("City of London Corporation"), "E09000001")
        self.assertEqual(council_lad.lad_for_council("Comhairle nan Eilean Siar"), "S12000013")
        self.assertEqual(council_lad.lad_for_council("Rhondda Cynon Taf County Borough Council"), "W06000016")
        self.assertEqual(council_lad.lad_for_council("Belfast City Council"), "N09000003")

    def test_unknown_or_empty_is_nobody(self):
        for name in ("", None, "Council", "Nowhere Borough Council"):
            self.assertIsNone(council_lad.lad_for_council(name))


class EverySourceCouncil(unittest.TestCase):
    def test_every_rest_centre_source_council_has_one_unique_code(self):
        got = {c["council"]: council_lad.lad_for_council(c["council"]) for c in _sources()}
        missing = sorted(k for k, v in got.items() if not v)
        self.assertEqual(missing, [])
        dup = [code for code, n in collections.Counter(got.values()).items() if n > 1]
        self.assertEqual(dup, [], "two councils share one area code")

    def test_every_district_level_area_is_reachable(self):
        lads = {a["code"] for a in json.load(open(os.path.join(ROOT, "scripts", "lad_codes.json"), encoding="utf-8"))["areas"]}
        got = {council_lad.lad_for_council(c["council"]) for c in _sources()}
        self.assertEqual(sorted(lads - got), [], "a district or unitary council's rest centre would reach nobody")


class LadData(unittest.TestCase):
    def setUp(self):
        self.d = json.load(open(os.path.join(ROOT, "scripts", "lad_codes.json"), encoding="utf-8"))

    def test_source_is_ons(self):
        self.assertIn("ONS Open Geography Portal", self.d["_source"])
        self.assertIn("admin_district", self.d["_source"])

    def test_codes_are_gss_and_unique(self):
        codes = [a["code"] for a in self.d["areas"]]
        self.assertEqual(len(codes), len(set(codes)))
        for c in codes:
            self.assertRegex(c, r"^[ENSW]\d{8}$")

    def test_normalised_names_never_collide(self):
        n = collections.Counter(council_lad._norm(a["name"]) for a in self.d["areas"])
        self.assertEqual([k for k, v in n.items() if v > 1], [])

    def test_aliases_point_at_real_ons_names(self):
        names = {a["name"] for a in self.d["areas"]}
        for v in council_lad.ALIASES.values():
            self.assertIn(v, names)


class LiveCardCarriesDistrictCode(unittest.TestCase):
    def test_incident_record_gets_district_code(self):
        import incident_rest_centre_live as live
        from unittest import mock

        page = {"council": "Exeter City Council", "url": "https://example.invalid/rest-centre",
                "rest_centre": {"active": True, "quote": "q"}, "_text": "t"}
        ann = {"name": "Civic Hall", "address": "EX1 1HS", "lat": 50.72, "lng": -3.53}
        with mock.patch("rest_centre_scan.rest_centre_on", return_value=True), \
             mock.patch("weather.parse_announcement", return_value=ann):
            rec = live.incident_record(page)
        self.assertEqual(rec["lad"], "E07000041")


if __name__ == "__main__":
    unittest.main()
