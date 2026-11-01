"""The type label on every shelters card uses the same three symbols as the pins and the strip.

House, sun, or 16 over 25, each in the blue square. The icon is the full height of the label.
A bed glyph, or any other picture in that label, is a failure. List cards and the pop-up sheet.
"""
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))

CHECK = r"""() => {
  const cards = [...document.querySelectorAll('#xlist .card.xsh, #sheet.open .card')];
  const out = [];
  for (const c of cards) {
    const name = ((c.querySelector('h3') || {}).textContent || '').slice(0, 48);
    const lab = c.querySelector('.utag, .xkind');
    const box = lab && lab.querySelector('.xmkbox');
    const svg = box && box.querySelector('svg');
    const id = c.dataset.id || '';
    const item = (window.SHELTERS && SHELTERS.items || []).find(i => i.id === id) || {};
    const expect = (item.kind === 'day_centre' || item.service === 'day_centre') ? 'sun'
      : item.kind === 'young_people' ? 'youth' : 'house';
    const html = svg ? svg.outerHTML : '';
    const sr = svg && svg.getBoundingClientRect();
    const lr = lab && lab.getBoundingClientRect();
    const svgs = lab ? [...lab.querySelectorAll('svg')] : [];
    out.push({
      name, id, expect, sym: box ? box.dataset.sym : '',
      nSvg: svgs.length,
      square: html.indexOf('M3 3h26v26H3z') >= 0,
      view: html.indexOf('1.6 1.6 28.8 28.8') >= 0,
      house: html.indexOf('M8 15.5l8-7.5 8 7.5V24H8z') >= 0,
      sun: html.indexOf('M16 8v2.8') >= 0,
      youth: html.indexOf('>16<') >= 0 && html.indexOf('>25<') >= 0,
      bed: (c.innerHTML || '').indexOf('M3 5v15') >= 0,
      pinTail: html.indexOf('l-5 9') >= 0,
      h: sr ? +sr.height.toFixed(1) : 0,
      w: sr ? +sr.width.toFixed(1) : 0,
      dTop: sr && lr ? +(sr.top - lr.top).toFixed(1) : 99,
      dBot: sr && lr ? +(lr.bottom - sr.bottom).toFixed(1) : 99
    });
  }
  return out;
}"""


def _fail(row):
    if not row['sym']:
        return 'no type symbol'
    if row['sym'] not in ('house', 'sun', 'youth') or row['sym'] != row['expect']:
        return 'symbol %s expected %s' % (row['sym'], row['expect'])
    if row['nSvg'] != 1 or not row['square'] or not row['view'] or row['pinTail']:
        return 'type label icon is not the blue square'
    if row['sym'] == 'house' and not row['house']:
        return 'house path missing'
    if row['sym'] == 'sun' and not row['sun']:
        return 'sun path missing'
    if row['sym'] == 'youth' and not row['youth']:
        return '16/25 missing'
    if row['bed']:
        return 'legacy bed icon'
    if abs(row['dTop']) > 1 or abs(row['dBot']) > 1:
        return 'icon not aligned to the label %s' % row
    if abs(row['h'] - row['w']) > 1:
        return 'icon not square %s' % row
    return ''


class Render(unittest.TestCase):
    def test_list_and_sheet_use_only_the_three_symbols(self):
        try:
            from playwright.sync_api import sync_playwright
            import newlook_render as R
        except Exception as e:
            raise unittest.SkipTest(str(e))
        if not os.path.exists('/usr/bin/google-chrome'):
            raise unittest.SkipTest('no chrome')
        with sync_playwright() as pw:
            b, p = R.open_page(pw, 'dark', 390)
            try:
                p.click('#v3big [data-l=sh]')
                p.wait_for_timeout(800)
                seen = set()
                # Several centres, then Show more, so the check is not just the first five.
                for q in ('SW1A 1AA', 'BN1 4NJ', 'M1 1AE'):
                    p.fill('#q', q)
                    p.press('#q', 'Enter')
                    p.wait_for_timeout(1800)
                    p.evaluate("() => { if (window.showMoreX) showMoreX('sh'); }")
                    p.wait_for_timeout(300)
                    rows = p.evaluate(CHECK)
                    self.assertTrue(rows, q)
                    bad = [(r['name'], _fail(r)) for r in rows if _fail(r)]
                    self.assertEqual(bad, [], (q, bad[:6]))
                    seen |= {r['sym'] for r in rows}
                self.assertIn('house', seen)
                self.assertIn('sun', seen)
                # The foyer is not in the nearest five of a generic search. Open it directly.
                p.evaluate("""() => {
                  const i = SHELTERS.items.find(x => x.kind === 'young_people');
                  nearest(i.lat, i.lng, i.postcode || i.name);
                }""")
                p.wait_for_timeout(500)
                for _ in range(8):
                    if p.evaluate("() => [...document.querySelectorAll('#xlist .xmkbox')].some(b => b.dataset.sym === 'youth')"):
                        break
                    p.evaluate("() => showMoreX('sh')")
                    p.wait_for_timeout(200)
                rows = p.evaluate(CHECK)
                youth = [r for r in rows if r['expect'] == 'youth']
                self.assertTrue(youth, rows)
                self.assertEqual([_fail(r) for r in youth], [''] * len(youth), youth)
                opened = p.evaluate("""() => {
                  let hit = null;
                  map.eachLayer(layer => { if (hit || !layer.eachLayer) return;
                    layer.eachLayer(m => { if (hit) return;
                      const cn = m.options && m.options.icon && m.options.icon.options && m.options.icon.options.className || '';
                      if (String(cn).indexOf('xpin') >= 0) hit = m; }); });
                  if (!hit) return false; hit.fire('click'); return true;
                }""")
                self.assertTrue(opened)
                p.wait_for_selector('#sheet.open .xmkbox', timeout=5000)
                sheet = p.evaluate(CHECK)
                sheet_rows = [r for r in sheet if r['name']]
                # The sheet card has no data-id, so expect falls through to house. Check the svg itself.
                live = p.evaluate("""() => {
                  const c = document.querySelector('#sheet.open .card');
                  const box = c.querySelector('.xmkbox');
                  const html = box.querySelector('svg').outerHTML;
                  const lab = c.querySelector('.utag,.xkind').getBoundingClientRect();
                  const sr = box.querySelector('svg').getBoundingClientRect();
                  return {sym: box.dataset.sym, bed: c.innerHTML.indexOf('M3 5v15') >= 0,
                    square: html.indexOf('M3 3h26v26H3z') >= 0, n: c.querySelectorAll('.utag svg, .xkind svg').length,
                    dTop: +(sr.top - lab.top).toFixed(1), dBot: +(lab.bottom - sr.bottom).toFixed(1),
                    h: +sr.height.toFixed(1), w: +sr.width.toFixed(1)};
                }""")
                self.assertIn(live['sym'], ('house', 'sun', 'youth'))
                self.assertFalse(live['bed'])
                self.assertTrue(live['square'])
                self.assertEqual(live['n'], 1)
                self.assertLessEqual(abs(live['dTop']), 1)
                self.assertLessEqual(abs(live['dBot']), 1)
                self.assertLessEqual(abs(live['h'] - live['w']), 1)
            finally:
                b.close()
