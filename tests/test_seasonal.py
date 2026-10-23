import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import seasonal as S
class T(unittest.TestCase):
    def test_space_opening(self): self.assertEqual(S.parse("**SPACE OPENING ON 7th December 2026** A warm space")["start"], "2026-12-07")
    def test_from_to(self):
        r = S.parse("Open weekly from 6th October 2026 to 6th April 2027, Tuesdays"); self.assertEqual(r, {"start": "2026-10-06", "end": "2027-04-06"})
    def test_end_of_month(self):
        r = S.parse("every Friday, beginning 7th November 2025 until the end of March 2026"); self.assertEqual(r, {"start": "2025-11-07", "end": "2026-03-31"})
    def test_nothing(self): self.assertEqual(S.parse("Open Mondays 10-12"), {"start": "", "end": ""})
    def test_upcoming_label(self):
        it = [{"id": "a", "scheme_start": "2026-12-07", "scheme_end": ""}]; k, g = S.apply(it, "2026-10-23")
        self.assertTrue(k[0]["upcoming"]); self.assertEqual(k[0]["scheme_dates"], "Opens 7 Dec 2026"); self.assertFalse(k[0].get("ended"))
    def test_open_now_with_end(self):
        k, _ = S.apply([{"id": "a", "scheme_start": "2026-10-06", "scheme_end": "2027-04-06"}], "2026-10-23")
        self.assertFalse(k[0].get("upcoming")); self.assertEqual(k[0]["scheme_dates"], "Until 2027-04-06")
    def test_ended_greyed_then_expired(self):
        k, g = S.apply([{"id": "a", "scheme_end": "2026-10-20"}], "2026-10-23"); self.assertTrue(k[0]["ended"]); self.assertEqual(g, [])
        k, g = S.apply([{"id": "a", "scheme_end": "2026-03-31"}], "2026-10-23"); self.assertEqual(k, []); self.assertIn("Season ended", g[0]["closed_reason"])
    def test_no_dates_untouched(self):
        k, _ = S.apply([{"id": "a", "scheme_dates": "Not stated by source"}], "2026-10-23"); self.assertEqual(k[0]["scheme_dates"], "Not stated by source")
if __name__ == "__main__": unittest.main()
