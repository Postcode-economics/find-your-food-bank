"""The morning 'What the system learned' sections are plain sentences. The facts are unchanged."""
import os, sys, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS
from test_learning_guards import assert_schedule_and_guards

class PlainEnglish(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        dg = open(os.path.join(R, "scripts", "digest.py"), encoding="utf-8").read()
        self.assertIn("learning.digest_lines", dg)
        self.assertIn("learning_signals.digest_lines", dg)
    def test_check_history_is_a_sentence(self):
        s = learning.load(os.devnull)
        self.assertIn("Nothing has been learned yet", "\n".join(learning.digest_lines(s, "2026-10-26")))
        learning.record(s, "a", "2026-10-25", True, finds=1); learning.snapshot(s, "2026-10-25")
        learning.record(s, "a", "2026-10-26", True, finds=1)
        learning.record(s, "b", "2026-10-26", False); learning.record(s, "b", "2026-10-26", False)
        learning.snapshot(s, "2026-10-26")
        txt = "\n".join(learning.digest_lines(s, "2026-10-26"))
        self.assertIn("## What the system learned", txt)
        self.assertIn("a (score up by", txt)
        self.assertIn("b (failed 2 times in a row)", txt)
        self.assertIn("at least every 7 days", txt)
        self.assertNotIn("(+", txt)
        self.assertNotIn("(2 fails)", txt)
    def test_signals_section_keeps_the_facts(self):
        out = {
            "trust": {"Give Food": 0.5}, "agreement_n": {"Give Food": 2},
            "source_blame": {"IFAN": {"phone": 1}}, "signals": {"https://b.org/": ["dead"]},
            "boost": {"https://b.org/": 0.5}, "boosted_by": {"signal": ["https://b.org/"]},
            "why": {"https://b.org/": {"signal": 0.5}},
            "season": {"boost": 0.0, "note": "not enough history yet"},
            "demand_note": "no visitor data yet (reports/demand.json not present) - no effect",
            "visitor_note": "no visitor reports recorded yet - no effect",
            "conflicts": [{"id": "b", "chosen": None}], "healed": [], "hosts": {},
            "trend": [], "weights": {"signal": 0.8}, "review": {"signal": -1},
        }
        txt = "\n".join(LS.digest_lines(out, full=True))
        self.assertIn("## What the system learned (signals)", txt)
        self.assertIn("no visitor data yet", txt)
        self.assertIn("never added on its own", txt)
        self.assertIn("Give Food scores 0.50", txt)
        self.assertIn("its weight fell by one step", txt)
        self.assertNotIn("fail_rate", txt)
        self.assertNotIn("boosted_by", txt)

if __name__ == "__main__":
    unittest.main()
