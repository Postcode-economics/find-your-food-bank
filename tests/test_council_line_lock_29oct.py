"""Council lines are locked like phone numbers (Dean, 29 Oct 2026 08:55 GMT).

The 29 Oct 05:44 warm spaces refresh (477f83f73) copied council_ooh into council_phone on 16 warm spaces.
guard() let it through because the frozen baseline already held the copy while the live file did not.
A refresh may never add, change, copy or remove council_phone, council_ooh, council_label or council_label_cy:
the live bytes stay and every proposal is held for Dean in reports/pending_dean.md."""
import copy, json, os, shutil, sys, tempfile, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import phone_lock, phone_baseline, shelter_contacts

UNDONE_16 = {
    "ww-64379621": ("Bishops Stortford Methodist Church", "CM23 3AZ"),
    "ww-58212607": ("Chabad Lubavitch of Islington", "N1 8HX"),
    "ww-65437525": ("Community Warm Space", "FK10 4JA"),
    "evergreen-elderberries-welling": ("Elderberries Vintage Tea Rooms", "DA16 1PR"),
    "ww-55473505": ("Glusburn Community & Arts Centre", "BD20 8FQ"),
    "ww-57993936": ("Leigh on Sea Elim Church", "SS9 2BE"),
    "swk-london-lgbtq-community-centre": ("London LGBTQ+ Community Centre", "SE1 9JH"),
    "ww-68472828": ("North Warwickshire Citizens Advice", "CV9 1DU"),
    "ww-55475831": ("Norton Hive", "YO17 9ES"),
    "ww-55474480": ("Salvation Army in Whitleigh", "PL5 4AA"),
    "ww-65413950": ("Shipston Community Warm Hub", "CV36 4AX"),
    "ww-60625347": ("St. Thomas Church, Sutton-in-Craven", "BD20 7JS"),
    "ww-57951953": ("The Mill", "E17 7HA"),
    "ww-67526400": ("The Vale Family Hub", "DT10 1AZ"),
    "ww-55474116": ("Wesley Warm Welcome", "SS9 1SJ"),
    "ww-59974983": ("Windmill Warmbank", "N18 1PL"),
}
OOH = "01279 655261"
LABEL = "Council out-of-hours homeless line"
LABEL_CY = "Llinell ddigartrefedd y cyngor y tu allan i oriau"


def items_of(path):
    t = open(path, encoding="utf-8").read()
    return json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]


def council(item):
    return {k: item[k] for k in phone_lock.COUNCIL_FIELDS if k in item}


def held(root):
    p = os.path.join(root, "reports", "pending_dean.md")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def refresh(items, published, contacts, root, layer="warmspaces"):
    """The council steps of build_warmspaces / build_shelters, in the same order."""
    live = phone_lock.live_council(published)
    shelter_contacts.apply(items, contacts)
    for x in items:
        phone_lock.settle_council(x)
    return phone_lock.guard(items, root, via="refresh", source="feed refresh", layer=layer, persist_new=True, published=live)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, "overrides"))
        os.makedirs(os.path.join(self.d, "reports"))
        self.live = {"id": "ww-1", "name": "Test Hub", "phone": "01279 501745", "tel": "01279501745",
                     "council": "East Herts", "council_url": "https://example.gov.uk/", "council_ooh": OOH,
                     "council_label": LABEL, "council_label_cy": LABEL_CY}
        phone_lock.save({"_about": "test", "listings": {"ww-1": phone_lock.snap(self.live, "warmspaces")}}, self.d)

    def test_refresh_with_council_ooh_and_no_council_phone_leaves_it_missing_and_holds_it(self):
        item = copy.deepcopy(self.live)
        contacts = {"ww-1": {"council": "East Herts", "council_phone": OOH, "council_ooh": OOH,
                             "council_label": LABEL, "council_label_cy": LABEL_CY, "council_url": "https://example.gov.uk/"}}
        self.assertTrue(refresh([item], [self.live], contacts, self.d))
        self.assertNotIn("council_phone", item)
        self.assertEqual(council(item), council(self.live))
        log = held(self.d)
        self.assertIn("blocked, held for Dean | ww-1 | council_phone | via refresh", log)
        self.assertIn("stored (none) | proposed %s" % OOH, log)

    def test_settle_council_copy_alone_is_held(self):
        item = copy.deepcopy(self.live)
        refresh([item], [self.live], {}, self.d)
        self.assertNotIn("council_phone", item)
        self.assertIn("| ww-1 | council_phone |", held(self.d))

    def test_baseline_holding_the_copy_is_not_published(self):
        """The 29 Oct cause: the baseline had council_phone, the live file did not."""
        rec = dict(phone_lock.snap(self.live, "warmspaces"), council_phone=OOH)
        phone_lock.save({"_about": "test", "listings": {"ww-1": rec}}, self.d)
        item = copy.deepcopy(self.live)
        refresh([item], [self.live], {}, self.d)
        self.assertNotIn("council_phone", item)
        self.assertIn("| ww-1 | council_phone |", held(self.d))
        self.assertIn("source overrides/phone_baseline.json", held(self.d))

    def test_change_and_removal_are_held_byte_for_byte(self):
        item = copy.deepcopy(self.live)
        item["council_label"] = "Council main number"
        item.pop("council_label_cy")
        item["council_ooh"] = "01279 000000"
        refresh([item], [self.live], {}, self.d)
        self.assertEqual(json.dumps(council(item)).encode(), json.dumps(council(self.live)).encode())
        log = held(self.d)
        for f in ("council_label", "council_label_cy", "council_ooh"):
            self.assertIn("| ww-1 | %s |" % f, log)

    def test_hiding_a_live_line_is_held_not_applied(self):
        live = dict(self.live, council_phone="01279 111111", council_label="Council main number")
        live.pop("council_ooh")
        phone_lock.save({"_about": "test", "listings": {"ww-1": phone_lock.snap(live, "warmspaces")}}, self.d)
        item = copy.deepcopy(live)
        refresh([item], [live], {}, self.d)
        self.assertEqual(council(item), council(live))
        self.assertIn("| ww-1 | council_phone |", held(self.d))

    def test_new_place_gets_no_council_line_and_it_is_held(self):
        new = {"id": "ww-new", "name": "New Hub", "phone": "01234 567890", "tel": "01234567890"}
        contacts = {"ww-new": {"council": "X", "council_phone": OOH, "council_ooh": OOH, "council_label": LABEL}}
        refresh([new], [self.live], contacts, self.d)
        self.assertEqual(council(new), {})
        self.assertIn("| ww-new | council_phone |", held(self.d))
        frozen = phone_lock.frozen("ww-new", self.d)
        self.assertEqual(frozen.get("phone"), "01234 567890")
        self.assertFalse(set(frozen) & set(phone_lock.COUNCIL_FIELDS))

    def test_shelters_and_food_banks_are_locked_the_same_way(self):
        for layer in ("shelters", "foodbanks"):
            live = dict(self.live, id="x-" + layer)
            phone_lock.save({"_about": "t", "listings": {live["id"]: phone_lock.snap(live, layer)}}, self.d)
            item = dict(copy.deepcopy(live), council_phone=OOH)
            phone_lock.guard([item], self.d, via="refresh", layer=layer, published=[live])
            self.assertNotIn("council_phone", item, layer)
            self.assertIn("| x-%s | council_phone |" % layer, held(self.d))

    def test_unchanged_line_is_not_held(self):
        item = copy.deepcopy(self.live)
        self.assertEqual(phone_lock.guard([item], self.d, published=[self.live]), 0)
        self.assertEqual(held(self.d), "")

    def test_live_snapshot_is_not_affected_by_later_edits_to_shared_items(self):
        shared = copy.deepcopy(self.live)
        live = phone_lock.live_council([shared])
        shared["council_phone"] = OOH  # carry-forward hands back the published dict itself
        phone_lock.guard([shared], self.d, published=live)
        self.assertNotIn("council_phone", shared)

    def test_learning_consider_never_writes_a_council_field(self):
        item = copy.deepcopy(self.live)
        self.assertFalse(phone_lock.consider(item, "council_phone", OOH, root=self.d))
        self.assertNotIn("council_phone", item)
        self.assertIn("| ww-1 | council_phone |", held(self.d))


class The16(unittest.TestCase):
    def test_the_16_have_no_council_phone_and_keep_their_other_council_fields(self):
        cards = {x["id"]: x for x in items_of(os.path.join(ROOT, "warmspaces.js"))}
        base = phone_lock.load(ROOT)["listings"]
        contacts = json.load(open(os.path.join(ROOT, "overrides", "warmspaces_contacts.json"), encoding="utf-8"))
        for i, (name, pc) in UNDONE_16.items():
            x = cards[i]
            self.assertTrue(x["name"].startswith(name.split(" (")[0][:12]), (i, x["name"]))
            self.assertEqual(x["postcode"], pc, i)
            self.assertNotIn("council_phone", x, i)
            self.assertNotIn("council_phone", base[i], i)
            self.assertNotIn("council_phone", contacts[i], i)
            self.assertTrue(x["council_ooh"] and x["council_label"] and x["council_label_cy"] and x["council_url"], i)
            self.assertEqual(base[i]["council_ooh"], x["council_ooh"], i)
            self.assertTrue(x.get("tel"), i)

    def test_the_16_stay_without_council_phone_after_a_simulated_refresh(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "overrides"))
        os.makedirs(os.path.join(d, "reports"))
        shutil.copy(os.path.join(ROOT, "overrides", "phone_baseline.json"), os.path.join(d, "overrides", "phone_baseline.json"))
        published = items_of(os.path.join(ROOT, "warmspaces.js"))
        items = copy.deepcopy(published)
        refresh(items, published, shelter_contacts.load(shelter_contacts.WS), d)
        got = {x["id"]: x for x in items}
        for i in UNDONE_16:
            self.assertNotIn("council_phone", got[i], i)
        before = {x["id"]: council(x) for x in published}
        self.assertEqual({i: council(x) for i, x in got.items()}, before)  # no council field moves on any warm space
        log = held(d)
        for i in UNDONE_16:
            self.assertIn("| %s | council_phone |" % i, log)

    def test_baseline_matches_the_live_council_bytes_on_every_layer(self):
        base = phone_lock.load(ROOT)["listings"]
        for fn in ("warmspaces.js", "shelters.js", "data.full.js"):
            for x in items_of(os.path.join(ROOT, fn)):
                rec = base.get(x["id"])
                if rec is None:
                    continue
                for f in phone_lock.COUNCIL_FIELDS:
                    live = x.get(f) if isinstance(x.get(f), str) and x.get(f).strip() else None
                    self.assertEqual(live, rec.get(f), "%s %s %s" % (fn, x["id"], f))

    def test_generate_freezes_the_published_council_bytes(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "overrides"))
        for f in ("data.full.js", "warmspaces.js", "shelters.js", "overrides/shelters_contacts.json", "overrides/warmspaces_contacts.json"):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        ws = {x["id"]: x for x in items_of(os.path.join(d, "warmspaces.js"))}
        i = "ww-64379621"
        contacts = json.load(open(os.path.join(d, "overrides", "warmspaces_contacts.json"), encoding="utf-8"))
        contacts[i]["council_phone"] = ws[i]["council_ooh"]  # an override that would copy the line
        json.dump(contacts, open(os.path.join(d, "overrides", "warmspaces_contacts.json"), "w", encoding="utf-8"), ensure_ascii=False)
        phone_baseline.generate(d)
        rec = json.load(open(os.path.join(d, "overrides", "phone_baseline.json"), encoding="utf-8"))["listings"][i]
        self.assertNotIn("council_phone", rec)
        self.assertEqual(rec["council_ooh"], ws[i]["council_ooh"])

    def test_every_refresh_path_locks_to_the_live_file(self):
        for f, needle in (("build_warmspaces.py", "published=LIVE_COUNCIL"), ("build_shelters.py", "published=LIVE_COUNCIL"),
                          ("build.py", "published=phone_lock.live_council(published)"), ("publish_gate.py", "published=live_council"),
                          ("shelter_contacts.py", "published=live")):
            src = open(os.path.join(ROOT, "scripts", f), encoding="utf-8").read()
            self.assertIn(needle, src, f)

    def test_undo_is_logged(self):
        log = json.load(open(os.path.join(ROOT, "reports", "council_line_changes.json"), encoding="utf-8"))
        self.assertEqual({e["id"] for e in log}, set(UNDONE_16))
        self.assertTrue(all(e["reverted"] and e["field"] == "council_phone" and "477f83f73" in e["added_by"] for e in log))
        md = open(os.path.join(ROOT, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertIn("<!-- council line undo -->", md)
        for i in UNDONE_16:
            self.assertIn(i, md)
        self.assertIn("'council line undo'", open(os.path.join(ROOT, "scripts", "publish_gate.py"), encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
