"""Shadow harness: proposed rules log would-apply decisions without writing overlays."""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import shadow_apply as S


class Shadow(unittest.TestCase):
    def test_logs_would_apply_and_hold(self):
        def decide(c):
            if c["id"] == "ok":
                return "apply", "two identical reads", {"hours": "10:00 - 12:00"}
            return "hold", "would shrink sessions", {}

        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "overrides"))
            open(os.path.join(td, "overrides", "opening_times.json"), "w").write("{}\n")
            before = ["overrides/opening_times.json"]
            report = S.shadow_run(
                "phase2-example",
                [{"id": "ok", "name": "A"}, {"id": "no", "name": "B"}],
                decide,
                root=td,
                write=True,
            )
            self.assertEqual(report["summary"]["would_apply"], 1)
            self.assertEqual(report["summary"]["would_hold"], 1)
            self.assertEqual(report["mode"], "shadow")
            self.assertTrue(os.path.exists(report["path"]))
            # overlays untouched
            self.assertEqual(open(os.path.join(td, "overrides", "opening_times.json")).read(), "{}\n")
            self.assertTrue(S.assert_no_overlay_writes(before, td))

    def test_decide_error_is_fail_closed(self):
        def decide(c):
            raise RuntimeError("boom")

        report = S.shadow_run("x", [{"id": "z"}], decide, write=False)
        self.assertEqual(report["summary"]["errors"], 1)
        self.assertEqual(report["summary"]["would_apply"], 0)


if __name__ == "__main__":
    unittest.main()
