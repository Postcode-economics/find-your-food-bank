import json, sys, os, shutil, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import full_check as F
FIX = {"https://a.org": dict(old=F.norm_phone("01234 567890"), new="09876543210", since="2026-10-24", source="https://a.org/c")}
class T(unittest.TestCase):
    def run_fix(self, **kw):
        root = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, "overrides"))
        json.dump({"listings": {}}, open(os.path.join(root, "overrides", "phone_baseline.json"), "w"))
        i = dict(id="x", name="A", phone="01234 567890", tel="01234567890", **kw); flags = {}
        n = F.apply_phone_fixes({"https://a.org": [i]}, FIX, lambda k, c, **x: flags.__setitem__(c + "|" + k, x), root=root)
        return i, flags, n, root
    def test_unlocked_is_held(self):
        i, flags, n, root = self.run_fix()
        self.assertEqual(i["phone"], "01234 567890"); self.assertEqual(i["tel"], "01234567890"); self.assertEqual(n, 0)
        self.assertIn("never auto-applied", list(flags)[0])
        text = open(os.path.join(root, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertIn("held for Dean", text)
        self.assertIn("09876543210", text)
        self.assertIn("unchanged (byte-identical)", text)
    def test_phone_checked_not_overwritten(self):
        i, flags, n, root = self.run_fix(phone_checked=True); self.assertEqual(i["phone"], "01234 567890"); self.assertEqual(i["tel"], "01234567890"); self.assertEqual(n, 0)
        self.assertEqual(len(flags), 1); self.assertEqual(list(flags.values())[0]["proposed"], "09876543210")
    def test_locked_not_overwritten(self):
        i, flags, n, root = self.run_fix(locked=True); self.assertEqual(i["phone"], "01234 567890"); self.assertEqual(n, 0); self.assertEqual(len(flags), 1)
if __name__ == "__main__": unittest.main()
