"""Tests for scripts/publish_one.py. Every write stays in a temp folder."""
import copy
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import classify
import compact
import phone_lock
import place_facts
import publish_one


def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


class TestPublishOne(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.overrides = os.path.join(self.temp_dir, "overrides")
        os.makedirs(self.overrides)
        _dump(os.path.join(self.overrides, "approved_new_places.json"),
              {"foodbanks": {}, "shelters": {}, "warmspaces": {}})
        self.fb = {
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
                    "givefood": "",
                },
                {
                    "id": "existing-fb-2",
                    "type": "foodbank",
                    "name": "Existing Food Bank 2",
                    "foodbank": "Existing Food Bank 2",
                    "address": "2 Road, Town, AA1 1AB",
                    "postcode": "AA1 1AB",
                    "lat": 51.6,
                    "lng": -0.2,
                    "phone": "01234 567891",
                    "tel": "01234567891",
                    "website": "https://fb2.example.org",
                    "givefood": "",
                },
            ],
        }
        with open(os.path.join(self.temp_dir, "data.full.js"), "w", encoding="utf-8") as f:
            f.write("window.FB_DATA=" + json.dumps(self.fb) + ";")
        with open(os.path.join(self.temp_dir, "data.js"), "w", encoding="utf-8") as f:
            f.write(compact.encode(self.fb))
        self.sh = {
            "updated": "2026-11-06",
            "items": [{
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
            }],
            "recently_closed": [],
            "sources": {},
        }
        with open(os.path.join(self.temp_dir, "shelters.js"), "w", encoding="utf-8") as f:
            f.write("var SHELTERS=" + json.dumps(self.sh) + ";\n")
        self.ws = {
            "updated": "2026-11-06",
            "items": [{
                "id": "existing-ws-1",
                "name": "Existing Warm Space 1",
                "phone": "01234 567892",
                "tel": "01234567892",
                "address": "3 Avenue, Town, CC1 1CC",
                "postcode": "CC1 1CC",
                "lat": 51.5,
                "lng": -0.1,
            }],
            "recently_closed": [],
            "sources": {},
        }
        with open(os.path.join(self.temp_dir, "warmspaces.js"), "w", encoding="utf-8") as f:
            f.write("var WARMSPACES=" + json.dumps(self.ws) + ";\n")
        self.stamp = {
            "run": "2026-11-06T12:00:00+00:00",
            "kind": "refresh",
            "label": "6 Nov 2026, 12:00",
            "layers": {
                "fb": {"run": "2026-11-06T12:00:00+00:00", "label": "6 Nov 2026, 12:00"},
                "sh": {"run": "2026-11-06T12:00:00+00:00", "label": "6 Nov 2026, 12:00"},
                "ws": {"run": "2026-11-06T12:00:00+00:00", "label": "6 Nov 2026, 12:00"},
            },
        }
        self._write_stamp(self.stamp)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_stamp(self, obj):
        with open(os.path.join(self.temp_dir, "stamp.js"), "w", encoding="utf-8") as f:
            f.write("window.FB_STAMP=" + json.dumps(obj) + ";\n")

    def _read_stamp(self):
        text = open(os.path.join(self.temp_dir, "stamp.js"), encoding="utf-8").read()
        return json.loads(text.split("=", 1)[1].rstrip().rstrip(";"))

    def _approve(self, layer, item_id, note="Approved"):
        path = os.path.join(self.overrides, "approved_new_places.json")
        doc = json.load(open(path, encoding="utf-8"))
        doc[layer][item_id] = note
        _dump(path, doc)

    def _phones(self, item_id, number="01234 999999"):
        _dump(os.path.join(self.overrides, "phones.json"), {item_id: number})
        _dump(os.path.join(self.overrides, "phone_sources.json"),
              {item_id: {"phone": number, "source": "https://example.com", "own_page": True}})

    def test_insert_new_approved_foodbank_updates_both_files_and_only_its_stamp(self):
        self._approve("foodbanks", "new-fb-1")
        self._phones("new-fb-1")
        _dump(os.path.join(self.overrides, "foodbank_approved_new.json"), {
            "new-fb-1": {
                "name": "New Approved Food Bank",
                "address": "10 High St, AA1 2BB",
                "postcode": "AA1 2BB",
                "lat": 51.51,
                "lng": -0.11,
                "phone": "09999 000000",
            }
        })
        shelters_before = open(os.path.join(self.temp_dir, "shelters.js"), encoding="utf-8").read()
        warm_before = open(os.path.join(self.temp_dir, "warmspaces.js"), encoding="utf-8").read()
        res = publish_one.publish_one(self.temp_dir, "foodbanks", "new-fb-1")
        self.assertEqual(res["phone"], "01234 999999")
        self.assertEqual(res["tel"], "01234999999")
        self.assertNotIn("09999", res.get("phone") or "")
        _, full, _ = publish_one.read_layer(self.temp_dir, "foodbanks")
        ids = [item["id"] for item in full["items"]]
        self.assertEqual(ids, ["existing-fb-1", "existing-fb-2", "new-fb-1"])
        self.assertEqual(full["items"][0], self.fb["items"][0])
        self.assertEqual(full["items"][1], self.fb["items"][1])
        js = open(os.path.join(self.temp_dir, "data.js"), encoding="utf-8").read()
        self.assertIn("new-fb-1", js)
        self.assertEqual(js, compact.encode(full))
        self.assertEqual(shelters_before, open(os.path.join(self.temp_dir, "shelters.js"), encoding="utf-8").read())
        self.assertEqual(warm_before, open(os.path.join(self.temp_dir, "warmspaces.js"), encoding="utf-8").read())
        stamp = self._read_stamp()
        self.assertEqual(stamp["layers"]["sh"], self.stamp["layers"]["sh"])
        self.assertEqual(stamp["layers"]["ws"], self.stamp["layers"]["ws"])
        self.assertNotEqual(stamp["layers"]["fb"]["run"], self.stamp["layers"]["fb"]["run"])
        self.assertEqual(stamp["kind"], "refresh")

    def _shelter_for_tag_test(self):
        self._approve("shelters", "tag-sh")
        _dump(os.path.join(self.overrides, "shelters_manual.json"), [{
            "id": "tag-sh", "name": "Tag Test Shelter", "phone": "01234 777777", "address": "Somewhere",
            "postcode": "BB1 2CC", "lat": 51.5, "lng": -0.1, "groups": [], "who_for": "Adults 18+",
        }])

    def test_publish_moves_index_cache_tags_with_the_files_it_writes(self):
        """7 Nov 2026: #449 committed a new data.js and stamp.js but left index.html on the old ?v= tags, so visitors
        could keep the old copies (rule 38) and test_index_stamps_match_file_hashes went red. Every publish must re-tag."""
        import re as _re
        import seo_meta
        idx = os.path.join(self.temp_dir, "index.html")
        stale = ('<head><script data-hm src="data.js?v=h000000000000" type="text/plain"></script>'
                 '<script src="stamp.js?v=h111111111111"></script><script src="tiles.js?v=hkeepme"></script></head>')
        with open(idx, "w", encoding="utf-8") as f:
            f.write(stale)
        publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        h = open(idx, encoding="utf-8").read()
        for name in ("data", "stamp"):
            want = seo_meta.content_stamp(self.temp_dir, name + ".js")
            self.assertEqual(_re.findall(r'src="%s\.js\?v=([^"]*)"' % name, h), [want], name)
        self.assertIn('data-hm src="data.js?v=', h)
        self.assertIn("tiles.js?v=hkeepme", h)
        before_sh = h
        self._shelter_for_tag_test()
        publish_one.publish_one(self.temp_dir, "shelters", "tag-sh")
        h = open(idx, encoding="utf-8").read()
        self.assertNotEqual(h, before_sh, "a shelters publish moves stamp.js, so its tag must move too")
        self.assertIn('stamp.js?v=%s"' % seo_meta.content_stamp(self.temp_dir, "stamp.js"), h)

    def test_dry_run_never_touches_index_html(self):
        idx = os.path.join(self.temp_dir, "index.html")
        with open(idx, "w", encoding="utf-8") as f:
            f.write('<script src="data.js?v=h000000000000"></script>')
        publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1", dry_run=True)
        self.assertEqual(open(idx, encoding="utf-8").read(), '<script src="data.js?v=h000000000000"></script>')

    def test_names_file_overwrites_a_nonempty_published_name(self):
        _dump(os.path.join(self.overrides, "foodbank_names.json"), {
            "existing-fb-1": {"name": "Asked Name", "foodbank": "Asked Food Bank"},
        })
        res = publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertEqual(res["name"], "Asked Name")
        self.assertEqual(res["foodbank"], "Asked Food Bank")
        items = [copy.deepcopy(self.fb["items"][0])]
        classify.classify(items, self.temp_dir)
        self.assertEqual(items[0]["name"], "Existing Food Bank 1")
        named = copy.deepcopy(self.fb["items"][0])
        named["name"] = "Asked Name"
        named["foodbank"] = "Asked Food Bank"
        self.assertEqual(res["name"], named["name"])
        self.assertEqual(res["foodbank"], named["foodbank"])

    def test_groups_overlay_overwrites_nonempty_groups_via_place_facts(self):
        manual = {
            "existing-fb-1": {
                "kind": "client",
                "evidence": "checked on the food bank's own page",
                "groups": ["Families"],
            }
        }
        _dump(os.path.join(self.overrides, "foodbank_manual.json"), manual)
        published = copy.deepcopy(self.fb["items"][0])
        published["groups"] = ["Stale"]
        _, data, _ = publish_one.read_layer(self.temp_dir, "foodbanks")
        data["items"][0] = published
        publish_one._write_layer(self.temp_dir, "foodbanks", "window.FB_DATA=", data, ";")
        stuck = copy.deepcopy(published)
        place_facts.stamp([stuck], manual, fill_missing=True)
        self.assertEqual(stuck["groups"], ["Stale"])
        res = publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertEqual(res["groups"], ["Families"])
        fresh = copy.deepcopy(published)
        fresh["groups"] = []
        place_facts.stamp([fresh], manual, fill_missing=True)
        self.assertEqual(res["groups"], fresh["groups"])

    def test_classify_sets_kind_and_manual_phone_does_not_beat_overlay_phone(self):
        _dump(os.path.join(self.overrides, "foodbank_manual.json"), {
            "existing-fb-1": {
                "kind": "warehouse",
                "evidence": "depot, donations only",
                "phone": "01111 111111",
            }
        })
        self._phones("existing-fb-1", "01234 999999")
        alone = [copy.deepcopy(self.fb["items"][0])]
        classify.classify(alone, self.temp_dir)
        self.assertEqual(alone[0]["kind"], "warehouse")
        self.assertEqual(alone[0]["phone"], "01111 111111")
        res = publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertEqual(res["kind"], "warehouse")
        self.assertEqual(res["label_en"], alone[0]["label_en"])
        self.assertEqual(res["phone"], "01234 999999")
        self.assertEqual(res["tel"], "01234999999")
        _, full, _ = publish_one.read_layer(self.temp_dir, "foodbanks")
        self.assertEqual(full["items"][1], self.fb["items"][1])

    def test_opening_times_follow_the_builder_assignment(self):
        _dump(os.path.join(self.overrides, "opening_times.json"), {
            "existing-fb-1": {"status": "TIMES_FOUND", "structured": {"tue": [["10:00", "12:00"]]}},
        })
        res = publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertEqual(res["opening_times"]["structured"]["tue"], [["10:00", "12:00"]])
        _dump(os.path.join(self.overrides, "foodbank_manual.json"), {
            "existing-fb-1": {
                "kind": "warehouse",
                "evidence": "depot",
                "drop_opening_times": True,
            }
        })
        dropped = publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertIsNone(dropped["opening_times"])
        self.assertEqual(dropped["kind"], "warehouse")

    def test_rule_88_rejects_an_approved_foodbank_with_no_phone(self):
        self._approve("foodbanks", "existing-fb-1")
        _, data, _ = publish_one.read_layer(self.temp_dir, "foodbanks")
        data["items"][0]["phone"] = ""
        data["items"][0]["tel"] = ""
        publish_one._write_layer(self.temp_dir, "foodbanks", "window.FB_DATA=", data, ";")
        full_before = open(os.path.join(self.temp_dir, "data.full.js"), encoding="utf-8").read()
        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertIn("no verified phone", str(ctx.exception))
        self.assertIn("rule 88", str(ctx.exception))
        self.assertEqual(full_before, open(os.path.join(self.temp_dir, "data.full.js"), encoding="utf-8").read())

    def test_reject_unapproved_new_foodbank(self):
        self._phones("unapproved-fb")
        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "foodbanks", "unapproved-fb")
        self.assertIn("Rejecting unapproved new foodbanks listing", str(ctx.exception))

    def test_notice_overwrites_a_nonempty_notice(self):
        _, data, _ = publish_one.read_layer(self.temp_dir, "foodbanks")
        data["items"][0]["notice"] = "Old notice"
        publish_one._write_layer(self.temp_dir, "foodbanks", "window.FB_DATA=", data, ";")
        _dump(os.path.join(self.overrides, "foodbank_notices.json"), {
            "existing-fb-1": {"notice": "Call ahead today"},
        })
        res = publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertEqual(res["notice"], "Call ahead today")

    def test_other_id_guard_rejects_a_sibling_edit(self):
        original = copy.deepcopy(self.fb["items"])
        tampered = copy.deepcopy(original)
        tampered[1]["name"] = "Mutated"
        with self.assertRaises(RuntimeError) as ctx:
            publish_one.assert_whole_file(original, tampered, "existing-fb-1", False)
        self.assertIn("other id existing-fb-2 was modified", str(ctx.exception))

    def test_stamp_parse_error_does_not_wipe_other_layers(self):
        path = os.path.join(self.temp_dir, "stamp.js")
        open(path, "w", encoding="utf-8").write("window.FB_STAMP=not-json;\n")
        before = open(path, encoding="utf-8").read()
        full_before = open(os.path.join(self.temp_dir, "data.full.js"), encoding="utf-8").read()
        with self.assertRaises(RuntimeError) as ctx:
            publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertIn("refusing", str(ctx.exception))
        self.assertEqual(before, open(path, encoding="utf-8").read())
        self.assertEqual(full_before, open(os.path.join(self.temp_dir, "data.full.js"), encoding="utf-8").read())
        open(path, "w", encoding="utf-8").write("window.FB_STAMP={};\n")
        with self.assertRaises(RuntimeError):
            publish_one.bump_stamp(self.temp_dir, "shelters")
        self.assertEqual("window.FB_STAMP={};\n", open(path, encoding="utf-8").read())

    def test_bump_stamp_moves_only_the_target_layer(self):
        when = datetime.datetime(2026, 11, 6, 18, 30, tzinfo=ZoneInfo("Europe/London"))
        publish_one.bump_stamp(self.temp_dir, "shelters", now=when)
        got = self._read_stamp()
        self.assertEqual(got["layers"]["fb"], self.stamp["layers"]["fb"])
        self.assertEqual(got["layers"]["ws"], self.stamp["layers"]["ws"])
        self.assertEqual(got["layers"]["sh"]["label"], "6 Nov 2026, 18:30")
        self.assertEqual(got["kind"], "shelters")

    def test_dry_run_does_not_persist_phone_lock_or_any_file(self):
        _dump(os.path.join(self.overrides, "phone_baseline.json"), {"listings": {}})
        self._phones("existing-fb-1", "01234 888888")
        before = {}
        for dirpath, _, names in os.walk(self.temp_dir):
            for name in names:
                path = os.path.join(dirpath, name)
                before[path] = open(path, "rb").read()
        calls = []
        real = phone_lock.guard

        def spy(*args, **kwargs):
            calls.append(kwargs.get("persist_new"))
            return real(*args, **kwargs)

        phone_lock.guard = spy
        try:
            publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1", dry_run=True)
        finally:
            phone_lock.guard = real
        self.assertTrue(calls)
        self.assertTrue(all(flag is False for flag in calls))
        after = {}
        for dirpath, _, names in os.walk(self.temp_dir):
            for name in names:
                path = os.path.join(dirpath, name)
                after[path] = open(path, "rb").read()
        self.assertEqual(before, after)
        publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1", dry_run=False)
        baseline = json.load(open(os.path.join(self.overrides, "phone_baseline.json"), encoding="utf-8"))
        self.assertIn("existing-fb-1", baseline["listings"])

    def test_shelter_who_for_phone_and_per_layer_stamp(self):
        self._approve("shelters", "who-for-sh")
        _dump(os.path.join(self.overrides, "shelters_manual.json"), [{
            "id": "who-for-sh",
            "name": "Shelter With Who For",
            "phone": "01234 777777",
            "address": "Somewhere",
            "postcode": "BB1 2CC",
            "lat": 51.5,
            "lng": -0.1,
            "groups": [],
            "who_for": "Adults 18+ eligible for accommodation",
        }])
        fb_before = open(os.path.join(self.temp_dir, "data.full.js"), encoding="utf-8").read()
        res = publish_one.publish_one(self.temp_dir, "shelters", "who-for-sh")
        self.assertEqual(res["who_for"], "Adults 18+ eligible for accommodation")
        self.assertEqual(res["tel"], "01234777777")
        _, shelters, _ = publish_one.read_layer(self.temp_dir, "shelters")
        self.assertEqual([item["id"] for item in shelters["items"]], ["existing-sh-1", "who-for-sh"])
        self.assertEqual(shelters["items"][0], self.sh["items"][0])
        self.assertEqual(fb_before, open(os.path.join(self.temp_dir, "data.full.js"), encoding="utf-8").read())
        stamp = self._read_stamp()
        self.assertEqual(stamp["layers"]["fb"], self.stamp["layers"]["fb"])
        self.assertEqual(stamp["layers"]["ws"], self.stamp["layers"]["ws"])
        self.assertNotEqual(stamp["layers"]["sh"]["run"], self.stamp["layers"]["sh"]["run"])
        self.assertEqual(stamp["kind"], "shelters")

    def test_shelter_rejects_missing_who_and_missing_phone(self):
        self._approve("shelters", "no-groups-sh")
        _dump(os.path.join(self.overrides, "shelters_manual.json"), [{
            "id": "no-groups-sh",
            "name": "Shelter No Groups",
            "phone": "01234 777777",
            "address": "Somewhere",
            "postcode": "BB1 2CC",
            "lat": 51.5,
            "lng": -0.1,
            "groups": [],
            "who_for": None,
        }])
        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "shelters", "no-groups-sh")
        self.assertIn("no sourced who-it's-for", str(ctx.exception))
        self._approve("shelters", "no-phone-sh")
        _dump(os.path.join(self.overrides, "shelters_manual.json"), [{
            "id": "no-phone-sh",
            "name": "Shelter No Phone",
            "address": "Somewhere",
            "postcode": "BB1 2CC",
            "lat": 51.5,
            "lng": -0.1,
            "groups": ["Adults"],
        }])
        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "shelters", "no-phone-sh")
        self.assertIn("no verified phone", str(ctx.exception))

    def test_no_pin_rejects_a_building_name_without_a_street_word(self):
        self._approve("shelters", "hostel-building")
        _dump(os.path.join(self.overrides, "shelters_manual.json"), [{
            "id": "hostel-building",
            "name": "Referral Hostel",
            "phone": "01234 666666",
            "card_type": "referral_hostel",
            "no_pin": True,
            "address": "Riverside House",
            "town": "Sheffield",
            "area": "Sheffield",
            "groups": ["Adults"],
        }])
        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "shelters", "hostel-building")
        self.assertIn("street address not allowed", str(ctx.exception))
        self.assertIn("Riverside House", str(ctx.exception))

    def test_no_pin_rejects_lat_and_postcode_and_allows_a_town_line(self):
        self._approve("shelters", "hostel-with-coords")
        _dump(os.path.join(self.overrides, "shelters_manual.json"), [{
            "id": "hostel-with-coords",
            "name": "Referral Hostel",
            "phone": "01234 666666",
            "card_type": "referral_hostel",
            "no_pin": True,
            "address": "Sheffield",
            "town": "Sheffield",
            "postcode": "S1 1AA",
            "lat": 53.3,
            "lng": -1.4,
            "groups": ["Adults"],
        }])
        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "shelters", "hostel-with-coords")
        self.assertIn("must not have lat/lng", str(ctx.exception))
        _dump(os.path.join(self.overrides, "shelters_manual.json"), [{
            "id": "hostel-with-coords",
            "name": "Referral Hostel",
            "phone": "01234 666666",
            "card_type": "referral_hostel",
            "no_pin": True,
            "address": "Sheffield",
            "town": "Sheffield",
            "postcode": "S1 1AA",
            "groups": ["Adults"],
        }])
        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "shelters", "hostel-with-coords")
        self.assertIn("must not have postcode", str(ctx.exception))
        self._approve("shelters", "town-hostel")
        _dump(os.path.join(self.overrides, "shelters_manual.json"), [{
            "id": "town-hostel",
            "name": "Town Hostel",
            "phone": "01234 666666",
            "card_type": "referral_hostel",
            "no_pin": True,
            "address": "Sheffield",
            "town": "Sheffield",
            "area": "Sheffield",
            "groups": ["Adults"],
        }])
        res = publish_one.publish_one(self.temp_dir, "shelters", "town-hostel")
        self.assertEqual(res["address"], "Sheffield")
        self.assertTrue(res.get("no_pin"))
        self.assertIn(res.get("lat"), (None, ""))
        self.assertIn(res.get("postcode"), (None, ""))

    def test_refuge_is_rejected(self):
        self._approve("shelters", "safe-refuge")
        _dump(os.path.join(self.overrides, "shelters_manual.json"), [{
            "id": "safe-refuge",
            "name": "Women's Aid Safe Refuge",
            "phone": "01234 666666",
            "address": "Somewhere",
            "postcode": "S1 1AA",
            "lat": 53.3,
            "lng": -1.4,
            "groups": ["Women"],
        }])
        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "shelters", "safe-refuge")
        self.assertIn("refuge or domestic abuse", str(ctx.exception))

    def test_warmspace_manual_name_overwrites_published_name(self):
        _dump(os.path.join(self.overrides, "warmspaces_manual.json"), [{
            "id": "existing-ws-1",
            "name": "Renamed Warm Space",
            "phone": "01234 567892",
        }])
        shelters_before = open(os.path.join(self.temp_dir, "shelters.js"), encoding="utf-8").read()
        res = publish_one.publish_one(self.temp_dir, "warmspaces", "existing-ws-1")
        self.assertEqual(res["name"], "Renamed Warm Space")
        self.assertEqual(shelters_before, open(os.path.join(self.temp_dir, "shelters.js"), encoding="utf-8").read())
        stamp = self._read_stamp()
        self.assertEqual(stamp["layers"]["fb"], self.stamp["layers"]["fb"])
        self.assertEqual(stamp["layers"]["sh"], self.stamp["layers"]["sh"])
        self.assertEqual(stamp["kind"], "warmspaces")

    def test_warmspace_card_gets_last_verified(self):
        # 14 Nov 2026: a card published without last_verified crashed the next full rebuild.
        _dump(os.path.join(self.overrides, "warmspaces_manual.json"), [{"id": "existing-ws-1", "phone": "01234 567892"}])
        now = datetime.datetime(2026, 11, 14, 11, 0, tzinfo=datetime.timezone.utc)
        res = publish_one.publish_one(self.temp_dir, "warmspaces", "existing-ws-1", now=now)
        self.assertEqual(res["last_verified"], "2026-11-14")
        _, data, _ = publish_one.read_layer(self.temp_dir, "warmspaces")
        self.assertTrue(all(x.get("last_verified") for x in data["items"]))

    def test_warmspace_existing_last_verified_is_kept(self):
        self.ws["items"][0]["last_verified"] = "2026-11-10"
        with open(os.path.join(self.temp_dir, "warmspaces.js"), "w", encoding="utf-8") as f:
            f.write("var WARMSPACES=" + json.dumps(self.ws) + ";\n")
        _dump(os.path.join(self.overrides, "warmspaces_manual.json"), [{"id": "existing-ws-1", "phone": "01234 567892"}])
        res = publish_one.publish_one(self.temp_dir, "warmspaces", "existing-ws-1")
        self.assertEqual(res["last_verified"], "2026-11-10")

    def test_overlay_collection_hours_keep_a_parent_client_facing(self):
        _, data, _ = publish_one.read_layer(self.temp_dir, "foodbanks")
        data["items"].append({
            "id": "existing-fb-1/centre",
            "type": "location",
            "name": "Existing Food Bank 1 Town Centre",
            "foodbank": "Existing Food Bank 1",
            "address": "9 Other Street, Town, AA1 1ZZ",
            "postcode": "AA1 1ZZ",
            "lat": 51.52,
            "lng": -0.12,
            "phone": "01234 111111",
            "tel": "01234111111",
            "website": "https://fb1.example.org",
            "givefood": "",
        })
        publish_one._write_layer(self.temp_dir, "foodbanks", "window.FB_DATA=", data, ";")
        alone = [copy.deepcopy(item) for item in data["items"]]
        classify.classify(alone, self.temp_dir)
        parent = next(item for item in alone if item["id"] == "existing-fb-1")
        self.assertEqual(parent["kind"], "warehouse")
        _dump(os.path.join(self.overrides, "opening_times.json"), {
            "existing-fb-1": {
                "status": "TIMES_FOUND",
                "collection": True,
                "structured": {"tue": [["10:00", "12:00"]]},
            }
        })
        res = publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertNotEqual(res.get("kind"), "warehouse")
        self.assertNotIn("Donations only", res.get("label_en") or "")
        self.assertEqual(res["opening_times"]["structured"]["tue"], [["10:00", "12:00"]])
        self.assertTrue(res["opening_times"].get("collection"))

    def test_existing_card_keeps_published_phone_when_classify_copies_warehouse_number(self):
        _dump(os.path.join(self.overrides, "foodbank_manual.json"), {
            "existing-fb-1": {
                "kind": "warehouse",
                "evidence": "depot, donations only",
                "phone": "01111 111111",
            }
        })
        alone = [copy.deepcopy(self.fb["items"][0])]
        classify.classify(alone, self.temp_dir)
        self.assertEqual(alone[0]["phone"], "01111 111111")
        res = publish_one.publish_one(self.temp_dir, "foodbanks", "existing-fb-1")
        self.assertEqual(res["kind"], "warehouse")
        self.assertEqual(res["phone"], "01234 567890")
        self.assertEqual(res["tel"], "01234567890")
        self.assertNotIn("01111", res.get("phone") or "")

    def _new_ws_manual(self, item_id="new-ws-1"):
        return {
            "id": item_id,
            "name": "New Verified Warm Space",
            "phone": "01234 555555",
            "address": "1 Park Road, Town",
            "postcode": "CC1 1CD",
            "lat": 51.5,
            "lng": -0.1,
        }

    def test_new_warmspace_verified_without_evidence_is_rejected(self):
        _dump(os.path.join(self.overrides, "warmspaces_manual.json"), [self._new_ws_manual()])
        _dump(os.path.join(self.overrides, "warmspaces_verified.json"), {
            "new-ws-1": {"verified_on": "2026-11-01"},
        })
        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "warmspaces", "new-ws-1")
        self.assertRegex(str(ctx.exception).lower(), r"evidence|quote")

    def test_new_warmspace_verified_without_quote_is_rejected(self):
        _dump(os.path.join(self.overrides, "warmspaces_manual.json"), [self._new_ws_manual()])
        _dump(os.path.join(self.overrides, "warmspaces_verified.json"), {
            "new-ws-1": {
                "verified_on": "2026-11-01",
                "evidence_url": "https://example.com/hours",
            },
        })
        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "warmspaces", "new-ws-1")
        self.assertRegex(str(ctx.exception).lower(), r"evidence|quote")

    def test_new_warmspace_verified_out_of_season_is_rejected(self):
        _dump(os.path.join(self.overrides, "warmspaces_manual.json"), [self._new_ws_manual()])
        _dump(os.path.join(self.overrides, "warmspaces_verified.json"), {
            "new-ws-1": {
                "verified_on": "2025-12-01",
                "evidence_url": "https://example.com/hours",
                "day_time_quote": "Open Monday 10am to noon",
            },
        })
        when = datetime.datetime(2026, 11, 6, 12, 0, tzinfo=ZoneInfo("Europe/London"))
        with self.assertRaises(ValueError) as ctx:
            publish_one.publish_one(self.temp_dir, "warmspaces", "new-ws-1", now=when)
        self.assertIn("season", str(ctx.exception).lower())

    def test_new_warmspace_verified_with_evidence_this_season_is_allowed(self):
        _dump(os.path.join(self.overrides, "warmspaces_manual.json"), [self._new_ws_manual()])
        _dump(os.path.join(self.overrides, "warmspaces_verified.json"), {
            "new-ws-1": {
                "verified_on": "2026-11-01",
                "evidence_url": "https://example.com/hours",
                "day_time_quote": "Open Monday 10am to noon",
            },
        })
        when = datetime.datetime(2026, 11, 6, 12, 0, tzinfo=ZoneInfo("Europe/London"))
        res = publish_one.publish_one(self.temp_dir, "warmspaces", "new-ws-1", now=when)
        self.assertTrue(res.get("verified"))
        self.assertEqual(res["evidence_url"], "https://example.com/hours")
        self.assertEqual(res["verified_on"], "2026-11-01")
        self.assertEqual(res["name"], "New Verified Warm Space")

    def test_script_does_not_call_a_full_builder(self):
        src = open(os.path.join(SCRIPTS, "publish_one.py"), encoding="utf-8").read()
        for banned in ("build.py", "build_shelters", "build_warmspaces", "full_check", "times_finder", "urlopen"):
            self.assertNotIn(banned, src)
        self.assertIn('item["opening_times"] = normalise(', src)
        self.assertIn('item["opening_times"] = None', src)
        self.assertNotIn('.update({"opening_times"', src)
        self.assertNotIn(".update({'opening_times'", src)


    def test_unpublished_warmspace_takes_name_from_verified(self):
        _dump(os.path.join(self.overrides, "warmspaces_verified.json"), {
            "new-ws-1": {
                "name": "New Hall",
                "evidence_url": "https://hall.example.org/",
                "evidence_name": "hall.example.org",
                "quote": "open Tuesday 10-12",
                "day_time_quote": "open Tuesday 10-12",
                "verified_on": "2026-11-14",
                "hours": {"Tue": "10:00 - 12:00"},
                "phone": "01234 000000",
                "postcode": "M13 9PL",
                "lat": 53.46,
                "lng": -2.23,
            },
            "existing-ws-1": {
                "name": "Should Not Replace",
                "evidence_url": "https://other.example.org/",
                "evidence_name": "other.example.org",
                "quote": "open Wednesday 10-12",
                "day_time_quote": "open Wednesday 10-12",
                "verified_on": "2026-11-14",
                "phone": "01234 567892",
                "postcode": "CC1 1CC",
            },
        })
        card = publish_one.rebuild_warmspace(self.temp_dir, "new-ws-1", None, [], False)
        self.assertEqual(card["name"], "New Hall")
        self.assertEqual(card["website"], "https://hall.example.org/")
        self.assertEqual(card["source_url"], "https://hall.example.org/")
        self.assertEqual(card["source"], "hall.example.org")
        self.assertEqual(card["phone"], "01234 000000")
        kept = publish_one.rebuild_warmspace(
            self.temp_dir,
            "existing-ws-1",
            {"id": "existing-ws-1", "name": "Existing Warm Space 1", "website": "https://live.example.org/", "phone": "01234 567892"},
            [],
            False,
        )
        self.assertEqual(kept["name"], "Existing Warm Space 1")
        self.assertEqual(kept["website"], "https://live.example.org/")

class TestDetect(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.overrides = os.path.join(self.temp_dir, "overrides")
        os.makedirs(self.overrides)
        subprocess.check_call(["git", "init", "-q"], cwd=self.temp_dir)
        subprocess.check_call(["git", "config", "user.name", "Test"], cwd=self.temp_dir)
        subprocess.check_call(["git", "config", "user.email", "test@example.org"], cwd=self.temp_dir)
        _dump(os.path.join(self.overrides, "foodbank_names.json"), {"fb-1": {"name": "Old"}})
        _dump(os.path.join(self.overrides, "approved_new_places.json"),
              {"foodbanks": {}, "shelters": {}, "warmspaces": {}})
        subprocess.check_call(["git", "add", "-A"], cwd=self.temp_dir)
        subprocess.check_call(["git", "commit", "-m", "baseline", "-q"], cwd=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _commit(self, message):
        subprocess.check_call(["git", "add", "-A"], cwd=self.temp_dir)
        subprocess.check_call(["git", "commit", "-m", message, "-q"], cwd=self.temp_dir)

    def test_names_change_is_a_foodbank_id(self):
        _dump(os.path.join(self.overrides, "foodbank_names.json"),
              {"fb-1": {"name": "New"}, "fb-2": {"name": "Second"}})
        self._commit("names")
        self.assertEqual(
            publish_one.detect_from_commit(self.temp_dir, "HEAD"),
            [("foodbanks", "fb-1"), ("foodbanks", "fb-2")],
        )

    def test_approved_new_places_uses_the_layer_key_not_the_filename(self):
        _dump(os.path.join(self.overrides, "approved_new_places.json"), {
            "foodbanks": {},
            "shelters": {"sh-9": "ok"},
            "warmspaces": {"ws-3": "ok"},
        })
        self._commit("approve shelter and warm space")
        self.assertEqual(
            publish_one.detect_from_commit(self.temp_dir, "HEAD"),
            [("shelters", "sh-9"), ("warmspaces", "ws-3")],
        )

    def test_refresh_output_commit_does_nothing(self):
        with open(os.path.join(self.temp_dir, "data.js"), "w", encoding="utf-8") as f:
            f.write("window.FB_DATA={};\n")
        os.makedirs(os.path.join(self.temp_dir, "reports"), exist_ok=True)
        with open(os.path.join(self.temp_dir, "reports", "daily.md"), "w", encoding="utf-8") as f:
            f.write("refresh\n")
        self._commit("3x-daily food bank refresh")
        self.assertEqual(publish_one.detect_from_commit(self.temp_dir, "HEAD"), [])

    def test_overlay_alongside_refresh_output_is_still_detected(self):
        _dump(os.path.join(self.overrides, "foodbank_names.json"), {"fb-1": {"name": "New"}})
        with open(os.path.join(self.temp_dir, "data.js"), "w", encoding="utf-8") as f:
            f.write("window.FB_DATA={};\n")
        os.makedirs(os.path.join(self.temp_dir, "reports"), exist_ok=True)
        with open(os.path.join(self.temp_dir, "reports", "daily.md"), "w", encoding="utf-8") as f:
            f.write("note\n")
        os.makedirs(os.path.join(self.temp_dir, "docs"), exist_ok=True)
        with open(os.path.join(self.temp_dir, "docs", "note.md"), "w", encoding="utf-8") as f:
            f.write("doc\n")
        self._commit("overlay with report and doc")
        self.assertEqual(
            publish_one.detect_from_commit(self.temp_dir, "HEAD"),
            [("foodbanks", "fb-1")],
        )

    def test_corrupt_overlay_alongside_a_report_still_fails(self):
        with open(os.path.join(self.overrides, "foodbank_names.json"), "w", encoding="utf-8") as f:
            f.write("{not-json")
        os.makedirs(os.path.join(self.temp_dir, "reports"), exist_ok=True)
        with open(os.path.join(self.temp_dir, "reports", "daily.md"), "w", encoding="utf-8") as f:
            f.write("note\n")
        self._commit("corrupt with report")
        with self.assertRaises(RuntimeError) as ctx:
            publish_one.detect_from_commit(self.temp_dir, "HEAD")
        self.assertIn("cannot be determined", str(ctx.exception))

    def test_duplicate_id_in_list_overlay_is_ambiguous(self):
        _dump(os.path.join(self.overrides, "shelters_manual.json"), [
            {"id": "sh-1", "name": "A"},
            {"id": "sh-1", "name": "B"},
        ])
        self._commit("duplicate list id")
        with self.assertRaises(RuntimeError) as ctx:
            publish_one.detect_from_commit(self.temp_dir, "HEAD")
        self.assertIn("duplicate", str(ctx.exception).lower())
        self.assertIn("sh-1", str(ctx.exception))

    def test_corrupt_overlay_fails_visibly(self):
        with open(os.path.join(self.overrides, "foodbank_names.json"), "w", encoding="utf-8") as f:
            f.write("{not-json")
        self._commit("corrupt")
        with self.assertRaises(RuntimeError) as ctx:
            publish_one.detect_from_commit(self.temp_dir, "HEAD")
        self.assertIn("cannot be determined", str(ctx.exception))

    def test_unknown_overlay_fails_visibly(self):
        _dump(os.path.join(self.overrides, "mystery.json"), {"x": 1})
        self._commit("mystery")
        with self.assertRaises(RuntimeError) as ctx:
            publish_one.detect_from_commit(self.temp_dir, "HEAD")
        self.assertIn("unknown overlay", str(ctx.exception).lower())

    def test_closure_auto_undone_is_a_warmspaces_overlay(self):
        _dump(os.path.join(self.overrides, "closure_auto_undone.json"), {})
        self._commit("empty lock")
        _dump(os.path.join(self.overrides, "closure_auto_undone.json"), {
            "ww-57952305": {"evidence": "The Vivarium and Nature's Library are now closed until May 2027"}
        })
        self._commit("lock gallery wording")
        self.assertEqual(
            publish_one.detect_from_commit(self.temp_dir, "HEAD"),
            [("warmspaces", "ww-57952305")],
        )

    def test_council_block_change_fails_visibly(self):
        _dump(os.path.join(self.overrides, "shelters_contacts.json"), {"_councils": {"A": {"council_phone": "1"}}})
        self._commit("base contacts")
        _dump(os.path.join(self.overrides, "shelters_contacts.json"), {"_councils": {"A": {"council_phone": "2"}}})
        self._commit("councils")
        with self.assertRaises(RuntimeError) as ctx:
            publish_one.detect_from_commit(self.temp_dir, "HEAD")
        self.assertIn("cannot be determined exactly", str(ctx.exception))

    def test_swep_only_commit_does_nothing(self):
        _dump(os.path.join(self.overrides, "swep_sources.json"), [{"council": "X", "url": "https://example.org"}])
        self._commit("swep")
        self.assertEqual(publish_one.detect_from_commit(self.temp_dir, "HEAD"), [])

    def test_list_command_prints_json_only(self):
        _dump(os.path.join(self.overrides, "shelters_manual.json"), [
            {"id": "sh-2", "name": "B"},
            {"id": "sh-1", "name": "A"},
        ])
        self._commit("manual")
        script = os.path.join(SCRIPTS, "publish_one.py")
        proc = subprocess.run(
            [sys.executable, script, "--root", self.temp_dir, "--commit", "HEAD", "--list"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {
            "foodbanks": [], "shelters": ["sh-1", "sh-2"], "warmspaces": [],
        })


if __name__ == "__main__":
    unittest.main()
