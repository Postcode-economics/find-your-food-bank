import sys, os, unittest, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import full_check as F
class T(unittest.TestCase):
    def test_pause_after_3(self):
        h = "bad.example"; F._errs.pop(h, None); F._paused.pop(h, None)
        F._note(h, False); F._note(h, False); self.assertNotIn(h, F._paused)
        F._note(h, False); self.assertGreater(F._paused[h], time.time() + 590)
        r = F.fetch("https://bad.example/x"); self.assertFalse(r["ok"]); self.assertIn("paused", r["error"])
    def test_success_resets(self):
        h = "ok.example"; F._errs.pop(h, None); F._paused.pop(h, None)
        F._note(h, False); F._note(h, False); F._note(h, True); F._note(h, False); self.assertNotIn(h, F._paused)
    def test_gap(self): self.assertEqual(F.MIN_GAP, 2.0)
