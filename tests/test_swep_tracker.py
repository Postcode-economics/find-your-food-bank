import sys, os, json, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import swep_tracker as S
class T(unittest.TestCase):
    def test_list(self):
        d = tempfile.mkdtemp(); f = os.path.join(d, "f.json")
        json.dump({"run": "2026-10-24", "councils": [{"council": "A", "status": "unknown"}, {"council": "B", "status": "active"}, {"council": "C", "status": "unreachable"}]}, open(f, "w"))
        n = S.update(f, os.path.join(d, "h.json"), os.path.join(d, "t.md")); self.assertEqual(n, 2)
        md = open(os.path.join(d, "t.md")).read(); self.assertIn("**2 of 3**", md); self.assertNotIn("- B", md)
    def test_hand(self):
        d = tempfile.mkdtemp(); f = os.path.join(d, "f.json"); h = os.path.join(d, "h.json")
        json.dump({"run": "2026-10-24", "councils": [{"code": "A", "council": "A", "status": "unknown"}, {"code": "C", "council": "C", "status": "unreachable"}, {"code": "D", "council": "D", "status": "unknown"}]}, open(f, "w"))
        json.dump({"A": {"checked": "2026-10-24", "result": "ok", "note": "n", "url": "u"}, "C": {"checked": "2026-08-01", "result": "ok", "note": "n", "url": "u"}, "D": {"checked": "2026-10-24", "result": "todo", "note": "n", "url": "u"}}, open(h, "w"))
        self.assertEqual(S.update(f, os.path.join(d, "x.json"), os.path.join(d, "t.md"), h), 2)  # A settled; C expired; D still todo
