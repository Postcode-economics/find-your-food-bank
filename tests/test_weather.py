import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import weather as w
RSS = b'<rss><channel><item><title>Amber warning of wind affecting Wales</title><description>Amber warning of wind affecting Wales: Gwynedd, Isle of Anglesey valid from 1000 Sat</description><link>x</link></item></channel></rss>'
class T(unittest.TestCase):
    def test_met(self):
        r = w.met(RSS)[0]; self.assertEqual((r["level"], r["areas"]), ("amber", ["Gwynedd", "Isle of Anglesey"]))
    def test_match(self):
        r = w.match(w.met(RSS), [{"name": "S1", "address": "1 High St, Bangor, Gwynedd LL57"}, {"name": "S2", "address": "Leeds"}], ["Isle of Anglesey County Council"])[0]
        self.assertEqual((r["places"], r["swep"]), (["S1"], ["Isle of Anglesey County Council"]))
        self.assertEqual(len(w.urgent([r])), 1)
    def test_sepa_skips_alerts(self):
        x = b'<rss><channel><item><title>A FLOOD ALERT has been issued for Tayside</title></item><item><title>A SEVERE FLOOD WARNING has been issued for Perth</title></item></channel></rss>'
        self.assertEqual([i["level"] for i in w.sepa(x)], ["red"])
    def test_nrw(self):
        import json
        js = json.dumps({"features": [{"geometry": {"coordinates": [-4.04, 52.50]}, "properties": {"SEVERITYVALUE": 2, "SEVERITY": "Flood Warning", "DESCRIPTION": "Tidal area at Borth"}},
                                      {"geometry": {"coordinates": [-3.0, 53.2]}, "properties": {"SEVERITYVALUE": 3, "SEVERITY": "Flood Alert", "DESCRIPTION": "x"}},
                                      {"geometry": {"coordinates": [-3.9, 51.9]}, "properties": {"SEVERITYVALUE": 1, "SEVERITY": "Severe Flood Warning", "DESCRIPTION": "y"}}]})
        r = w.nrw(js, locate=lambda la, lo: "Ceredigion")
        self.assertEqual([(i["level"], i["areas"]) for i in r], [("flood warning", ["Ceredigion"]), ("red", ["Ceredigion"])])
        self.assertTrue(all(i["credit"] == w.NRW_CREDIT for i in r))
        self.assertIn("Natural Resources Wales and database right", w.NRW_CREDIT)
    def test_nrw_key_env(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {"NRW_FLOOD_API_KEY": " abc "}): self.assertEqual(w.nrw_key(), "abc")
class D(unittest.TestCase):
    def test_digest_weather_alert(self):
        import digest
        self.assertEqual([a[0] for a in digest.triggers({}, {}, [], "9", [{"level": "amber", "title": "t", "places": [], "swep": []}, {"level": "yellow", "title": "y"}])[0]], ["weather"])
