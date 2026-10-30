"""Hermetic regression: Dean-approved hand-verified manual shelters must pass recheck + verification + publish gate."""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import common, publish_gate as pg, recheck as R

IDS = (
    "man-hastings-wuth-night-shelter",
    "man-mary-rose-court-basingstoke",
    "man-ymca-basingstoke",
    "man-ymca-watford-charter",
)


def _manual():
    return {x["id"]: x for x in json.load(open(os.path.join(ROOT, "overrides", "shelters_manual.json"), encoding="utf-8"))}


def _verified():
    return json.load(open(os.path.join(ROOT, "overrides", "shelters_verified.json"), encoding="utf-8"))


class RecheckEmptyHours(unittest.TestCase):
    def test_office_hours_in_quote_do_not_block_when_hours_blank(self):
        """YMCA Basingstoke: day_time_quote is office contact hours; published hours are blank."""
        man = _manual()["man-ymca-basingstoke"]
        ov = _verified()["man-ymca-basingstoke"]
        page = {"http": 200, "text": ("YMCA Basingstoke RG21 4QD homelessness " * 40), "final_url": ov["evidence_url"],
                "etag": "", "last_modified": "", "sha256": "x"}
        r = R.check(man, ov, page, ov["evidence_url"])
        self.assertTrue(r["ok"], r)


class VerificationGateGroups(unittest.TestCase):
    def test_infer_groups_for_blank_manual_rows(self):
        ver = _verified()
        pending = os.path.join(tempfile.mkdtemp(), "shelters_pending.json")
        for i in ("man-hastings-wuth-night-shelter", "man-mary-rose-court-basingstoke", "man-ymca-watford-charter"):
            pub, _, _ = common.verification_gate([dict(_manual()[i])], None, ver, "2026-10-30", pending, recheck=False)
            self.assertEqual(len(pub), 1, i)
            self.assertTrue(pub[0].get("groups"), i)


class PublishGateApproved(unittest.TestCase):
    def test_approved_verified_manual_shelters_not_held_for_groups(self):
        d = tempfile.mkdtemp()
        try:
            shutil.copytree(os.path.join(ROOT, "scripts"), os.path.join(d, "scripts"), ignore=shutil.ignore_patterns("__pycache__"))
            for sub in ("logs", "reports", "overrides"):
                os.makedirs(os.path.join(d, sub))
            shutil.copy(os.path.join(ROOT, "overrides", "auto_apply_rules.json"), os.path.join(d, "overrides"))
            shutil.copy(os.path.join(ROOT, "overrides", "approved_new_places.json"), os.path.join(d, "overrides"))
            ver = _verified()
            items = []
            for i in IDS:
                m = dict(_manual()[i])
                pub, _, _ = common.verification_gate([m], None, ver, "2026-10-30", os.path.join(d, "logs", "shelters_pending.json"), recheck=False)
                row = pub[0]
                row["tel"] = "01234567890"
                items.append(row)
            path = os.path.join(d, pg.FILES["shelters"])
            open(path, "w").write("var SHELTERS=" + json.dumps({"items": items}, separators=(",", ":")) + ";")
            git = lambda *a: subprocess.run(a, cwd=d, check=True, capture_output=True)
            git("git", "init", "-q")
            git("git", "add", "-A")
            git("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
            r = subprocess.run([sys.executable, os.path.join("scripts", "publish_gate.py"), "shelters"], cwd=d, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            left = [x["id"] for x in json.loads(open(path).read().split("=", 1)[1].strip().rstrip(";"))["items"]]
            pending = json.load(open(os.path.join(d, "logs", "pending_dean.json"))).get("shelters", [])
            self.assertEqual(set(left), set(IDS))
            self.assertEqual(pending, [])
        finally:
            shutil.rmtree(d, True)


if __name__ == "__main__":
    unittest.main()
