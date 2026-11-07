"""Successful per-listing checks advance one displayed date, even without edits.
All mocked network responses and generated reports live in temporary directories.
"""
import copy
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_dates
import common
import compact
import discover
import fb_recheck
from tests.test_fb_recheck import item, META, page

OLD = "2026-10-24"
NOW = "2026-11-07T12:00:00+00:00"


class Dates(unittest.TestCase):
    def test_uk_midnight_and_bst(self):
        self.assertEqual(check_dates.uk_day("2026-07-07T23:30:00Z"), "2026-07-08")
        self.assertEqual(check_dates.uk_day("2026-11-07T23:30:00Z"), "2026-11-07")
        self.assertEqual(check_dates.uk_day("2026-07-07T23:30:00"), "")

    def test_only_primary_display_date_changes_no_invented_fallback(self):
        x = item(givefood="", verified_on=OLD, facilities=["Staff-confirmed wording"])
        before = copy.deepcopy(x)
        check_dates.success(x, NOW)
        before["verified_on"] = "2026-11-07"
        self.assertEqual(x, before)
        self.assertIsNone(x["opening_times"])
        self.assertFalse(x["givefood"])

    def test_newer_human_date_wins_and_previous_check_survives_rebuild(self):
        x = {"verified_on": "2026-11-08"}
        check_dates.success(x, NOW)
        self.assertEqual(x["verified_on"], "2026-11-08")
        rebuilt = {"verified_on": OLD}
        check_dates.preserve(rebuilt, x)
        self.assertEqual(rebuilt["verified_on"], "2026-11-08")

    def test_rebuild_preserves_date_without_inventing_source_or_hours(self):
        items = [item(id="gf", verified_on=OLD), item(id="own", givefood="")]
        previous = [item(id="gf", verified_on="2026-11-06"), item(id="own", givefood="")]
        check_dates.preserve_foodbanks(items, previous, "2026-11-07")
        self.assertEqual(items[0]["verified_on"], "2026-11-06")
        self.assertNotIn("verified_on", items[1])
        self.assertEqual(items[1]["givefood"], "")
        self.assertIsNone(items[1]["opening_times"])

    def test_compact_and_card_single_date_all_layers(self):
        x = item(verified_on=OLD)
        check_dates.success(x, NOW)
        encoded = compact.encode({"items": [x], "fetched": "2026-11-09"})
        js = "global.window={};" + encoded + "const f=require(" + json.dumps(str(ROOT / "facts.js")) + ");" + "console.log(JSON.stringify(['fb','sh','ws'].map(k=>f.checked(Object.assign({},window.FB_DATA.items[0],{layer:k})))));"
        cards = json.loads(subprocess.check_output(["node", "-e", js], text=True))
        for html in cards:
            self.assertEqual(html.count('class="xrow uchk"'), 1)
            self.assertEqual(html.count("Last checked"), 1)
            self.assertIn("7 Nov 2026", html)
            self.assertNotIn("9 Nov 2026", html)
            self.assertNotIn("Last refreshed", html)


class LayerGates(unittest.TestCase):
    def test_shelter_and_warmspace_verified_and_tier2(self):
        for layer in ("shelters", "warmspaces"):
            for tier in ("verified", "unverified"):
                for ok in (True, False, None):
                    with self.subTest(layer=layer, tier=tier, ok=ok), tempfile.TemporaryDirectory() as td:
                        x = dict(id="man-test", name="Test", address="Town", hours="", last_verified=OLD,
                                 verified_on=OLD, checked_on=OLD, facilities=["Staff-confirmed wording"], phone="01234567890")
                        before = copy.deepcopy(x)
                        ver = {x["id"]: dict(evidence_url="https://example.org/test", quote="Test", verified_on=OLD)} if tier == "verified" else {}
                        unv = {x["id"]: dict(sign_url="https://example.org/test", checked_on=OLD)} if tier == "unverified" else {}
                        rc = {x["id"]: dict(ok=ok, fetched_at=NOW, http=200 if ok else 403)} if ok is not None else {}
                        cwd = os.getcwd()
                        try:
                            os.chdir(td)
                            Path("logs").mkdir()
                            with patch("recheck.recheck_all", return_value=rc):
                                pub, _, _ = common.verification_gate([dict(x, last_verified="2026-11-07")], {"items": [copy.deepcopy(x)]}, ver,
                                    "2026-11-07", "logs/" + layer + "_pending.json", unverified=unv,
                                    now=datetime.datetime.fromisoformat(NOW))
                        finally:
                            os.chdir(cwd)
                        self.assertEqual(pub[0]["verified_on"], "2026-11-07" if ok else OLD)
                        for key in ("phone", "name", "address", "hours", "facilities"):
                            self.assertEqual(pub[0][key], before[key])
                        if ver:
                            self.assertEqual(ver[x["id"]]["verified_on"], OLD)

    def test_foodbank_unchanged_record_and_blocked_sample(self):
        for http in (200, 403, 429):
            with self.subTest(http=http), tempfile.TemporaryDirectory() as td:
                x = item(verified_on=OLD)
                before = copy.deepcopy(x)
                with patch.object(fb_recheck, "now", return_value=NOW):
                    pub, _ = fb_recheck.gate([x], {x["id"]: {"slug": "acme"}}, copy.deepcopy(META),
                        td + "/log", td + "/pending", fetcher=lambda u: page(http=http), per_run=1)
                self.assertEqual(pub[0]["verified_on"], "2026-11-07" if http == 200 else OLD)
                for k, v in before.items():
                    if k != "verified_on":
                        self.assertEqual(pub[0][k], v)

    def test_saved_manual_record_is_not_a_new_fetch(self):
        with tempfile.TemporaryDirectory() as td:
            x = item(manual=True, evidence_url="https://example.org/test", verified_on=OLD)
            with patch.object(fb_recheck, "now", return_value=NOW):
                pub, _ = fb_recheck.gate([x], {"acme": {}}, copy.deepcopy(META), td + "/r", td + "/p", per_run=0)
            self.assertEqual(pub[0]["verified_on"], OLD)


class OwnSiteChecks(unittest.TestCase):
    def test_only_final_successful_verdict_advances_primary_date(self):
        for kind, field in (("fb", "opening_times"), ("sh", "hours"), ("ws", "hours")):
            for status in ("confirmed", "unconfirmed", "differs_review", "none_published"):
                with self.subTest(kind=kind, status=status):
                    x = item(verified_on=OLD)
                    home = dict(http=200, final_url=x["website"])
                    with patch.object(discover, "site_pages", return_value=(home, [(x["website"], "Test")])), \
                         patch.object(discover, "read_sources", return_value={}), \
                         patch.object(discover, "hand_checked", return_value=False), \
                         patch.object(discover, "card_check", return_value=None), \
                         patch.object(discover, "confirm_times", return_value=(status, None, "test")), \
                         patch.object(discover, "extract_times", return_value=None), \
                         patch.object(discover, "times_gate_apply"), \
                         patch.object(discover, "enforce_protected_times"), \
                         patch("intelligent_rails.note"):
                        discover.cross_check_times([x], kind, field, today=datetime.date(2026, 11, 7), threads=1)
                    self.assertEqual(x["verified_on"], "2026-11-07" if status == "confirmed" else OLD)


if __name__ == "__main__":
    unittest.main()
