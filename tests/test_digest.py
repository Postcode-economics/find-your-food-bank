import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import digest as D
class T(unittest.TestCase):
    def test_closure(self):
        h = {"a": [{"id": "a", "name": "A FB", "change": "removed", "label": "real closure (own site says closed)", "when": "2026-10-24T05:00:00+00:00"}],
             "b": [{"id": "b", "change": "removed", "label": "removed from feed (not confirmed closed)", "when": "2026-10-24T05:00:00+00:00"}]}
        al, _, c = D.triggers({}, h, [], "2026-10-23T05:00:00+00:00"); self.assertEqual([a[0] for a in al], ["closure"]); self.assertEqual(len(c), 1)
        al, _, _ = D.triggers({}, h, [], "2026-10-25T00:00:00+00:00"); self.assertEqual(al, [])
    def test_dup_spike(self):
        d = [{"kind": "likely duplicate"}] * 31
        self.assertEqual([a[0] for a in D.triggers({"dups": [24, 24, 25]}, {}, d, "x")[0]], ["dup-spike"])
        self.assertEqual(D.triggers({"dups": [24, 24, 25]}, {}, d[:28], "x")[0], [])
        self.assertEqual(D.triggers({}, {}, d, "x")[0], [])
