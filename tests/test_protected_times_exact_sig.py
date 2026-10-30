"""Dean 30 Oct 2026: protected hand-checked times block only the same structured table, not every auto-apply."""
import hashlib, json, os, shutil, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import discover as D, times_finder as TF

R1, R2 = "2026-10-30T03:00:00+00:00", "2026-10-30T11:00:00+00:00"
ON = {"times_auto_apply": True}
KS = {"pages": {}, "skip": {}}


def pg(html, url="https://example.org/"):
    return {"http": 200, "final_url": url, "html": html, "etag": "e", "last_modified": "",
            "sha256": hashlib.sha256(html.encode()).hexdigest()}


class ProtectedExactSig(unittest.TestCase):
    def test_same_structured_table_still_blocked(self):
        stored = {"protected": True, "status": "TIMES_FOUND", "structured": {"wed": [["10:00", "12:00"]]},
                  "raw": "Wed 10-12", "reader": "hand-reviewed 2026-10-29"}
        new = {"status": "TIMES_FOUND", "structured": {"wed": [["10:00", "12:00"]]}, "raw": "Wed 10-12"}
        item = {"id": "x", "postcode": "AB1 2CD", "website": "https://example.org/", "opening_times": stored}
        why = D.hand_checked_hold_reason(item, "opening_times", new, {item["id"]: stored})
        self.assertIn("refresh only flags differences", why)

    def test_different_structured_table_not_blocked_by_protection(self):
        stored = {"protected": True, "status": "TIMES_TEXT_ONLY", "structured": None,
                  "raw": "Tuesdays 2pm", "reader": "hand-reviewed 2026-10-30"}
        new = {"status": "TIMES_FOUND", "structured": {"wed": [["13:00", "13:00"]]}, "raw": "Wednesday 1pm"}
        item = {"id": "x", "opening_times": stored}
        self.assertIsNone(D.hand_checked_hold_reason(item, "opening_times", new, {item["id"]: stored}))

    def test_warm_space_hours_protected_same_rule(self):
        stored_h = {"mon": [["09:00", "11:00"]]}
        item = {"id": "ws1", "hours": {"structured": stored_h}, "hours_protected": True, "postcode": "AB1 2CD",
                "website": "https://example.org/"}
        same = {"status": "TIMES_FOUND", "structured": dict(stored_h), "raw": "Mon 9-11"}
        diff = {"status": "TIMES_FOUND", "structured": {"wed": [["13:00", "14:00"]]}, "raw": "Wed 1-2"}
        self.assertIn("refresh only flags differences", D.hand_checked_hold_reason(item, "hours", same))
        self.assertIsNone(D.hand_checked_hold_reason(item, "hours", diff))

    def test_single_run_not_applied(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        for d in ("logs", "reports", "overrides"):
            os.makedirs(os.path.join(root, d))
        stored = {"protected": True, "status": "TIMES_TEXT_ONLY", "structured": None, "raw": "Tue 2pm",
                  "reader": "hand-reviewed", "source_url": "https://x.org/"}
        json.dump({"fb1": stored}, open(os.path.join(root, "overrides", "opening_times.json"), "w"))
        html = "<html><body>AB12CD Holy Trinity food bank. Wednesday 1pm - 2pm</body></html>"
        item = {"id": "fb1", "name": "T", "postcode": "AB1 2CD", "website": "https://x.org/", "opening_times": dict(stored)}
        f = lambda u: pg(html, "https://x.org/") if "x.org" in u else {"http": 404, "final_url": u, "html": ""}
        log = D.cross_check_times([item], "fb", "opening_times", f, state_root=root, rules=ON, run_at=R1)
        self.assertEqual(log["fb1"]["status"], "held_for_dean")
        self.assertFalse(os.path.exists(os.path.join(root, "reports", "times_auto_applied.json")))

    def test_shrink_sessions_still_held(self):
        old = {"protected": True, "status": "TIMES_FOUND", "structured": {"mon": [["09:00", "11:00"]], "wed": [["09:00", "11:00"]]},
               "raw": "Mon and Wed", "reader": "hand-reviewed"}
        new = {"status": "TIMES_FOUND", "structured": {"wed": [["09:00", "11:00"]]}, "raw": "Wed only"}
        item = {"id": "x", "postcode": "AB1 2CD", "website": "https://x.org/", "opening_times": old}
        seen = {"fb:x": {"sig": json.dumps(new["structured"], sort_keys=True), "source_url": "https://x.org/", "run_at": R1}}
        why = D.times_gate_reasons(item, "fb", "opening_times", new, ["AB12CD Wed only"], {"final_url": "https://x.org/"},
                                   seen, {}, True, R2, overrides={item["id"]: old})
        self.assertTrue(any("fewer days" in w or "fewer sessions" in w for w in why), why)
        self.assertFalse(any("refresh only flags differences" in w for w in why), why)


if __name__ == "__main__":
    unittest.main()
