"""Anomaly brake: exact bars at other medians, history parsing, the drill's spike matches the brake,
and full_check.main() really stops: nothing published, the spike is not added to change_counts."""
import json, os, sys, tempfile, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, brake_drill


def hist(*counts): return [{"day": "2026-10-%02d" % (n + 1), "changes": c} for n, c in enumerate(counts)]


class Bars(unittest.TestCase):
    def edge(self, history, first_stop):
        self.assertFalse(learning.anomaly_brake(history, first_stop - 1)["stop"], first_stop - 1)
        self.assertTrue(learning.anomaly_brake(history, first_stop)["stop"], first_stop)

    def test_floor_of_ten_binds_when_runs_are_quiet(self):
        self.edge(hist(0, 0, 0, 0), 10)

    def test_plus_eight_binds_at_median_five(self):
        self.edge(hist(5, 5, 5, 5), 15)   # max(10, 15, 13)

    def test_three_times_binds_at_median_ten(self):
        self.edge(hist(10, 10, 10, 10), 30)

    def test_even_history_uses_the_upper_median(self):
        f = learning.anomaly_brake(hist(1, 1, 9, 9), 0)
        self.assertEqual(f["median"], 9)

    def test_bare_ints_count_and_junk_rows_are_ignored(self):
        mixed = [2, {"changes": 2}, {"changes": "40"}, {"changes": None}, "x", None, {"day": "d"}, 2, {"changes": 2}]
        f = learning.anomaly_brake(mixed, 10)
        self.assertEqual(f["median"], 2); self.assertTrue(f["stop"])
        three_valid = [2, {"changes": 2}, {"changes": "9"}, 2]
        self.assertFalse(learning.anomaly_brake(three_valid, 99)["stop"])
        self.assertIn("3 past runs", learning.anomaly_brake(three_valid, 99)["reason"])

    def test_held_kinds_never_count(self):
        for e in ({"kind": "closure", "old": "on map", "new": "note"}, {"kind": "New Place", "old": "a", "new": "b"},
                  {"kind": "new food bank"}, {"id": "x"}, "phone", None):
            self.assertFalse(learning.is_applied_change(e), e)
        for e in ({"kind": "Phone"}, {"kind": " access "}, {"kind": "removed"}, {"old": "voucher", "new": "walkin"}):
            self.assertTrue(learning.is_applied_change(e), e)


class DrillMatchesBrake(unittest.TestCase):
    def test_spike_is_exactly_the_first_stopped_count(self):
        for m in range(0, 41):
            h = hist(m, m, m, m, m)
            s = brake_drill.spike_for(h)
            self.assertTrue(learning.anomaly_brake(h, s)["stop"], m)
            self.assertFalse(learning.anomaly_brake(h, s - 1)["stop"], m)


class MainStops(unittest.TestCase):
    """12 clear phone fixes against a median of 2: the brake stops main() before anything is published."""
    def test_spike_publishes_nothing_and_is_not_added_to_history(self):
        import full_check as F, learning_signals
        sites = ["https://s%02d.example/home" % n for n in range(12)]
        items = [dict(id="brake-%02d" % n, type="foodbank", name="B%d" % n, foodbank="B%d" % n, website=u,
                      phone="01000000000", tel="01000000000") for n, u in enumerate(sites)]
        phone = ["02000000000"]
        store = {"full_check_state.json": {"sites": {u: {"phones": phone, "tel": phone, "final_url": u + "/contact",
                                                           "checked_at": "2026-10-27T03:00:00+00:00", "access": "unclear"} for u in sites},
                                           "ids": [i["id"] for i in items]}}
        counts = hist(2, 2, 2, 2)
        LS = learning.load(path=os.path.join(tempfile.mkdtemp(), "none.json")); LS["change_counts"] = list(counts)
        written, saved = {}, []
        rep = tempfile.mkdtemp(); tmp = tempfile.mkdtemp()
        def fake(u):
            return dict(url=u, ok=True, final_url=u + "/contact", pages=[u + "/contact"], access="unclear", hours_hash="", hours_sample=[],
                        seasonal=None, closed=None, perm_closed=None, phones=phone, tel=phone, needs=None,
                        checked_at="2026-10-27T11:00:00+00:00", http=200)
        orig = (F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site, F.DATA, F.ACC, learning.load, learning.save)
        F.rj = lambda n, d: store.get(n, d); F.wj = lambda n, o: written.__setitem__(n, o)
        F.load_data = lambda: ("x=", {"items": items}); F.load_access = lambda: {}
        F.write_md = lambda *a: None; F.REP = rep; F.check_site = fake
        F.DATA = os.path.join(tmp, "data.full.js"); F.ACC = os.path.join(tmp, "access.js")
        learning.load = lambda *a, **k: LS
        learning.save = lambda s, *a, **k: saved.append(json.loads(json.dumps(s)))
        os.environ.pop("DRY_RUN", None); os.environ.pop("SAMPLE", None)
        try: F.main()
        finally:
            (F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site, F.DATA, F.ACC, learning.load, learning.save) = orig
        md = open(os.path.join(rep, "anomaly_brake.md"), encoding="utf-8").read()
        self.assertIn("would change 12 places", md); self.assertIn("Nothing from this run was published", md)
        for f in ("phone_fixes.json", "access_changes.json", "access_tags.json", "full_check_state.json", "provenance.json"):
            self.assertNotIn(f, written)
        self.assertFalse(os.path.exists(os.path.join(rep, "phone_auto_applied.json")))
        self.assertEqual({i["phone"] for i in items}, {"01000000000"})
        self.assertEqual(os.listdir(tmp), [])
        self.assertEqual(saved[-1]["change_counts"], counts)   # the spike is not a new baseline
        self.assertTrue(saved[-1]["anomaly"]["stop"]); self.assertEqual(saved[-1]["anomaly"]["proposed"], 12)


if __name__ == "__main__": unittest.main()
