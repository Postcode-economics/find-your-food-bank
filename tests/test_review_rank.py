"""Plan 1.6 (9 Nov 2026): short ranked review list. Reporting only; the full list and the auto-applied list stay."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import review_rank as R


def it(cat, name, **k): return dict({"category": cat, "name": name, "website": "https://x/" + name, "first_flagged": "2026-11-08T06:00"}, **k)


class Short(unittest.TestCase):
    def test_unchanged_items_counted_not_listed(self):
        a = {"u|a": it("opening times unclear", "A")}
        b = {"u|a": it("opening times unclear", "A", first_flagged="2026-11-09T06:00")}
        s = R.short_list(b, a)
        self.assertEqual(s["rows"], []); self.assertEqual(s["unchanged"], {"opening times unclear": 1})

    def test_run_counters_alone_are_not_a_change(self):
        a = {"d|a": it("dead or unreachable website", "A", failed_runs=40, note="site failed 40 runs")}
        b = {"d|a": it("dead or unreachable website", "A", failed_runs=42, note="site failed 42 runs")}
        self.assertEqual(R.short_list(b, a)["rows"], [])

    def test_real_change_and_new_listed_and_ranked(self):
        a = {"d|a": it("dead or unreachable website", "A", error="HTTP 403")}
        b = {"d|a": it("dead or unreachable website", "A", error="HTTP 404"),
             "r|b": it("not fetched, robots", "B"), "p|c": it("phone fix held (confidence under the rules)", "C")}
        s = R.short_list(b, a)
        self.assertEqual([r["name"] for r in s["rows"]], ["C", "A", "B"])
        self.assertEqual((s["new"], s["changed"]), (2, 1))
        self.assertEqual(s["rows"][1]["status"], "changed")
        self.assertTrue(all(r["action"] for r in s["rows"]))

    def test_no_saved_day_lists_everything_capped_and_says_so(self):
        b = {"k%d" % i: it("opening times unclear", "N%03d" % i) for i in range(80)}
        s = R.short_list(b, None)
        self.assertFalse(s["has_prev"]); self.assertEqual(len(s["rows"]), R.CAP); self.assertEqual(s["more"], 30)
        text = "\n".join(R.md_lines(s, 0))
        self.assertIn("No earlier day saved", text); self.assertIn("30 more in the full list below", text)

    def test_unknown_category_not_buried(self):
        s = R.short_list({"x": it("brand new problem", "Z"), "y": it("not fetched, robots", "A")}, {})
        self.assertEqual(s["rows"][0]["name"], "Z")

    def test_auto_applied_count_always_stated(self):
        self.assertIn("Auto-applied this run: 4, every one listed", "\n".join(R.md_lines(R.short_list({}, {}), 4)))

    def test_previous_day(self):
        self.assertEqual(R.previous_day({"2026-11-07": {}, "2026-11-08": {}, "2026-11-09": {}}, "2026-11-09"), "2026-11-08")
        self.assertIsNone(R.previous_day({"2026-11-09": {}}, "2026-11-09"))
        self.assertIsNone(R.previous_day({}, "2026-11-09"))


class WriteMd(unittest.TestCase):
    def test_full_list_and_auto_applied_kept(self):
        import inspect, full_check
        src = inspect.getsource(full_check.write_md)
        self.assertIn("## Auto-applied this run", src); self.assertIn("## For Dean to review", src)


if __name__ == "__main__":
    unittest.main()
