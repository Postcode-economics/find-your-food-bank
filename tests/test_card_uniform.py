"""Every place card uses one formatter (Dean). Display only: the stored phone, times and
postcode are not rewritten. The test renders each live record and fails if the card text
drifts (row order, address, postcode, opening lines, wheelchair wording).
"""
import json, os, subprocess, unittest
ROOT = os.path.join(os.path.dirname(__file__), '..')
NODE = r'''
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
const PC = /^[A-Z]{1,2}\d[A-Z\d]? \d[A-Z]{2}$/;
const DAY = /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:\u2013(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun))?(?:, (?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:\u2013(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun))?)* /;
const ROWS = ['Who it’s for', 'How to get in', 'Opening times', 'Wheelchair access', 'Facilities'];
const WHEEL = new Set(['Yes', 'No', 'Partly', 'Not stated']);
function text(html){return String(html||'').replace(/<[^>]+>/g,'').replace(/\s+/g,' ').trim()}
function audit(layer, i){
  const bad = [];
  const id = i.id || i.name || '?';
  let addr = '';
  try { addr = U.addr(i); } catch (e) { return [id + ' addr threw']; }
  const plain = text(addr);
  if (/,\s*$/.test(plain) || /,\s*,/.test(plain)) bad.push(id + ' address punctuation');
  const pc = U.normPc(i.postcode || '');
  if (pc) {
    const bold = (addr.match(/<b>([^<]*)<\/b>\s*$/) || [])[1] || '';
    if (bold !== pc || !PC.test(bold)) bad.push(id + ' postcode ' + JSON.stringify(bold));
    if (plain.indexOf(pc) !== plain.lastIndexOf(pc)) bad.push(id + ' postcode repeated');
  }
  let lines = [];
  try { lines = U.timesLines(layer, i) || []; } catch (e) { bad.push(id + ' times threw'); }
  lines.forEach(l => {
    if (/times unknown/i.test(l)) bad.push(id + ' times unknown');
    if (/\d{2}:\d{2}-\d{2}:\d{2}/.test(l)) bad.push(id + ' hyphen ' + l.slice(0, 60));
    if (DAY.test(l) && /\bclosed\b/.test(l) && !/\bClosed\b/.test(l)) bad.push(id + ' closed case');
  });
  const block = U.block(layer, i, {});
  let at = -1;
  ROWS.forEach(label => {
    const n = block.indexOf(label);
    if (n < 0 || n < at) bad.push(id + ' row ' + label);
    at = n;
  });
  const wheel = text((block.split('Wheelchair access')[1] || '').split('Facilities')[0]);
  const word = (wheel.match(/Yes|No|Partly|Not stated/) || [])[0];
  if (!WHEEL.has(word)) bad.push(id + ' wheelchair ' + wheel.slice(0, 40));
  const checked = text(U.checked(i));
  if (!/Last checked/.test(checked) || !/Gwiriwyd ddiwethaf/.test(checked)) bad.push(id + ' checked');
  if (!/Not stated|Heb ei nodi|\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}/.test(checked)) bad.push(id + ' date');
  return bad;
}
const sets = [
  ['fb', (ctx.FB_DATA && ctx.FB_DATA.items) || []],
  ['sh', (ctx.SHELTERS && ctx.SHELTERS.items) || []],
  ['ws', (ctx.WARMSPACES && ctx.WARMSPACES.items) || []]
];
const out = {counts: {}, problems: []};
sets.forEach(([layer, items]) => {
  out.counts[layer] = items.length;
  items.forEach(i => { const b = audit(layer, i); if (b.length) out.problems.push(layer + ' ' + b[0]); });
});
out.problems = out.problems.slice(0, 30);
out.n = sets.reduce((n, s) => n + s[1].length, 0);
const hall = ((ctx.FB_DATA && ctx.FB_DATA.items) || []).find(i => i.id === 'salvation-army/brighton-congress-hall');
out.hall = hall ? text(U.checked(hall)) : '';
const foyer = ((ctx.SHELTERS && ctx.SHELTERS.items) || []).find(i => i.id === 'man-brighton-hove-foyer');
out.foyer = foyer ? (U.howPair('sh', foyer) || [])[0] : '';
process.stdout.write(JSON.stringify(out));
'''


class Uniform(unittest.TestCase):
    def test_every_live_card(self):
        r = subprocess.run(
            ['node', '-e', NODE,
             os.path.join(ROOT, 'v3.js'), os.path.join(ROOT, 'facts.js'),
             os.path.join(ROOT, 'data.js'), os.path.join(ROOT, 'shelters.js'),
             os.path.join(ROOT, 'warmspaces.js')],
            capture_output=True, text=True, check=True)
        got = json.loads(r.stdout)
        self.assertGreater(got['counts'].get('fb', 0), 2000, got['counts'])
        self.assertGreater(got['counts'].get('sh', 0), 50, got['counts'])
        self.assertGreater(got['counts'].get('ws', 0), 50, got['counts'])
        self.assertEqual(got['problems'], [], 'checked %s across %s' % (got['n'], got['counts']))
        self.assertIn('31 Oct 2026', got.get('hall', ''), got.get('hall'))
        self.assertEqual(got.get('foyer'), 'Referral needed: Brighton & Hove City Council Housing Options team')
