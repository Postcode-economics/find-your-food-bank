"""Full listing audit: uniform cards, shelter symbols, footer key order (Dean).

Runs in CI over every food bank, shelter (incl. area/no-pin rows), and warm space record
via UFacts + published data.js / shelters.js / warmspaces.js. Welsh checked on checked() line.
"""
import json, os, subprocess, unittest

ROOT = os.path.join(os.path.dirname(__file__), '..')
LAYERS = os.path.join(ROOT, 'layers.js')
V3CSS = os.path.join(ROOT, 'v3.css')

SYMBOL_NODE = r'''
const fs = require('fs');
const vm = require('vm');
const ctx = {window: {}, document: {documentElement: {lang: 'en'}}, console};
ctx.window = ctx; ctx.global = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx); } catch (e) {}
ctx.window.timesFmt = ctx.timesFmt;
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), ctx);
vm.runInContext(fs.readFileSync(process.argv[3], 'utf8'), ctx);
vm.runInContext(fs.readFileSync(process.argv[4], 'utf8'), ctx);
vm.runInContext(fs.readFileSync(process.argv[5], 'utf8'), ctx);
const U = ctx.UFacts;
function symKey(i) {
  if (!i || i.card_type === 'referral_hostel') return 'house';
  if (U.isYouth(i)) return 'youth';
  if (U.isDayCentre(i)) return 'sun';
  return 'house';
}
const sh = (ctx.SHELTERS && ctx.SHELTERS.items) || [];
const symBad = [];
sh.forEach(i => {
  const s = symKey(i);
  if (!['house', 'sun', 'youth'].includes(s)) symBad.push(i.id + ' sym ' + s);
});
process.stdout.write(JSON.stringify({sh: sh.length, symBad: symBad.slice(0, 20)}));
'''

CARD = open(os.path.join(ROOT, 'tests', 'test_card_uniform.py'), encoding='utf-8').read()
NODE = CARD.split("NODE = r'''")[1].split("'''")[0]


def footer_key_order():
    text = open(LAYERS, encoding='utf-8').read()
    marks = (
        "symSvg('food',20)",
        "symSvg('flame',20)",
        "symSvg('house',20)",
        "symSvg('sun',20)",
        "symSvg('youth',20)",
    )
    pos = [text.find(m) for m in marks]
    return all(p >= 0 for p in pos) and pos == sorted(pos)


class FullAudit(unittest.TestCase):
    def test_uniform_cards_all_layers(self):
        r = subprocess.run(
            ['node', '-e', NODE,
             os.path.join(ROOT, 'v3.js'), os.path.join(ROOT, 'facts.js'),
             os.path.join(ROOT, 'data.js'), os.path.join(ROOT, 'shelters.js'),
             os.path.join(ROOT, 'warmspaces.js')],
            capture_output=True, text=True, check=True)
        got = json.loads(r.stdout)
        self.assertEqual(got['problems'], [], 'uniform card problems: %s' % (got['problems'][:5],))

    def test_shelter_symbols_and_key_order(self):
        r = subprocess.run(
            ['node', '-e', SYMBOL_NODE,
             os.path.join(ROOT, 'v3.js'), os.path.join(ROOT, 'facts.js'),
             os.path.join(ROOT, 'data.js'), os.path.join(ROOT, 'shelters.js'),
             os.path.join(ROOT, 'warmspaces.js')],
            capture_output=True, text=True, check=True)
        got = json.loads(r.stdout)
        self.assertTrue(footer_key_order(), 'footer key row order in layers.js')
        self.assertEqual(got['symBad'], [], got)

    def test_type_icon_shell_colours_and_card_top_class(self):
        js = open(LAYERS, encoding='utf-8').read()
        css = open(V3CSS, encoding='utf-8').read()
        boot = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
        self.assertIn("food:{fill:'#F5C518'", js)
        self.assertIn("flame:{fill:'#D55E00'", js)
        self.assertIn("house:{fill:'#56B4E9'", js)
        sym_fn = js[js.index('const symSvg'):js.index('window.symSvg')]
        self.assertIn('SYM_SHELL[key]', sym_fn)
        self.assertNotIn('fill="#56B4E9" stroke="#0A1628" stroke-width="2.5"/>${SYM[key', sym_fn)
        self.assertIn('class="xtop xtop-${layer}"', js)
        self.assertIn('xtop.xtop-fb .utag{border-color:#F5C518', css)
        self.assertIn('xtop.xtop-ws .utag{border-color:#D55E00', css)

    def test_marker_card_and_key_use_same_layer_symbols(self):
        """Food bank bag, warm space flame, shelter house/sun/youth: map marker = card icon = footer key."""
        js = open(LAYERS, encoding='utf-8').read()
        boot = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
        bag = 'M9 13.5h14l-1.3 10.5H10.3z'
        flame = 'M16.2 7.2c'
        self.assertIn(bag, js, 'shopping bag inner missing from layers.js SYM.food')
        self.assertIn(bag, boot, 'food bank map pin must use the same bag symbol as cards/key')
        self.assertIn(flame, js, 'flame inner missing from layers.js SYM.flame')
        self.assertNotIn('M13 21c0-4', js, 'warm space map must not use the old droplet marker')
        self.assertIn("symSvg('flame',34", js, 'warm space map marker must use symSvg(flame)')
        self.assertIn("symSvg('food',20)", js)
        self.assertIn("symSvg('flame',20)", js)
        key_block = js[js.index('const lg=document.createElement'):js.index('const ft=document.querySelector')]
        card_top = js[js.index('function cardTop'):js.index('function cardTop') + 350]
        self.assertIn("symSvg(sk,26)", card_top)
        for needle in ("symSvg('food'", "symSvg('flame'"):
            self.assertIn(needle, key_block, 'footer key must use unified symbols')
        self.assertIn("symSvg(sk,26)", card_top, 'card top must use unified symSvg')
        self.assertIn("sk=layer==='fb'?'food':layer==='ws'?'flame'", card_top)


if __name__ == '__main__':
    unittest.main()
