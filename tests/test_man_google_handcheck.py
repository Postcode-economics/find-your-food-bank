"""man-google rows publish only from the hand-check list (Dean, 1 Nov 2026).

Page-title hits such as 'About Us - Hinckley...' and 'National - Housing' must
not be republished by the next shelters refresh, even if they are still in
shelters_manual.json or were already on the map.
"""
import json
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import google_handcheck as G

PULL_IDS = (
    "man-google-maggs-day-centre-worcester",
    "man-google-share-homeless-action-centre-shac",
    "hl-ymca-lincs-nomad-centre",
    "man-vaughan-house",
    "ss-63bf328f843d85a21d7bbdce",
)


def _published():
    raw = open(os.path.join(ROOT, "shelters.js"), encoding="utf-8").read()
    return json.loads(raw.split("=", 1)[1].strip().rstrip(";"))["items"]


def _manual():
    return json.load(open(os.path.join(ROOT, "overrides", "shelters_manual.json"), encoding="utf-8"))


class ManGoogleHandCheck(unittest.TestCase):
    def test_allowlist_matches_hand_check_file(self):
        path = os.path.join(ROOT, "overrides", "man_google_handcheck.json")
        want = set(json.load(open(path, encoding="utf-8")))
        self.assertEqual(G.allowed(ROOT), want)
        self.assertEqual(len(want), 6)
        self.assertIn("man-google-day-centre", want)
        self.assertNotIn("man-google-calderwood-house", want)
        self.assertNotIn("man-google-homeless-accommodation-tai-gogledd-cymru", want)

    def test_shelters_js_has_no_pull_ids_or_unlisted_man_google(self):
        allow = G.allowed(ROOT)
        published = _published()
        by = {i["id"] for i in published}
        for pid in PULL_IDS:
            self.assertNotIn(pid, by, pid)
        mg = sorted(i["id"] for i in published if str(i.get("id") or "").startswith("man-google-"))
        self.assertEqual(mg, sorted(allow))

    def test_published_map_has_no_man_google_outside_the_list(self):
        allow = G.allowed(ROOT)
        extra = [i["id"] for i in _published() if str(i.get("id") or "").startswith("man-google-") and i["id"] not in allow]
        self.assertEqual(extra, [])

    def test_refresh_keeps_only_hand_checked_man_google_rows(self):
        allow = G.allowed(ROOT)
        brentwood = next(i for i in _manual() if i.get("id") == "man-google-brentwood-middleton-day-centre")
        page_title = {
            "id": "man-google-about-us-hinckley-homeless-group-lawrence-house",
            "name": "About Us - Hinckley Homeless Group - Lawrence House",
            "card_type": "referral_hostel",
        }
        duplicate = {"id": "man-google-clock-tower-sanctuary", "name": "Clock Tower Sanctuary", "kind": "day_centre"}
        kept, held = G.keep([brentwood, page_title, duplicate, {"id": "man-first-base-brighton", "name": "First Base"}], ROOT)
        self.assertEqual([i["id"] for i in kept], ["man-google-brentwood-middleton-day-centre", "man-first-base-brighton"])
        self.assertEqual({i["id"] for i in held}, {page_title["id"], duplicate["id"]})
        self.assertTrue(all(G.held_reason(i, allow, ROOT) for i in held))
        manual_extra = [i for i in _manual() if str(i.get("id") or "").startswith("man-google-") and i["id"] not in allow]
        self.assertGreaterEqual(len(manual_extra), 27)
        kept_m, held_m = G.keep(manual_extra, ROOT)
        self.assertEqual(kept_m, [])
        self.assertEqual(len(held_m), len(manual_extra))
