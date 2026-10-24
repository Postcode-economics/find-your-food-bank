import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import classify as C
class T(unittest.TestCase):
    def test_add_idempotent(self):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "overrides"))
        rec = {"name": "X", "address": "A", "postcode": "S1 1AA", "lat": 1, "lng": 2, "phone": "07000000000", "website": "w", "evidence_url": "w", "opening_times": {"structured": {"mon": [["10:00", "11:00"]]}}}
        json.dump({"_comment": "", "x": rec, "dup": rec}, open(os.path.join(d, "overrides", "foodbank_added.json"), "w"))
        items = [{"id": "dup", "type": "foodbank"}]
        self.assertEqual(C.add_added_foodbanks(items, d), 1); C.add_added_foodbanks(items, d)
        self.assertEqual(len(items), 2); x = [i for i in items if i["id"] == "x"][0]; self.assertEqual(x["tel"], "07000000000")
    def test_real_file(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        for k, v in json.load(open(os.path.join(root, "overrides", "foodbank_added.json"))).items():
            if k.startswith("_"): continue
            self.assertTrue(v["phone"] and v["opening_times"]["structured"] and v["postcode"] in v["address"] and "/" not in k, k)
