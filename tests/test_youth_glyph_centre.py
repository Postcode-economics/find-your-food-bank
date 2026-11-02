"""Youth 16/25 symbol: centred stack at y=10.5 and y=21.5 (key, chip, card, marker share layers.js SYM.youth)."""
import os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class YouthGlyphCentre(unittest.TestCase):
    def test_layers_and_chip_match(self):
        L = open(os.path.join(ROOT, "layers.js"), encoding="utf-8").read()
        self.assertIn('y="10.5"', L)
        self.assertIn('y="21.5"', L)
        self.assertIn('dominant-baseline="central"', L)
        self.assertNotIn('textLength="15.6"', L)
        chip = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        frag = chip[chip.index('data-f="youth"'):chip.index('data-f="youth"') + 800]
        self.assertIn('width="28" height="28"', frag)
        self.assertIn('y="10.5"', frag)
        self.assertIn('y="21.5"', frag)


if __name__ == "__main__":
    unittest.main()
