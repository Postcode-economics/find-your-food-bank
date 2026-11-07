"""'Get food at:' centres list on donations-only cards (Newcastle Foodbank screenshot, 7 Nov 2026).

The 28 Oct QA B6 tap-area rule (inline card links get 14px padding cancelled by a -14px margin) also matched the boxed
centre-name buttons (.cen a[data-cid]), which are not inline links. Each box was pulled 14px up over the heading and its
address, and every Directions button ran into the next centre row. Centre boxes must be excluded from that rule, and on
a phone-size sheet no part of the centres list may overlap.
"""
import os, re, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
rd = lambda f: open(os.path.join(R, f), encoding='utf-8').read()

ROWS_JS = """()=>{const r=e=>e.getBoundingClientRect();const lh=document.querySelector('#sheetBody .lh');
  const rows=[...document.querySelectorAll('#sheetBody .cen li')].map(li=>{const a=li.querySelector('a[data-cid]'),s=li.querySelector('span'),d=li.querySelector('a.cdir');
    return {a:[r(a).top,r(a).bottom],s:[r(s).top,r(s).bottom],d:d?[r(d).top,r(d).bottom]:null}});
  return {lh:lh?r(lh).bottom:null,rows}}"""


def overlaps(info, tol=0.5):
    """Each block must start at or below the bottom of the one before it: heading, name, address, Directions, next row."""
    bad, prev = [], info['lh']
    for n, row in enumerate(info['rows']):
        for part in ('a', 's', 'd'):
            box = row[part]
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
        self.assertEqual(overlaps({'lh': 100, 'rows': [{'a': [104, 150], 's': [150, 170], 'd': [174, 230]}]}), [])
        self.assertTrue(overlaps({'lh': 100, 'rows': [{'a': [86, 150], 's': [136, 170], 'd': None}]}))


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
                faults = {}
                for fid in ids:
                    p.evaluate("id=>select(items.findIndex(x=>x.id===id))", fid)
                    p.wait_for_timeout(30)
                    info = p.evaluate(ROWS_JS)
                    self.assertTrue(info['rows'], fid)
                    bad = overlaps(info)
                    if bad:
                        faults[fid] = bad
                self.assertEqual(faults, {}, '%s: centres list overlaps on %d cards' % (scheme, len(faults)))
            finally:
                b.close()


if __name__ == '__main__':
    unittest.main()
