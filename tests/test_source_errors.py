import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import full_check as F
class T(unittest.TestCase):
    def test_errors(self):
        res = {"a": {"ok": True}, "b": {"ok": False, "http": 500, "error": "HTTP 500", "fail_runs": 2}, "c": {"ok": None, "error": "time budget reached - not checked this run"}}
        e = F.source_errors(["a", "b", "c"], res, {"b": [{"foodbank": "B FB"}]}, "t")
        self.assertEqual([x["website"] for x in e["errors"]], ["b", "c"]); self.assertEqual(e["errors"][0]["name"], "B FB"); self.assertEqual(e["checked"], 3)
