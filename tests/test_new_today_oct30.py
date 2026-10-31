"""Regression (30 Oct 2026): new_today.md must not relist places already on the published map.

Uses pinned git baselines plus fixtures under tests/fixtures/oct30_new_today/ — not live logs/.
"""
import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "oct30_new_today")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import discovery_rules as DR

DAY = "2026-10-30"
BASE = "7756ee24a^"  # last publish before the first 30 Oct food-bank refresh


def _git(path):
    return subprocess.check_output(["git", "-C", ROOT, "show", "%s:%s" % (BASE, path)], text=True)


def _fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def _published_snapshot(root):
    for name in ("warmspaces.js", "shelters.js", "data.full.js"):
        with open(os.path.join(root, name), "w", encoding="utf-8") as f:
            f.write(_git(name))


class Oct30NewToday(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "logs"))
        os.makedirs(os.path.join(self.root, "reports"))
        _published_snapshot(self.root)

    def test_published_ids_match_oct30_baseline(self):
        ws = DR.published_ids("warmspaces", self.root)
        sh = DR.published_ids("shelters", self.root)
        relisted_ws = {a["id"] for a in _fixture("warmspaces_relisted.json")}
        relisted_sh = {a["id"] for a in _fixture("shelters_relisted.json")}
        self.assertTrue(relisted_ws <= ws, relisted_ws - ws)
        self.assertTrue(relisted_sh <= sh, relisted_sh - sh)

    def test_warmspaces_and_shelters_not_relisted(self):
        ws_added = _fixture("warmspaces_relisted.json")
        sh_added = _fixture("shelters_relisted.json")
        kept_ws = DR.filter_added("warmspaces", ws_added, self.root)
        kept_sh = DR.filter_added("shelters", sh_added, self.root)
        self.assertEqual(kept_ws, [])
        self.assertEqual(kept_sh, [])

    def test_genuinely_new_warm_space_is_kept(self):
        ws_added = _fixture("warmspaces_relisted.json") + _fixture("warmspaces_genuinely_new.json")
        kept = DR.filter_added("warmspaces", ws_added, self.root)
        self.assertEqual([a["id"] for a in kept], ["ww-69464578"])

    def test_foodbanks_only_true_publish_diff(self):
        """build.py passes publish_new_ids=new_ids; empty diff => nothing in new_today."""
        before = DR.published_ids("foodbanks", self.root)
        publish_new = sorted(before - before)
        self.assertEqual(publish_new, [])
        fb_added = _fixture("foodbanks_discovery_sample.json")
        kept = DR.filter_added("foodbanks", fb_added, self.root, publish_new_ids=publish_new)
        self.assertEqual(kept, [])

    def test_foodbanks_publish_new_ids_allowlist(self):
        fb_added = _fixture("foodbanks_discovery_sample.json")
        allow = ["lincoln", "caterham"]
        kept = DR.filter_added("foodbanks", fb_added, self.root, publish_new_ids=allow)
        self.assertEqual([a["id"] for a in kept], allow)

    def test_record_writes_zero_for_oct30_relisted_case(self):
        with open(os.path.join(self.root, "reports", "manual_review.md"), "w", encoding="utf-8") as f:
            f.write("# Manual review queue\n")
        ws_added = _fixture("warmspaces_relisted.json")
        DR.record("warmspaces", DAY, ws_added, [], [], source="test", root=self.root)
        with open(os.path.join(self.root, "reports", "new_today.md"), encoding="utf-8") as f:
            nt = f.read()
        self.assertIn("## Warm spaces: 0 added", nt)
        self.assertNotIn("Marlborough Primary School", nt)

    def test_record_lists_genuinely_new_warm_space(self):
        with open(os.path.join(self.root, "reports", "manual_review.md"), "w", encoding="utf-8") as f:
            f.write("# Manual review queue\n")
        ws_added = _fixture("warmspaces_relisted.json") + _fixture("warmspaces_genuinely_new.json")
        DR.record("warmspaces", DAY, ws_added, [], [], source="test", root=self.root)
        with open(os.path.join(self.root, "reports", "new_today.md"), encoding="utf-8") as f:
            nt = f.read()
        self.assertIn("## Warm spaces: 1 added", nt)
        self.assertIn("Second Chance Headway Centre", nt)
        self.assertNotIn("Marlborough Primary School", nt)


if __name__ == "__main__":
    unittest.main()
