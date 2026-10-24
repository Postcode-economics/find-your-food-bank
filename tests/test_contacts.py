import unittest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import shelter_contacts as sc

class T(unittest.TestCase):
    def test_fill_fix_drop_and_fallback(self):
        data = {"_councils": {"c": {"council": "X Council", "council_phone": "01234 567890"}},
                "a": {"phone": "0161 236 7537"}, "b": {"phone_fix": "01274 481039"}, "d": {"drop_phone": True, "area": "c"}}
        it = [{"id": "a", "phone": ""}, {"id": "b", "phone": "01274 435999", "tel": "01274435999"}, {"id": "d", "phone": "0300 123 1966", "tel": "03001231966"}]
        sc.apply(it, data)
        self.assertEqual(it[0]["tel"], "01612367537"); self.assertEqual(it[1]["tel"], "01274481039")
        self.assertEqual(it[2]["tel"], ""); self.assertEqual(it[2]["council_phone"], "01234 567890")
        self.assertEqual(sc.check(it), [])
    def test_overrides_cover_all_live(self):  # refresh can't leave an entry without a number or labelled fallback
        for lay, path in (("shelters", sc.PATH), ("warmspaces", sc.WS)):
            import json
            t = open(os.path.join(os.path.dirname(__file__), "..", lay + ".js")).read(); d = json.loads(t[t.index("{"):t.rindex("}") + 1])
            sc.apply(d["items"], sc.load(path)); self.assertEqual(sc.check(d["items"]), [], lay)

class Fenland(unittest.TestCase):
    def test_fenland_switchboard_only_as_named_ooh_line(self):  # Dean 24 Oct: switchboard only when council page names it the OOH homeless line
        import json
        t = open(os.path.join(os.path.dirname(__file__), "..", "warmspaces.js")).read(); d = json.loads(t[t.index("{"):t.rindex("}") + 1])
        sc.apply(d["items"], sc.load(sc.WS))
        hits = [x for x in d["items"] if x.get("council_phone") == "01354 654321"]
        self.assertTrue(hits)
        for x in hits:
            self.assertEqual(x.get("council_ooh"), "01354 654321", x["id"])
            self.assertIn(x.get("council_label"), ("Council out-of-hours homeless line", "Fenland Council out-of-hours homeless line"), x["id"])
            self.assertIn("I-Need-Accommodation-Now", x.get("council_url", ""), x["id"])
