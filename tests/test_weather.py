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
