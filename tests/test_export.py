import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import export_data as e
class T(unittest.TestCase):
    def test_osm_excluded(self):
        self.assertFalse(e.shareable_shelter({"source": "OpenStreetMap"})); self.assertTrue(e.shareable_shelter({"source": "Operator website"}))
    def test_no_private_fields(self):
        for f in ("email", "notes", "opening_times", "hours", "fb_page"): self.assertNotIn(f, e.FB + e.SH + e.WS)
