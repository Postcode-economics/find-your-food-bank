"""Directions hidden without a pin, 116 numbers accepted, explicit kind beats the youth heuristic."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEL_JS = re.compile(
    r"tel=i\.tel!==undefined\?\(/\^\(0\\d\{9,10\}\|116\\d\{3\}\)\$/\.test\(i\.tel\)\?i\.tel:''\):"
    r"\(/\^\(0\\d\{9,10\}\|\\?\+44\\d\{9,10\}\|116\\d\{3\}\)\$/\.test\(tel0\)\?tel0:''\)"
)
HAS_PIN = "const hasPin=!i.no_pin&&Number.isFinite(Number(i.lat))&&Number.isFinite(Number(i.lng));"
DIR_COND = 'const dir=hasPin?`<a class="btn gm"'
KIND_GUARD = "i.kind==='day_centre'||i.kind==='hostel'||i.kind==='night_shelter'"


class TemplatePatch(unittest.TestCase):
    def test_layers_hides_directions_without_coords(self):
        text = (ROOT / "layers.js").read_text()
        self.assertIn(HAS_PIN, text)
        self.assertIn(DIR_COND, text)
        self.assertIn("destination=${i.lat},${i.lng}", text)
        self.assertNotIn('const dir=`<a class="btn gm"', text)

    def test_layers_accepts_116_numbers(self):
        text = (ROOT / "layers.js").read_text()
        self.assertIn("116\\d{3}", text)
        self.assertIsNotNone(TEL_JS.search(text))

    def test_isYouth_respects_explicit_non_youth_kind(self):
        facts = (ROOT / "facts.js").read_text()
        self.assertIn("i.kind === 'day_centre' || i.kind === 'hostel' || i.kind === 'night_shelter'", facts)
        self.assertIn(KIND_GUARD, (ROOT / "layers.js").read_text())

    def test_referral_hostel_label_uses_card_type(self):
        layers = (ROOT / "layers.js").read_text()
        self.assertIn("i.card_type==='referral_hostel')?'refHostel'", layers)
        facts = (ROOT / "facts.js").read_text()
        self.assertIn("i.card_type === 'referral_hostel'", facts)


if __name__ == "__main__":
    unittest.main()
