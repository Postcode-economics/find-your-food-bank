"""learning_state.json is merged per key by the run that writes it when several layers saved it (synthetic data)."""
import json, os, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import private_state_restore as R
import learning

REL = "reports/learning_state.json"


def key(kind, last, checks=1):
    return {"kind": kind, "checks": checks, "finds": 0, "fails": 0, "consec_fail": 0, "last_check": last,
            "last_find": None, "last_change": None, "methods": {}, "last_method": None}


def state(keys, total=0, history=None, **extra):
    s = {"version": 1, "keys": keys, "total_checks": total, "history": history or []}
    s.update(extra); return s


class LearningStatePerKey(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self.src = os.path.join(self.tmp, "src"); self.dst = os.path.join(self.tmp, "dst")
        os.makedirs(self.dst)

    def tearDown(self): shutil.rmtree(self.tmp, ignore_errors=True)

    def save(self, layer, content, at):
        p = os.path.join(self.src, layer, REL); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh: fh.write(content if isinstance(content, str) else json.dumps(content))
        with open(os.path.join(self.src, layer, ".saved_at"), "w") as fh: fh.write(str(at))

    def restored(self):
        R.restore(self.src, self.dst)
        return learning.load(os.path.join(self.dst, REL))

    def test_an_earlier_sweep_save_no_longer_wipes_the_brake_history(self):
        # The sweep copy was restored before the food bank run saved, and the sweep saved last.
        counts = [{"day": "2000-01-0%d" % i, "changes": i} for i in range(1, 6)]
        self.save("foodbanks", state({"https://fb.example/a": key("foodbank_site", "2000-01-05"),
                                      "https://council.example/p": key("sweep_page", "2000-01-01")}, 10,
                                     change_counts=counts, anomaly={"stop": False, "day": "2000-01-05"},
                                     signals_run="2000-01-05", tombstones=[{"key": "x", "last_day": "1999-01-01", "reason": "pruned"}]), 200)
        self.save("sweep", state({"https://council.example/p": key("sweep_page", "2000-01-06", 2)}, 8), 300)
        got = self.restored()
        self.assertEqual(got["change_counts"], counts)
        self.assertEqual(got["anomaly"]["day"], "2000-01-05")
        self.assertEqual(got["signals_run"], "2000-01-05")
        self.assertEqual(len(got["tombstones"]), 1)
        self.assertEqual(sorted(got["keys"]), ["https://council.example/p", "https://fb.example/a"])
        self.assertEqual(got["keys"]["https://council.example/p"]["last_check"], "2000-01-06")   # sweep owns its pages
        self.assertEqual(got["total_checks"], 10)
        self.assertGreaterEqual(len(got["change_counts"]), 4)                                     # brake has its runs

    def test_owner_copy_wins_even_when_a_carried_copy_is_newer_or_checked_later(self):
        self.save("foodbanks", state({"https://fb.example/a": key("foodbank_site", "2000-01-02", 5)}), 100)
        self.save("sweep", state({"https://fb.example/a": key("foodbank_site", "2000-01-09", 1)}), 900)
        self.assertEqual(self.restored()["keys"]["https://fb.example/a"]["checks"], 5)

    def test_a_key_the_owner_pruned_is_not_brought_back_by_a_carried_copy(self):
        self.save("sweep", state({"https://fb.example/gone": key("foodbank_site", "1999-01-01"),
                                  "https://council.example/p": key("sweep_page", "2000-01-01")}), 100)
        self.save("foodbanks", state({}, tombstones=[{"key": "https://fb.example/gone", "last_day": "1999-01-01", "reason": "pruned"}]), 200)
        got = self.restored()
        self.assertEqual(sorted(got["keys"]), ["https://council.example/p"])

    def test_unreadable_owner_copy_fails_closed(self):
        for bad in ("{not json", "[]", "null", '"x"', '{"keys": []}'):
            with self.subTest(copy=bad):
                shutil.rmtree(self.src, ignore_errors=True); shutil.rmtree(self.dst); os.makedirs(self.dst)
                self.save("sweep", state({"https://fb.example/a": key("foodbank_site", "2000-01-01"),
                                          "https://council.example/p": key("sweep_page", "2000-01-02")},
                                         change_counts=[{"day": "2000-01-01", "changes": 1}]), 100)
                self.save("foodbanks", bad, 200)
                got = self.restored()
                self.assertEqual(sorted(got["keys"]), ["https://council.example/p"])   # no carried food bank keys
                self.assertNotIn("change_counts", got)                                # no carried owner fields

    def test_no_owner_save_takes_the_newest_check_then_the_later_save(self):
        self.save("shelters", state({"https://fb.example/a": key("foodbank_site", "2000-01-03", 3),
                                     "https://x.example/t": key("other", "2000-01-01", 1)}), 100)
        self.save("warmspaces", state({"https://fb.example/a": key("foodbank_site", "2000-01-02", 2),
                                       "https://x.example/t": key("other", "2000-01-01", 9)},
                                      change_counts=[{"day": "2000-01-02", "changes": 0}]), 200)
        got = self.restored()
        self.assertEqual(got["keys"]["https://fb.example/a"]["checks"], 3)   # newer last_check
        self.assertEqual(got["keys"]["https://x.example/t"]["checks"], 9)    # tie: later save
        self.assertEqual(got["change_counts"], [{"day": "2000-01-02", "changes": 0}])

    def test_heal_before_record_source_keys_belong_to_foodbanks(self):
        self.save("foodbanks", state({"https://fb.example/h": key("source", "2000-01-01", 4)}), 100)
        self.save("sweep", state({"https://fb.example/h": key("source", "2000-01-05", 1)}), 200)
        self.assertEqual(self.restored()["keys"]["https://fb.example/h"]["checks"], 4)

    def test_history_is_the_union_of_runs_by_day_last_14(self):
        h = lambda d, r: {"day": d, "reward": {"k": r}}
        self.save("foodbanks", state({}, history=[h("2000-01-%02d" % i, 1) for i in range(1, 11)]), 100)
        self.save("sweep", state({}, history=[h("2000-01-05", 1), h("2000-01-05", 2)] + [h("2000-01-%02d" % i, 3) for i in range(11, 15)]), 200)
        got = self.restored()["history"]
        self.assertEqual(len(got), 14)
        self.assertEqual([x["day"] for x in got], sorted(x["day"] for x in got))
        self.assertEqual(got[-1], h("2000-01-14", 3))
        self.assertEqual(sum(1 for x in got if x == h("2000-01-05", 1)), 1)       # exact duplicate once

    def test_one_copy_and_all_unreadable_are_copied_as_before(self):
        self.save("sweep", "{not json", 100)
        self.save("foodbanks", "[]", 200)
        R.restore(self.src, self.dst)
        with open(os.path.join(self.dst, REL)) as fh: self.assertEqual(fh.read(), "[]")
        shutil.rmtree(self.src); shutil.rmtree(self.dst); os.makedirs(self.dst)
        self.save("sweep", state({"https://council.example/p": key("sweep_page", "2000-01-01")}), 100)
        R.restore(self.src, self.dst)
        with open(os.path.join(self.src, "sweep", REL)) as a, open(os.path.join(self.dst, REL)) as b: self.assertEqual(a.read(), b.read())

    def test_checkout_copy_always_wins(self):
        self.save("foodbanks", state({"https://fb.example/a": key("foodbank_site", "2000-01-01")}), 100)
        self.save("sweep", state({}), 200)
        os.makedirs(os.path.join(self.dst, "reports"))
        with open(os.path.join(self.dst, REL), "w") as fh: fh.write("{}")
        R.restore(self.src, self.dst)
        with open(os.path.join(self.dst, REL)) as fh: self.assertEqual(fh.read(), "{}")

    def test_written_like_learning_save(self):
        self.save("foodbanks", state({"https://fb.example/a": key("foodbank_site", "2000-01-01")}), 100)
        self.save("sweep", state({}), 200)
        R.restore(self.src, self.dst)
        with open(os.path.join(self.dst, REL)) as fh: raw = fh.read()
        self.assertEqual(raw, json.dumps(json.loads(raw), indent=0, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
