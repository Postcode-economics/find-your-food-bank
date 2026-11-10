"""Restoring the intelligent mode summary (reports/intelligent_mode.json) from the private run state: each layer's run
writes only its own slot, so a later save by another layer must not hide that layer's applies from the blast caps
(intelligent_rails.applied_today / blast_reason). Synthetic layers, ids and counts only; temp folders only."""
import datetime, json, os, shutil, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import private_state_restore as M
import intelligent_rails as IR

REL = "reports/intelligent_mode.json"


def slot(applied, alerts=()):
    return {"steps": {"times": {"applied": applied, "applied_this_run": applied, "held": 0, "stale_cleared": 0, "rejected": [],
                                "errors": [], "alerts": list(alerts), "coverage": {}, "enabled": True}},
            "applied": applied, "applied_this_run": applied, "held": 0, "stale_cleared": 0, "rejected": [], "errors": [],
            "alerts": list(alerts), "coverage": {}}


def summary(day, layers, blocks=(), enabled=True, at="2026-01-05T05:00:00+00:00"):
    return {"run": day, "enabled": enabled, "generated_at": at, "layers": layers, "alerts": [], "would_block": list(blocks)}


class RestoreIntelligentSummary(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d, True)
        self.src = os.path.join(self.d, "site-run-state"); self.n = 0
        self.today = datetime.date.today().isoformat()
        IR.reset(); self.addCleanup(IR.reset)

    def save(self, layer, data, at):
        p = os.path.join(self.src, layer, REL); os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(data if isinstance(data, str) else json.dumps(data))
        open(os.path.join(self.src, layer, ".saved_at"), "w").write(str(at))

    def restored(self, dst=None):
        self.n += 1
        dst = dst or os.path.join(self.d, "run-%d" % self.n); os.makedirs(dst, exist_ok=True)
        M.restore(self.src, dst); self.dst = dst
        p = os.path.join(dst, REL)
        return open(p).read() if os.path.exists(p) else None

    def test_every_layers_slot_comes_back_and_counts_towards_the_caps(self):
        t = self.today
        # parallel runs: each saved only its own slot; the food bank run saved last
        self.save("shelters", summary(t, {"shelters": slot(30)}), 100)
        self.save("warmspaces", summary(t, {"warmspaces": slot(5)}), 200)
        self.save("foodbanks", summary(t, {"foodbanks": slot(2)}), 300)
        got = json.loads(self.restored())
        self.assertEqual(sorted(got["layers"]), ["foodbanks", "shelters", "warmspaces"])
        self.assertEqual(IR.applied_today(self.dst), 37)
        self.assertEqual(IR.applied_today(self.dst, "shelters"), 30)
        self.assertIn("blast limit", IR.blast_reason(11, "shelters", self.dst))     # 41 this layer: held, as designed
        self.assertIn("blast limit", IR.blast_reason(4, "foodbanks", self.dst))     # 41 across layers: held
        self.assertEqual(IR.blast_reason(3, "foodbanks", self.dst), "")

    def test_the_layers_own_save_wins_over_a_carried_copy(self):
        t = self.today
        self.save("shelters", summary(t, {"shelters": slot(9)}), 100)
        self.save("foodbanks", summary(t, {"shelters": slot(1), "foodbanks": slot(2)}), 200)   # carried, older count
        got = json.loads(self.restored())
        self.assertEqual(got["layers"]["shelters"]["applied"], 9)
        self.assertEqual(got["layers"]["foodbanks"]["applied"], 2)

    def test_without_the_layers_own_save_that_day_the_newest_carried_copy_counts(self):
        t = self.today
        self.save("sweep", summary(t, {"warmspaces": slot(3), "sweep": slot(0)}), 100)
        self.save("foodbanks", summary(t, {"warmspaces": slot(4), "foodbanks": slot(1)}), 200)
        self.save("warmspaces", summary("2000-01-01", {"warmspaces": slot(40)}), 300)        # its own save is from another day
        got = json.loads(self.restored())
        self.assertEqual(got["run"], t)
        self.assertEqual({k: v["applied"] for k, v in got["layers"].items()}, {"foodbanks": 1, "sweep": 0, "warmspaces": 4})

    def test_older_days_never_count(self):
        self.save("shelters", summary("2000-01-01", {"shelters": slot(30)}), 300)
        self.save("foodbanks", summary("2000-01-02", {"foodbanks": slot(2)}), 100)
        got = json.loads(self.restored())
        self.assertEqual((got["run"], sorted(got["layers"])), ("2000-01-02", ["foodbanks"]))

    def test_day_wide_fields_are_merged(self):
        t = self.today
        self.save("shelters", summary(t, {"shelters": slot(1, ["A"])}, blocks=["coverage gate: x"], enabled=False,
                                      at="2026-01-05T06:00:00+00:00"), 100)
        self.save("foodbanks", summary(t, {"foodbanks": slot(1, ["B"])}, blocks=["coverage gate: y", "coverage gate: x"],
                                       enabled=True, at="2026-01-05T05:00:00+00:00"), 200)
        got = json.loads(self.restored())
        self.assertEqual(got["would_block"], ["coverage gate: x", "coverage gate: y"])
        self.assertEqual(got["alerts"], ["A", "B"])
        self.assertTrue(got["enabled"])
        self.assertEqual(got["generated_at"], "2026-01-05T06:00:00+00:00")

    def test_written_like_intelligent_rails_writes_it(self):
        t = self.today
        self.save("shelters", summary(t, {"shelters": slot(1)}), 100)
        self.save("foodbanks", summary(t, {"foodbanks": slot(1)}), 200)
        raw = self.restored()
        self.assertEqual(raw, json.dumps(json.loads(raw), indent=1, ensure_ascii=False))

    def test_a_single_save_is_restored_as_is(self):
        self.save("shelters", '{"run": "x",  "odd spacing": 1}', 100)
        self.assertEqual(self.restored(), '{"run": "x",  "odd spacing": 1}')

    def test_unusable_copies_fall_back_to_the_newest_save_as_is(self):
        self.save("shelters", "{not json", 100)
        self.save("foodbanks", "[]", 200)
        self.assertEqual(self.restored(), "[]")

    def test_an_unusable_copy_never_hides_the_others(self):
        t = self.today
        self.save("shelters", summary(t, {"shelters": slot(6)}), 100)
        self.save("foodbanks", "{not json", 200)
        self.assertEqual(json.loads(self.restored())["layers"]["shelters"]["applied"], 6)

    def test_checkout_copy_still_wins(self):
        t = self.today
        self.save("shelters", summary(t, {"shelters": slot(6)}), 100)
        self.save("foodbanks", summary(t, {"foodbanks": slot(1)}), 200)
        dst = os.path.join(self.d, "co"); os.makedirs(os.path.join(dst, "reports"))
        open(os.path.join(dst, REL), "w").write("{}")
        self.assertEqual(self.restored(dst), "{}")

    def test_other_shared_files_still_newest_save(self):
        for layer, at, body in (("shelters", 100, "old"), ("foodbanks", 200, "new")):
            p = os.path.join(self.src, layer, "reports", "other.json"); os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").write(body); open(os.path.join(self.src, layer, ".saved_at"), "w").write(str(at))
        self.restored()
        self.assertEqual(open(os.path.join(self.dst, "reports", "other.json")).read(), "new")


if __name__ == "__main__":
    unittest.main()
