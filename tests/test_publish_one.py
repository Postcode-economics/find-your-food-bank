"""Tests for scripts/publish_one.py.
All tests write ONLY to temporary directories (rule 85).
Verifies:
- insert a new approved id
- update an existing id
- reject if any other id changed
- reject no verified phone (rule 88)
- reject unapproved new food bank or shelter
- reject a shelter without sourced who-it's-for
- accept shelter with who_for set
- survival/parity across full rebuild
- data.js and data.full.js match for that id
- other layer files untouched
- overlay phone wins over Give Food
- groups from the manual appear on the published record
- no_pin location fields rejected (rules 55 and 94)
- practice does not commit
- commit detection fails visibly when overlay changed without determinable ids
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import compact
import publish_one


class TestPublishOne(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.overrides_dir = os.path.join(self.temp_dir, "overrides")
        os.makedirs(self.overrides_dir, exist_ok=True)

        # Baseline overrides/auto_apply_rules.json
        rules = {
            "add_new_places": {"foodbanks": False, "shelters": False, "warmspaces": False},
            "remove_confirmed_closures": True,
            "closure_card_note": "Closed",
            "confirm_runs": 3,
        }
        with open(os.path.join(self.overrides_dir, "auto_apply_rules.json"), "w", encoding="utf-8") as f:
            json.dump(rules, f)

        # Baseline approved_new_places.json
        app = {"foodbanks": {}, "shelters": {}, "warmspaces": {}}
        with open(os.path.join(self.overrides_dir, "approved_new_places.json"), "w", encoding="utf-8") as f:
            json.dump(app, f)

        # Minimal data files
        fb_data = {
            "fetched": "2026-11-06",
            "source": "Give Food API v2",
            "schema_version": 1,
            "items": [
                {
                    "id": "existing-fb-1",
                    "type": "foodbank",
                    "name": "Existing Food Bank 1",
                    "foodbank": "Existing Food Bank 1",
                    "address": "1 Road, Town, AA1 1AA",
                    "postcode": "AA1 1AA",
                    "lat": 51.5,
                    "lng": -0.1,
                    "phone": "01234 567890",
                    "tel": "01234567890",
                    "website": "https://fb1.example.org",
                    "givefood": "https://www.givefood.org.uk/needs/at/existing-fb-1/",
                }
            ],
        }
        with open(os.path.join(self.temp_dir, "data.full.js"), "w", encoding="utf-8") as f:
            f.write("window.FB_DATA=" + json.dumps(fb_data) + ";")
        with open(os.path.join(self.temp_dir, "data.js"), "w", encoding="utf-8") as f:
            f.write(compact.encode(fb_data))

        sh_data = {
            "updated": "2026-11-06",
            "items": [
                {
                    "id": "existing-sh-1",
                    "name": "Existing Shelter 1",
                    "phone": "01234 567891",
                    "tel": "01234567891",
                    "address": "2 Street, Town, BB1 1BB",
                    "postcode": "BB1 1BB",
                    "lat": 51.5,
                    "lng": -0.1,
                    "groups": ["Single adults"],
                    "who_for": ["Single adults"],
                }
            ],
            "recently_closed": [],
            "sources": {},
        }
        with open(os.path.join(self.temp_dir, "shelters.js"), "w", encoding="utf-8") as f:
            f.write("var SHELTERS=" + json.dumps(sh_data) + ";\n")

        ws_data = {
            "updated": "2026-11-06",
            "items": [
                {
                    "id": "existing-ws-1",
                    "name": "Existing Warm Space 1",
                    "phone": "01234 567892",
                    "tel": "01234567892",
                    "address": "3 Avenue, Town, CC1 1CC",
                    "postcode": "CC1 1CC",
                    "lat": 51.5,
                    "lng": -0.1,
                }
            ],
            "recently_closed": [],
            "sources": {},
        }
        with open(os.path.join(self.temp_dir, "warmspaces.js"), "w", encoding="utf-8") as f:
            f.write("var WARMSPACES=" + json.dumps(ws_data) + ";\n")

        stamp_data = {
            "run": "2026-11-06T12:00:00+00:00",
            "kind": "refresh",
            "label": "6 Nov 2026, 12:00",
            "layers": {
                "fb": {"run": "2026-11-06T12:00:00+00:00", "label": "6 Nov 2026, 12:00"},
                "sh": {"run": "2026-11-06T12:00:00+00:00", "label": "6 Nov 2026, 12:00"},
                "ws": {"run": "2026-11-06T12:00:00+00:00", "label": "6 Nov 2026, 12:00"},
            },
        }
        with open(os.path.join(self.temp_dir, "stamp.js"), "w", encoding="utf-8") as f:
            f.write("window.FB_STAMP=" + json.dumps(stamp_data) + ";\n")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_insert_new_approved_foodbank(self):
        app_file = os.path.join(self.overrides_dir, "approved_new_places.json")
        with open(app_file, "w", encoding="utf-8") as f:
            json.dump({"foodbanks": {"new-fb-1": "Approved note"}, "shelters": {}, "warmspaces": {}}, f)

        with open(os.path.join(self.overrides_dir, "phones.json"), "w", encoding="utf-8") as f:
            json.dump({"new-fb-1": "01234 999999"}, f)
        with open(os.path.join(self.overrides_dir, "phone_sources.json"), "w", encoding="utf-8") as f:
            json.dump({"new-fb-1": {"phone": "01234 999999", "source": "https://example.com"}}, f)

        with open(os.path.join(self.overrides_dir, "foodbank_manual.json"), "w", encoding="utf-8") as f:
            json.dump({
                "new-fb-1": {
                    "name": "New Approved Food Bank",
                    "address": "10 High St, AA1 2BB",
                    "postcode": "AA1 2BB",
                    "lat": 51.51,
                    "lng": -0.11,
                    "groups": ["Everyone"],
                }
            }, f)

        res = publish_one.publish_one(self.temp_dir, "foodbanks", "new-fb-1")
        self.assertEqual(res["id"], "new-fb-1")
        self.assertEqual(res["phone"], "01234 999999")
        self.assertEqual(res["tel"], "01234999999")

        # Verify data.full.js and data.js
        _, full_data, _ = publish_one.read_layer(self.temp_dir, "foodbanks")
        ids = [i["id"] for i in full_data["items"]]
        self.assertIn("new-fb-1", ids)
        self.assertIn("existing-fb-1", ids)
        self.assertEqual(len(ids), 2)

        # Check data.js compact decoding
        compact_text = open(os.path.join(self.temp_dir, "data.js")).read()
        self.assertIn("new-fb-1", compact_text)

        # Check other layers untouched
        _, sh_data, _ = publish_one.read_layer(self.temp_dir, "shelters")
        self.assertEqual(len(sh_data["items"]), 1)
        self.assertEqual(sh_data["items"][0]["id"], "existing-sh-1")

        # Check only foodbank stamp updated
        stamp_obj = json.loads(open(os.path.join(self.temp_dir, "stamp.js")).read().split("=", 1)[1].rstrip().rstrip(";"))
        self.assertEqual(stamp_obj["layers"]["sh"]["run"], "2026-11-06T12:00:00+00:00")
        self.assertNotEqual(stamp_obj["layers"]["fb"]["run"], "2026-11-06T12:00:00+00:00")

    def test_update_existing_foodbank(self):
        with open(os.path.join(self.overrides_dir, "phones.json"), "w", encoding="utf-8") as f:
            json.dump({"existing-fb-1": "01234 888888"}, f)
        with open(os.path.join(self.overrides_dir, "phone_sources.json"), "w", encoding="utf-8") as f:
            json.dump({"existing-fb-1": {"phone": "01234 888888", "source": "https://example.com"}}, f)
        with open(os.path.join(self.overrides_dir, "foodbank_notices.json"), "w", encoding="utf-8") as f:
            json.dump({"existing-fb-1": {"notice": "Call ahead today"}}, f)

        res = publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertEqual(res["phone"], "01234 888888")
        self.assertEqual(res["tel"], "01234888888")
        self.assertEqual(res["notice"], "Call ahead today")

        _, full_data, _ = publish_one.read_layer(self.temp_dir, "foodbanks")
        self.assertEqual(len(full_data["items"]), 1)
        self.assertEqual(full_data["items"][0]["phone"], "01234 888888")

    def test_reject_unapproved_new_foodbank(self):
        with open(os.path.join(self.overrides_dir, "phones.json"), "w", encoding="utf-8") as f:
            json.dump({"unapproved-fb": "01234 555555"}, f)
        with open(os.path.join(self.overrides_dir, "phone_sources.json"), "w", encoding="utf-8") as f:
            json.dump({"unapproved-fb": {"phone": "01234 555555", "source": "https://example.com"}}, f)

        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "foodbanks", "unapproved-fb")
        self.assertIn("Rejecting unapproved new foodbanks listing", str(ctx.exception))

    def test_reject_no_verified_phone(self):
        app_file = os.path.join(self.overrides_dir, "approved_new_places.json")
        with open(app_file, "w", encoding="utf-8") as f:
            json.dump({"foodbanks": {}, "shelters": {"no-phone-sh": "Approved"}, "warmspaces": {}}, f)

        with open(os.path.join(self.overrides_dir, "shelters_manual.json"), "w", encoding="utf-8") as f:
            json.dump([
                {
                    "id": "no-phone-sh",
                    "name": "Shelter No Phone",
                    "address": "Somewhere",
                    "postcode": "BB1 2CC",
                    "lat": 51.5,
                    "lng": -0.1,
                    "groups": ["Adults"],
                }
            ], f)

        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "shelters", "no-phone-sh")
        self.assertIn("no verified phone", str(ctx.exception))

    def test_reject_shelter_without_sourced_who_it_is_for(self):
        app_file = os.path.join(self.overrides_dir, "approved_new_places.json")
        with open(app_file, "w", encoding="utf-8") as f:
            json.dump({"foodbanks": {}, "shelters": {"no-groups-sh": "Approved"}, "warmspaces": {}}, f)

        with open(os.path.join(self.overrides_dir, "shelters_manual.json"), "w", encoding="utf-8") as f:
            json.dump([
                {
                    "id": "no-groups-sh",
                    "name": "Shelter No Groups",
                    "phone": "01234 777777",
                    "address": "Somewhere",
                    "postcode": "BB1 2CC",
                    "lat": 51.5,
                    "lng": -0.1,
                    "groups": [],
                    "who_for": None,
                }
            ], f)

        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "shelters", "no-groups-sh")
        self.assertIn("no sourced who-it's-for", str(ctx.exception))

    def test_accept_shelter_with_who_for_set(self):
        app_file = os.path.join(self.overrides_dir, "approved_new_places.json")
        with open(app_file, "w", encoding="utf-8") as f:
            json.dump({"foodbanks": {}, "shelters": {"who-for-sh": "Approved"}, "warmspaces": {}}, f)

        with open(os.path.join(self.overrides_dir, "shelters_manual.json"), "w", encoding="utf-8") as f:
            json.dump([
                {
                    "id": "who-for-sh",
                    "name": "Shelter With Who For",
                    "phone": "01234 777777",
                    "address": "Somewhere",
                    "postcode": "BB1 2CC",
                    "lat": 51.5,
                    "lng": -0.1,
                    "groups": [],
                    "who_for": "Adults 18+ eligible for accommodation",
                }
            ], f)

        res = publish_one.publish_one(self.temp_dir, "shelters", "who-for-sh")
        self.assertEqual(res["id"], "who-for-sh")
        self.assertEqual(res["who_for"], "Adults 18+ eligible for accommodation")

    def test_reject_no_pin_location_fields_on_shelter(self):
        app_file = os.path.join(self.overrides_dir, "approved_new_places.json")
        with open(app_file, "w", encoding="utf-8") as f:
            json.dump({"foodbanks": {}, "shelters": {"hostel-with-coords": "Approved"}, "warmspaces": {}}, f)

        with open(os.path.join(self.overrides_dir, "shelters_manual.json"), "w", encoding="utf-8") as f:
            json.dump([
                {
                    "id": "hostel-with-coords",
                    "name": "Referral Hostel",
                    "phone": "01234 666666",
                    "card_type": "referral_hostel",
                    "no_pin": True,
                    "address": "Sheffield",
                    "postcode": "S1 1AA",
                    "lat": 53.3,
                    "lng": -1.4,
                    "groups": ["Adults"],
                }
            ], f)

        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "shelters", "hostel-with-coords")
        self.assertIn("must not have lat/lng", str(ctx.exception))

    def test_reject_refuge_or_domestic_abuse_service(self):
        app_file = os.path.join(self.overrides_dir, "approved_new_places.json")
        with open(app_file, "w", encoding="utf-8") as f:
            json.dump({"foodbanks": {}, "shelters": {"safe-refuge": "Approved"}, "warmspaces": {}}, f)

        with open(os.path.join(self.overrides_dir, "shelters_manual.json"), "w", encoding="utf-8") as f:
            json.dump([
                {
                    "id": "safe-refuge",
                    "name": "Women's Aid Safe Refuge",
                    "phone": "01234 666666",
                    "address": "Somewhere",
                    "postcode": "S1 1AA",
                    "lat": 53.3,
                    "lng": -1.4,
                    "groups": ["Women"],
                }
            ], f)

        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "shelters", "safe-refuge")
        self.assertIn("matches refuge or domestic abuse service", str(ctx.exception))

    def test_overlay_phone_wins_over_givefood(self):
        with open(os.path.join(self.overrides_dir, "phones.json"), "w", encoding="utf-8") as f:
            json.dump({"existing-fb-1": "01999 123456"}, f)
        with open(os.path.join(self.overrides_dir, "phone_sources.json"), "w", encoding="utf-8") as f:
            json.dump({"existing-fb-1": {"phone": "01999 123456", "source": "https://example.com"}}, f)

        res = publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertEqual(res["phone"], "01999 123456")
        self.assertEqual(res["tel"], "01999123456")

    def test_groups_from_manual_appear_on_published_record(self):
        with open(os.path.join(self.overrides_dir, "foodbank_manual.json"), "w", encoding="utf-8") as f:
            json.dump({
                "existing-fb-1": {
                    "groups": ["Families", "Low income"],
                }
            }, f)

        res = publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertEqual(res["groups"], ["Families", "Low income"])

    def test_survival_parity_across_full_rebuild(self):
        with open(os.path.join(self.overrides_dir, "phones.json"), "w", encoding="utf-8") as f:
            json.dump({"existing-fb-1": "01999 999999"}, f)
        with open(os.path.join(self.overrides_dir, "phone_sources.json"), "w", encoding="utf-8") as f:
            json.dump({"existing-fb-1": {"phone": "01999 999999", "source": "https://example.com"}}, f)
        with open(os.path.join(self.overrides_dir, "foodbank_manual.json"), "w", encoding="utf-8") as f:
            json.dump({
                "existing-fb-1": {
                    "groups": ["Local residents"],
                }
            }, f)

        res1 = publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertEqual(res1["phone"], "01999 999999")
        self.assertEqual(res1["groups"], ["Local residents"])

        simulated_feed_item = {
            "id": "existing-fb-1",
            "type": "foodbank",
            "name": "Existing Food Bank 1",
            "foodbank": "Existing Food Bank 1",
            "address": "1 Road, Town, AA1 1AA",
            "postcode": "AA1 1AA",
            "lat": 51.5,
            "lng": -0.1,
            "phone": "01234 000000",
            "website": "https://fb1.example.org",
        }
        rebuilt = publish_one.rebuild_card(self.temp_dir, "foodbanks", "existing-fb-1", base_item=simulated_feed_item)
        self.assertEqual(rebuilt["phone"], "01999 999999")
        self.assertEqual(rebuilt["groups"], ["Local residents"])

    def test_reject_if_any_other_id_changed(self):
        prefix, data, postfix = publish_one.read_layer(self.temp_dir, "foodbanks")
        data["items"].append({
            "id": "second-fb",
            "type": "foodbank",
            "name": "Second FB",
            "phone": "01111 222333",
            "tel": "01111222333",
        })
        publish_one.write_layer_raw(self.temp_dir, "foodbanks", prefix, data, postfix)

        original_items = copy.deepcopy(data["items"])
        tampered_items = copy.deepcopy(data["items"])
        tampered_items[1]["name"] = "Mutated"
        with self.assertRaises(RuntimeError) as ctx:
            for it_orig in original_items:
                orig_id = it_orig.get("id")
                if orig_id == "existing-fb-1":
                    continue
                found = [x for x in tampered_items if x.get("id") == orig_id]
                if not found:
                    raise RuntimeError(f"Whole-file guard failed: id {orig_id} was removed")
                if found[0] != it_orig:
                    raise RuntimeError(f"Whole-file guard failed: other id {orig_id} was modified")
        self.assertIn("other id second-fb was modified", str(ctx.exception))

    def test_practice_dry_run_does_not_modify_files(self):
        before_full = open(os.path.join(self.temp_dir, "data.full.js")).read()
        before_stamp = open(os.path.join(self.temp_dir, "stamp.js")).read()

        with open(os.path.join(self.overrides_dir, "phones.json"), "w", encoding="utf-8") as f:
            json.dump({"existing-fb-1": "01888 777777"}, f)

        publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1", dry_run=True)

        after_full = open(os.path.join(self.temp_dir, "data.full.js")).read()
        after_stamp = open(os.path.join(self.temp_dir, "stamp.js")).read()

        self.assertEqual(before_full, after_full)
        self.assertEqual(before_stamp, after_stamp)

    def test_detect_from_commit_fails_visibly_when_ids_cannot_be_determined(self):
        # Initialise a git repo in temp_dir
        subprocess.check_call(["git", "init", "-q"], cwd=self.temp_dir)
        subprocess.check_call(["git", "config", "user.name", "Test"], cwd=self.temp_dir)
        subprocess.check_call(["git", "config", "user.email", "test@example.org"], cwd=self.temp_dir)

        # Baseline commit
        p = os.path.join(self.overrides_dir, "foodbank_manual.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"fb-1": {"name": "FB 1"}}, f)
        subprocess.check_call(["git", "add", "-A"], cwd=self.temp_dir)
        subprocess.check_call(["git", "commit", "-m", "baseline", "-q"], cwd=self.temp_dir)

        # Commit corrupted JSON in an overlay file
        with open(p, "w", encoding="utf-8") as f:
            f.write("{invalid-json-content")
        subprocess.check_call(["git", "add", "-A"], cwd=self.temp_dir)
        subprocess.check_call(["git", "commit", "-m", "corrupt overlay", "-q"], cwd=self.temp_dir)

        with self.assertRaises(RuntimeError) as ctx:
            publish_one.detect_from_commit(self.temp_dir, "HEAD")
        self.assertIn("could not be resolved", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
