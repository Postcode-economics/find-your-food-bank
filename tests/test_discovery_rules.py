"""Dean's auto-add rule (23 Oct 2026): add when valid in-area postcode, not a duplicate (name+postcode or 150 m),
working source page and current/future dates; otherwise queue for manual review. Held places are never auto-added."""
import os, sys, json, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discovery_rules as DR, discover as D
OK = {"result": "add", "reasons": []}
G = {"LE15DB": (52.634234, -1.135836)}
T = "2026-10-23"
def c(**k): return dict({"id": "x1", "name": "Test Warm Hub", "postcode": "LE1 5DB", "address": "6 St Martins, Leicester, LE1 5DB", "source_live": True}, **k)
class Assess(unittest.TestCase):
    def test_all_checks_pass_adds(self): self.assertEqual(DR.assess(c(), OK, G, T, H=[])[0], "add")
    def test_unknown_postcode_queued(self):
        d, why = DR.assess(c(postcode="NW10 4LL"), OK, G, T, H=[]); self.assertEqual(d, "queue"); self.assertIn("not recognised", why[0])
    def test_pin_outside_area_queued(self):
        d, why = DR.assess(c(src_lat=51.5, src_lng=-0.1), OK, G, T, H=[]); self.assertEqual(d, "queue"); self.assertIn("km from its postcode", why[0])
    def test_address_with_other_postcode_queued(self):
        self.assertEqual(DR.assess(c(address="High St, NW10 4LL"), OK, G, T, H=[])[0], "queue")
    def test_past_dates_rejected(self):
        self.assertEqual(DR.assess(c(notes="SPACE OPENING ON 5th November 2025 until 31 March 2026"), OK, G, T, H=[])[0], "reject")
    def test_future_popup_added_with_opens(self):
        x = c(notes="**SPACE OPENING ON 7th December 2026**"); self.assertEqual(DR.assess(x, OK, G, T, H=[])[0], "add")
        DR.apply_dates(x, T); self.assertTrue(x["upcoming"]); self.assertEqual(x["scheme_start"], "2026-12-07")
    def test_unreachable_source_queued(self):
        self.assertEqual(DR.assess(c(), {"result": "flag", "reasons": ["own site unreachable (HTTP 503)"]}, G, T, H=[])[0], "queue")
    def test_no_own_site_but_live_directory_record_adds(self):
        self.assertEqual(DR.assess(c(), {"result": "flag", "reasons": ["no own website in directory"]}, G, T, H=[])[0], "add")
        self.assertEqual(DR.assess(c(source_live=False), {"result": "flag", "reasons": ["no own website in directory"]}, G, T, H=[])[0], "queue")
    def test_closed_rejected(self):
        self.assertEqual(DR.assess(c(), {"result": "flag", "reasons": ["own site says closed: permanently closed"]}, G, T, H=[])[0], "reject")
    def test_held_never_added(self):
        d, why = DR.assess(c(), OK, G, T, H=[{"postcode": "LE1 5DB", "reason": "awaiting Dean"}]); self.assertEqual(d, "queue")
    def test_hold_by_postcode_not_common_name(self):
        self.assertIsNone(DR.held(c(name="The Hub"), [{"name": "The Hub", "postcode": "TQ10 9BP"}]))
    def test_rule_error_is_queue_not_add(self):
        self.assertEqual(DR.assess(c(), None, None, T, H=[])[0], "queue")
class Dup(unittest.TestCase):
    def test_within_150m_is_duplicate(self):
        e = [{"name": "Other Place", "postcode": "LE1 1AA", "lat": 52.6340, "lng": -1.1358}]
        self.assertTrue(D.is_dup({"name": "New Hub", "postcode": "LE1 5DB", "lat": 52.6350, "lng": -1.1358}, e))   # ~110 m
        self.assertFalse(D.is_dup({"name": "New Hub", "postcode": "LE1 5DB", "lat": 52.6370, "lng": -1.1358}, e))  # ~330 m
class Record(unittest.TestCase):
    def test_new_today_and_queue_written(self):
        r = tempfile.mkdtemp(); os.makedirs(os.path.join(r, "reports"))
        open(os.path.join(r, "reports", "manual_review.md"), "w").write("# Manual review queue\n\nhand-made section\n")
        DR.record("warmspaces", T, [{"id": "a", "name": "New Hub", "postcode": "LE1 5DB", "upcoming": True, "scheme_start": "2026-12-07"}],
                  [{"id": "b", "name": "Queued Place", "reasons": ["postcode not recognised"]}], [], root=r)
        DR.record("warmspaces", T, [], [{"id": "b", "name": "Queued Place", "reasons": ["postcode not recognised"]}], [], root=r)
        nt = open(os.path.join(r, "reports", "new_today.md")).read(); mr = open(os.path.join(r, "reports", "manual_review.md")).read()
        self.assertIn("New Hub", nt); self.assertIn("Opens 2026-12-07", nt)
        self.assertIn("hand-made section", mr); self.assertIn("Queued Place", mr); self.assertEqual(mr.count(DR.START), 1)
        self.assertEqual(len(json.load(open(os.path.join(r, "logs", "discovery_today_warmspaces.json")))["runs"]), 2)
if __name__ == "__main__": unittest.main()
