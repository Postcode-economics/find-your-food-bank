import sys, os, json, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import entry_history as E
def w(p, items): open(p, "w").write("var D=" + json.dumps({"items": items}) + ";")
class T(unittest.TestCase):
    def test_labels(self):
        d = tempfile.mkdtemp(); P = lambda n: os.path.join(d, n)
        json.dump({"a": {"url": "u"}}, open(P("c.json"), "w"))
        w(P("d.js"), [{"id": "a", "name": "A"}, {"id": "b", "name": "B", "phone": "1"}, {"id": "c", "name": "C"}])
        self.assertEqual(E.update(P("d.js"), P("s.json"), P("h.json"), P("c.json")), [])
        w(P("d.js"), [{"id": "b", "name": "B", "phone": "2"}, {"id": "n", "name": "N"}])
        ch = {(c["id"], c["change"]): c["label"] for c in E.update(P("d.js"), P("s.json"), P("h.json"), P("c.json"))}
        self.assertEqual(ch[("a", "removed")], "real closure (own site says closed)")
        self.assertEqual(ch[("c", "removed")], "removed from feed (not confirmed closed)")
        self.assertEqual(ch[("n", "added")], "new on map"); self.assertEqual(ch[("b", "phone")], "website/feed update")
        self.assertEqual(json.load(open(P("h.json")))["b"][0]["new"], "2")
