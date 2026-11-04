"""The 36 Street Support shelters link to the organisation's own site; Street Support is credited separately (Dean, 3 Nov 2026).
Plain unittest: the shelter refresh runs `python -m unittest discover`, which has no pytest installed."""
import json, os, re, shutil, subprocess, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ss():
    d = json.load(open(os.path.join(ROOT, "overrides", "shelters_manual.json"), encoding="utf-8"))
    return [e for e in d if e["id"].startswith("man-ss")]


class StreetSupportCredit(unittest.TestCase):
    def test_36_entries_own_site_and_credit(self):
        ss = _ss()
        self.assertEqual(len(ss), 36)
        for e in ss:
            self.assertTrue(e["source_url"].startswith("http") and "streetsupport.net" not in e["source_url"], e["id"])
            self.assertNotEqual(e["source"], "Street Support", e["id"])
            self.assertEqual(e["discovery_label"], "Street Support", e["id"])
            self.assertTrue(e["discovery_url"].startswith("https://www.streetsupport.net/find-help"), e["id"])

    def test_card_renders_found_via_credit(self):
        node = shutil.which("node")
        if not node: self.skipTest("node not installed")
        with open(os.path.join(ROOT, "layers.js"), encoding="utf-8") as f: src = f.read()
        fn = re.search(r"function shSource\(i\)\{.*?</p>`\}", src, re.S).group(0)
        e = _ss()[0]
        js = ("const esc=s=>String(s);const fmt=s=>s;const T={en:{src:'Source',ver:'checked',chk:'c',lst:'l',seen:'s'},cy:{src:'Ffynhonnell',ver:'v',chk:'c',lst:'l',seen:'s'}};"
              + fn + ";console.log(shSource(" + json.dumps(e) + "))")
        out = subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout
        self.assertTrue("Found via" in out and e["discovery_url"] in out and ">Street Support</a>" in out)
        self.assertIn('href="%s"' % e["source_url"], out)


if __name__ == "__main__":
    unittest.main()
