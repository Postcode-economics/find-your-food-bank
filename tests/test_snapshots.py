import sys, os, unittest, datetime as dt, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import snapshots as S
class T(unittest.TestCase):
    def test_plan(self):
        t = dt.date(2026, 10, 24); D = dt.date
        keep, arch = S.plan([D(2026, 10, 20), D(2026, 9, 1), D(2026, 9, 2), D(2026, 8, 31), D(2025, 3, 3), D(2025, 3, 4), D(2024, 1, 1)], t)
        self.assertIn(D(2026, 10, 20), keep); self.assertIn(D(2026, 9, 1), keep); self.assertIn(D(2024, 1, 1), keep)
        self.assertIn(D(2026, 8, 31), keep)  # Monday within a year
        self.assertIn(D(2026, 9, 2), arch); self.assertIn(D(2025, 3, 3), arch); self.assertIn(D(2025, 3, 4), arch)
    def test_never_deletes(self):
        d = tempfile.mkdtemp(); open(os.path.join(d, "2026-09-02.json.gz"), "w").write("x")
        self.assertEqual(S.apply(d, dt.date(2026, 10, 24)), [dt.date(2026, 9, 2)]); self.assertTrue(os.path.exists(os.path.join(d, "archive", "2026-09-02.json.gz")))
