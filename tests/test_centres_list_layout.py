"""'Get food at:' centres list on donations-only cards (Newcastle Foodbank screenshot, 7 Nov 2026).

The 28 Oct QA B6 tap-area rule (inline card links get 14px padding cancelled by a -14px margin) also matched the boxed
centre-name buttons (.cen a[data-cid]), which are not inline links. Each box was pulled 14px up over the heading and its
address, and every Directions button ran into the next centre row. Centre boxes must be excluded from that rule, and on
a phone-size sheet no part of the centres list may overlap.

7 Nov 2026 (Dean): each distribution centre should show ONE address and ONE Directions button. The parent donations-only
card repeated every centre's address and a Directions button in its list (Newcastle Foodbank 5 of each, Newcastle (Staffs)
6). The list now shows only the tappable centre names; each centre's own card keeps its single address and Directions.
"""
import os, re, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
rd = lambda f: open(os.path.join(R, f), encoding='utf-8').read()

ROWS_JS = """()=>{const r=e=>e.getBoundingClientRect();const lh=document.querySelector('#sheetBody .lh');
  const rows=[...document.querySelectorAll('#sheetBody .cen li')].map(li=>{const a=li.querySelector('a[data-cid]');
    return {cid:a?a.dataset.cid:null,a:a?[r(a).top,r(a).bottom]:null,span:li.querySelectorAll('span').length,
      cdir:li.querySelectorAll('a.cdir').length,dir:[...li.querySelectorAll('a')].filter(x=>/Directions/i.test(x.textContent)).length}});
  return {lh:lh?r(lh).bottom:null,rows}}"""

# Same path as the data-cid click handler (setView to the centre, then select it), without the 300ms delay.
OPEN_CENTRE_JS = """async id=>{const k=items.findIndex(x=>x.id===id);if(k<0)return;map.setView([items[k].lat,items[k].lng],15,{animate:false});
  for(let t=0;t<40;t++){try{select(k,false);return}catch(e){await new Promise(r=>setTimeout(r,25))}}select(k,false)}"""
CENTRE_JS = """()=>{const b=document.querySelector('#sheetBody');if(!b)return {found:0};
  const d=[...b.querySelectorAll('a')].filter(x=>x.matches('a.btn.gm')||/^\\s*Directions\\s*$/i.test(x.textContent));
  return {found:1,dir:d.length,cen:b.querySelectorAll('.cen').length}}"""


def overlaps(info, tol=0.5):
    """Each centre-name box must start at or below the bottom of the block before it: heading, name, next name."""
    bad, prev = [], info['lh']
    for n, row in enumerate(info['rows']):
        for part in ('a',):
            box = row.get(part)
            if box is None:
                continue
            if prev is not None and box[0] < prev - tol:
                bad.append((n, part, round(prev - box[0], 1)))
            prev = box[1]
    return bad


class CentresCss(unittest.TestCase):
    def test_tap_area_rule_skips_centre_boxes(self):
        css = rd('v3.css')
        m = re.search(r"[^}]*\.card a:not\(\.btn\)[^{]*\{padding-top:14px!important;padding-bottom:14px!important;margin-top:-14px!important", css)
        self.assertIsNotNone(m, 'B6 inline-link tap-area rule not found')
        self.assertIn(':not([data-cid])', m.group(0), 'centre-name boxes (.cen a[data-cid]) must not get the inline-link negative margin')

    def test_overlap_helper(self):
        self.assertEqual(overlaps({'lh': 100, 'rows': [{'a': [104, 150]}, {'a': [154, 200]}]}), [])
        self.assertTrue(overlaps({'lh': 100, 'rows': [{'a': [86, 150]}]}))
        self.assertTrue(overlaps({'lh': 100, 'rows': [{'a': [104, 150]}, {'a': [140, 190]}]}))


class CentresTemplate(unittest.TestCase):
    def test_list_rows_are_names_only(self):
        html = rd('index.html')
        m = re.search(r'Get food at:</div>(.*?)Contact the food bank for where to get food\.', html, re.S)
        self.assertIsNotNone(m, "'Get food at:' list template not found")
        tpl = m.group(1)
        self.assertIn('data-cid="${esc(c.id)}">${esc(c.name)}</a></li>', tpl)
        self.assertNotIn('c.address', tpl, 'centre address must only be on the centre card, not the parent list')
        self.assertNotIn('cdir', tpl, 'Directions belongs on the centre card, not the parent list')
        self.assertNotIn('Directions', tpl)


class CentresRendered(unittest.TestCase):
    """Every published card with centres, opened in the real sheet at iPhone width (390px), light and dark."""
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
            import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import newlook_render as NR
        except Exception as e:
            raise unittest.SkipTest('playwright not available: %s' % e)
        cls.NR = NR; cls.pw = sync_playwright().start()

    @classmethod
    def tearDownClass(cls):
        cls.pw.stop()

    def test_no_overlap_in_any_centres_list(self):
        for scheme in ('dark', 'light'):
            try:
                b, p = self.NR.open_page(self.pw, scheme)
            except Exception as e:
                raise unittest.SkipTest('no browser: %s' % e)
            try:
                ids = p.evaluate("()=>items.filter(i=>(i.centres||[]).length).map(i=>i.id)")
                self.assertTrue(ids, 'no cards with centres in data.js')
                faults, extras, checked = {}, {}, 0
                for fid in ids:
                    p.evaluate("id=>select(items.findIndex(x=>x.id===id))", fid)
                    p.wait_for_timeout(30)
                    info = p.evaluate(ROWS_JS)
                    self.assertTrue(info['rows'], fid)
                    bad = overlaps(info)
                    if bad:
                        faults[fid] = bad
                    for row in info['rows']:
                        if not row['cid'] or row['span'] or row['cdir'] or row['dir']:
                            extras.setdefault(fid, []).append(row)
                self.assertEqual(faults, {}, '%s: centres list overlaps on %d cards' % (scheme, len(faults)))
                self.assertEqual(extras, {}, '%s: centres list rows with address/Directions on %d cards' % (scheme, len(extras)))
                # Each listed centre opened from the list keeps exactly one Directions and no centres list of its own.
                cen = {}
                for fid in ids:
                    for cid in p.evaluate("id=>items.find(x=>x.id===id).centres.map(c=>c.id)", fid):
                        p.evaluate(OPEN_CENTRE_JS, cid)
                        got = p.evaluate(CENTRE_JS)
                        if got['found'] and (got['dir'] != 1 or got['cen']):
                            cen[cid] = got
                        checked += got['found']
                self.assertGreater(checked, 0, 'no listed centre could be opened')
                self.assertEqual(cen, {}, '%s: centre cards without exactly one Directions' % scheme)
            finally:
                b.close()


if __name__ == '__main__':
    unittest.main()
