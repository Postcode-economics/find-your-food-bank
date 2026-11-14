"""Crisis Skylight cards must stay as they are on main (Dean, 14 Nov 2026).

The eight Crisis Skylight listings were hand-updated from Crisis's own pages
(PRs #431, #436, #458/#459, #460, #461, #462, #463, #464). This batch must not
change those overlay records or add another Crisis Skylight card.
"""
import json, os, subprocess, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "crisis_skylight_main.json")
IDS = [
    "man-crisis-skylight-birmingham",
    "man-crisis-skylight-brent",
    "man-crisis-skylight-croydon",
    "man-crisis-skylight-edinburgh",
    "man-crisis-skylight-merseyside",
    "man-crisis-skylight-newcastle",
    "man-crisis-skylight-oxford",
    "man-crisis-skylight-south-wales",
]


def _load(path):
    return json.loads(open(os.path.join(ROOT, path), encoding="utf-8").read())


def _git_json(spec):
    r = subprocess.run(["git", "-C", ROOT, "show", spec], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)


def _baseline():
    """Prefer live origin/main when it is available; otherwise the committed fixture."""
    man = _git_json("origin/main:overrides/shelters_manual.json")
    ver = _git_json("origin/main:overrides/shelters_verified.json")
    app = _git_json("origin/main:overrides/approved_new_places.json")
    if man is not None and ver is not None and app is not None:
        return {
            "manual": {r["id"]: r for r in man if r.get("id") in IDS},
            "verified": {i: ver[i] for i in IDS if i in ver},
            "approved": {i: (app.get("shelters") or {}).get(i) for i in IDS},
        }
    return json.loads(open(FIX, encoding="utf-8").read())


class CrisisSkylightUnchanged(unittest.TestCase):
    def setUp(self):
        self.base = _baseline()
        self.manual = {r["id"]: r for r in _load("overrides/shelters_manual.json")}
        self.verified = _load("overrides/shelters_verified.json")
        self.approved = (_load("overrides/approved_new_places.json").get("shelters") or {})

    def test_eight_cards_match_main_in_every_overlay(self):
        for iid in IDS:
            self.assertEqual(self.manual.get(iid), self.base["manual"].get(iid), iid + " manual")
            self.assertEqual(self.verified.get(iid), self.base["verified"].get(iid), iid + " verified")
            self.assertEqual(self.approved.get(iid), self.base["approved"].get(iid), iid + " approved")

    def test_no_extra_crisis_skylight_cards(self):
        extra = [i for i in self.manual if i.startswith("man-crisis-skylight-") and i not in IDS]
        self.assertEqual(extra, [])
        extra_v = [i for i in self.verified if i.startswith("man-crisis-skylight-") and i not in IDS]
        self.assertEqual(extra_v, [])
