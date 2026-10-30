"""Regression (30 Oct 2026): new_today.md relisted places already on the published map."""
import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import discovery_rules as DR

DAY = "2026-10-30"
BASE = "7756ee24a^"  # last publish before the first 30 Oct food-bank refresh


def _git(path):
    return subprocess.check_output(["git", "-C", ROOT, "show", "%s:%s" % (BASE, path)], text=True)


class Oct30NewToday(unittest.TestCase):
    def test_warmspaces_and_shelters_not_relisted(self):
        ws = json.loads(_git("warmspaces.js").split("=", 1)[1].strip().rstrip(";"))
        sh = json.loads(_git("shelters.js").split("=", 1)[1].strip().rstrip(";"))
        base_ws = {i["id"] for i in ws["items"]}
        base_sh = {i["id"] for i in sh["items"]}
        ws_log = json.load(open(os.path.join(ROOT, "logs", "discovery_today_warmspaces.json")))
        sh_log = json.load(open(os.path.join(ROOT, "logs", "discovery_today_shelters.json")))
        ws_names = {"Marlborough Primary School B10 9NY", "Saifee Mosque B18 6PU", "The Midlands Greek & Cypriot Association B23 7SJ"}
        ws_added = [a for a in ws_log["added"] if a.get("postcode") and any(n.split()[-1] in a["postcode"] or n in a["name"] for n in ws_names)]
        self.assertEqual(len(ws_log["added"]), 3)
        self.assertEqual(len([a for a in ws_added if a["id"] in base_ws]), 3)
        sh_added = sh_log["added"]
        self.assertEqual(len(sh_added), 3)
        self.assertTrue(all(a["id"] in base_sh for a in sh_added))
        d = tempfile.mkdtemp()
        open(os.path.join(d, "warmspaces.js"), "w").write(_git("warmspaces.js"))
        open(os.path.join(d, "shelters.js"), "w").write(_git("shelters.js"))
        kept_ws = DR.filter_added("warmspaces", ws_log["added"], d)
        kept_sh = DR.filter_added("shelters", sh_log["added"], d)
        self.assertEqual(kept_ws, [])
        self.assertEqual(kept_sh, [])

    def test_foodbanks_only_true_publish_diff(self):
        fb = _git("data.full.js")
        s = fb[fb.index("=") + 1 :].strip().rstrip(";")
        before = {i["id"] for i in json.loads(s)["items"]}
        after = before  # 30 Oct refresh commits changed no food-bank ids
        publish_new = sorted(after - before)
        self.assertEqual(publish_new, [])
        fb_log = json.load(open(os.path.join(ROOT, "logs", "discovery_today_foodbanks.json")))
        self.assertEqual(len(fb_log["added"]), 81)
        kept = DR.filter_added("foodbanks", fb_log["added"], ROOT, publish_new_ids=publish_new)
        self.assertEqual(kept, [])

    def test_record_writes_zero_for_oct30_case(self):
        r = tempfile.mkdtemp()
        os.makedirs(os.path.join(r, "reports"))
        open(os.path.join(r, "reports", "manual_review.md"), "w").write("# Manual review queue\n")
        open(os.path.join(r, "warmspaces.js"), "w").write(_git("warmspaces.js"))
        ws_log = json.load(open(os.path.join(ROOT, "logs", "discovery_today_warmspaces.json")))
        DR.record("warmspaces", DAY, ws_log["added"], [], [], source="test", root=r)
        nt = open(os.path.join(r, "reports", "new_today.md")).read()
        self.assertIn("## Warm spaces: 0 added", nt)
        self.assertNotIn("Marlborough Primary School", nt)


if __name__ == "__main__":
    unittest.main()
