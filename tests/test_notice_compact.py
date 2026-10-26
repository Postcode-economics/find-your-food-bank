"""Card notices (overrides/foodbank_notices.json) reach the browser (owner, 25 Oct 2026): compact data.js kept 'notice'
out, so no notice ever showed. Every notice in data.full.js must decode from data.js."""
import os, sys, json, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
class T(unittest.TestCase):
    def test_key_kept(self):
        import compact; self.assertIn("notice", compact.KEYS)
    def test_notices_in_data_js(self):
        import compact
        full = {i["id"]: i.get("notice") for i in compact.load_full()["items"] if i.get("notice")}
        s = open(os.path.join(ROOT, "data.js"), encoding="utf-8").read()
        for n in set(full.values()): self.assertTrue(json.dumps(n)[1:-1] in s or json.dumps(n, ensure_ascii=False)[1:-1] in s, n)
        self.assertIn("First Base emergency parcel pick-up point", set(full.values()))
