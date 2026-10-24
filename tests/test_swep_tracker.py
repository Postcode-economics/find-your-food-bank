import sys, os, json, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import swep_tracker as S
class T(unittest.TestCase):
    def test_list(self):
        d = tempfile.mkdtemp(); f = os.path.join(d, "f.json")
        json.dump({"run": "2026-10-24", "councils": [{"council": "A", "status": "unknown"}, {"council": "B", "status": "active"}, {"council": "C", "status": "unreachable"}]}, open(f, "w"))
        n = S.update(f, os.path.join(d, "h.json"), os.path.join(d, "t.md")); self.assertEqual(n, 2)
        md = open(os.path.join(d, "t.md")).read(); self.assertIn("**2 of 3**", md); self.assertNotIn("- B", md)
